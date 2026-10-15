"""One-off pull: forward off-lease maturity schedule from public auto-lease ABS (EDGAR ABS-EE, EX-102).

KMX checklist item 8. For each public auto-lease trust that is still reporting, take the latest
ABS-EE asset-level file and count the active leases (and their residual value) by scheduled
termination month.

SEC fair access: declared User-Agent and no more than 5 requests/sec (limit is 10).
Usage: python pull_lease_abs.py   (writes output/lease_maturity_schedule.csv; raw files cached in raw/)
"""
import csv
import json
import re
import time
import urllib.request
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

USER_AGENT = "SRS Research fintan.creedon@srsfund.com"
ROOT = Path(__file__).parent
RAW_DIR = ROOT / "raw"
OUT_DIR = ROOT / "output"

# Issuer label -> regex on the EDGAR entity name. Toyota and Hyundai lease deals are mostly 144A (not on EDGAR).
ISSUERS = {
    "GM Financial": r"^GM FINANCIAL AUTOMOBILE LEASING TRUST \d{4}-\d",
    "Ford Credit": r"^FORD CREDIT AUTO LEASE TRUST \d{4}-[A-Z]",
    "Nissan": r"^NISSAN AUTO LEASE TRUST \d{4}-[A-Z]",
    "BMW": r"^BMW VEHICLE LEASE TRUST \d{4}-\d",
    "Mercedes-Benz": r"^MERCEDES-BENZ AUTO LEASE TRUST \d{4}-[A-Z]",
    "Volkswagen": r"^VOLKSWAGEN AUTO LEASE TRUST \d{4}-[A-Z]",
    "World Omni": r"^WORLD OMNI AUTOMOBILE LEASE SECURITIZATION TRUST \d{4}-[A-Z]",
    "Honda": r"^HONDA AUTO LEASE TRUST",  # usually none public; kept to confirm
    "Toyota": r"^TOYOTA LEASE TRUST",
    "Hyundai": r"^HYUNDAI AUTO LEASE SECURITIZATION TRUST",
}
STALE_AFTER_DAYS = 120  # skip trusts whose latest ABS-EE is older than this (paid off / called)

# EX-102 auto-lease field names (Reg AB II). The first one present in a file is used.
MATURITY_FIELDS = ["scheduledTerminationDate", "leaseMaturityDate", "originalLeaseMaturityDate"]
RESIDUAL_FIELDS = ["baseResidualValue", "contractResidualValue", "securitizationResidualValue"]
TERMINATED_FIELDS = ["terminationIndicator", "zeroBalanceCode"]


def http_get(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Encoding": "identity"})
    time.sleep(0.2)
    return urllib.request.urlopen(req)


def cached(url, dest):
    if not (dest.exists() and dest.stat().st_size > 0):
        tmp = dest.with_suffix(dest.suffix + ".part")
        with http_get(url) as resp, open(tmp, "wb") as f:
            while chunk := resp.read(1 << 20):
                f.write(chunk)
        tmp.replace(dest)
        print(f"  downloaded {dest.name} ({dest.stat().st_size / 1e6:.1f} MB)")
    return dest


def find_trusts():
    """Match lease-trust entity names in EDGAR's full CIK list."""
    path = cached("https://www.sec.gov/Archives/edgar/cik-lookup-data.txt", RAW_DIR / "cik-lookup-data.txt")
    patterns = {k: re.compile(v) for k, v in ISSUERS.items()}
    trusts = {}
    with open(path, encoding="latin-1") as f:
        for line in f:
            # Lines look like "NAME:0001234567:"; names can contain colons
            name, _, cik = line.rstrip("\n").rstrip(":").rpartition(":")
            if not cik.isdigit():
                continue
            for issuer, pat in patterns.items():
                if pat.match(name.upper()):
                    trusts[int(cik)] = (issuer, name.strip())
    return trusts


def latest_abs_ee(cik):
    with http_get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json") as resp:
        recent = json.load(resp)["filings"]["recent"]
    hits = [(d, a) for f, d, a in zip(recent["form"], recent["filingDate"], recent["accessionNumber"]) if f == "ABS-EE"]
    return max(hits) if hits else None


def find_ex102(cik, accession):
    base = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession.replace('-', '')}"
    with http_get(f"{base}/index.json") as resp:
        items = json.load(resp)["directory"]["item"]
    xmls = [i for i in items if i["name"].lower().endswith(".xml") and "103" not in i["name"]]
    if not xmls:
        raise RuntimeError(f"No EX-102 XML in {base}")
    return f"{base}/{max(xmls, key=lambda i: int(i.get('size') or 0))['name']}"


def local_name(tag):
    return tag.rsplit("}", 1)[-1]


def parse_month(value):
    """EX-102 dates come as MM/YYYY, MM-YYYY, YYYY-MM, MM/DD/YYYY or YYYY-MM-DD."""
    v = (value or "").strip()
    for fmt in ("%m/%Y", "%m-%Y", "%Y-%m", "%m/%d/%Y", "%Y-%m-%d"):
        try:
            d = datetime.strptime(v, fmt)
            return date(d.year, d.month, 1)
        except ValueError:
            pass
    return None


def first_present(record, fields):
    return next((f for f in fields if record.get(f) not in (None, "")), None)


def schedule_from_file(path):
    """Active leases and residual value by scheduled termination month."""
    counts, residual = defaultdict(int), defaultdict(float)
    mat_field = res_field = None
    for _, elem in ET.iterparse(path, events=("end",)):
        if local_name(elem.tag) != "assets":
            continue
        rec = {local_name(c.tag): (c.text or "").strip() for c in elem}
        elem.clear()
        if any(rec.get(f) not in (None, "", "false", "0") for f in TERMINATED_FIELDS):
            continue
        mat_field = mat_field or first_present(rec, MATURITY_FIELDS)
        res_field = res_field or first_present(rec, RESIDUAL_FIELDS)
        if mat_field is None:
            raise RuntimeError(f"No maturity field in {path.name}; fields seen: {sorted(rec)}")
        month = parse_month(rec.get(mat_field))
        if month is None:
            continue
        counts[month] += 1
        try:
            residual[month] += float(rec.get(res_field) or 0)
        except ValueError:
            pass
    return counts, residual, mat_field, res_field


def main():
    RAW_DIR.mkdir(exist_ok=True)
    OUT_DIR.mkdir(exist_ok=True)
    trusts = find_trusts()
    print(f"{len(trusts)} candidate lease trusts on EDGAR")

    rows = []
    for cik, (issuer, name) in sorted(trusts.items(), key=lambda kv: kv[1]):
        latest = latest_abs_ee(cik)
        if latest is None:
            continue
        filed, accession = latest
        if (date.today() - date.fromisoformat(filed)).days > STALE_AFTER_DAYS:
            continue
        print(f"{name} (ABS-EE filed {filed})")
        xml_path = cached(find_ex102(cik, accession), RAW_DIR / f"lease_{cik}_{accession}.xml")
        counts, residual, mat_field, res_field = schedule_from_file(xml_path)
        print(f"  {sum(counts.values()):,} active leases; maturity={mat_field}, residual={res_field}")
        for month in sorted(counts):
            rows.append({
                "issuer": issuer, "trust": name, "cik": cik, "filing_date": filed, "accession": accession,
                "maturity_month": month.isoformat(), "leases": counts[month], "residual_value": round(residual[month], 2),
            })

    out = OUT_DIR / "lease_maturity_schedule.csv"
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else ["issuer"])
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {out} ({len(rows):,} rows)")


if __name__ == "__main__":
    main()
