"""Inline datapull/output/trust_losses.csv into template.html -> index.html (self-contained snapshot).
Usage: python build_app.py
"""
import csv
import json
import re
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parent
DATA_DIR = ROOT.parent / "datapull" / "output"
ISSUER_ORDER = ["Carvana", "CarMax"]


def short_name(name):
    m = re.search(r"(\d{4}-[A-Z0-9]+)\s*$", name, re.I)
    tag = m.group(1).upper() if m else name
    return f"Select {tag}" if "select" in name.lower() else tag


def edgar_link(cik):
    return f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type=10-D"


def main():
    with open(DATA_DIR / "trust_losses.csv", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    with open(DATA_DIR / "parse_issues.csv", encoding="utf-8") as f:
        issues = list(csv.DictReader(f))

    trusts = {}
    for r in rows:
        t = trusts.setdefault(r["cik"], {
            "issuer": r["issuer"], "name": r["trust_name"], "short": short_name(r["trust_name"]),
            "program": r["program"], "year": int(r["issue_year"]), "cik": r["cik"],
            "pool": round(float(r["original_pool_balance"])), "edgar": edgar_link(r["cik"]), "points": [],
        })
        # [month, gross %, net %, period end, cum gross $, cum net $] -- the $ amounts drive the
        # trailing-window recovery rates (recoveries = gross - net charge-offs).
        t["points"].append([int(r["month"]), round(float(r["gross_loss_pct"]), 4),
                            round(float(r["net_loss_pct"]), 4), r["period_end"],
                            round(float(r["cum_gross_loss"])), round(float(r["cum_net_loss"]))])

    issuers = {}
    for key in ISSUER_ORDER:
        ts = sorted((t for t in trusts.values() if t["issuer"] == key and t["points"]),
                    key=lambda t: (t["year"], t["program"] != "AOT", t["short"]))
        issuers[key] = {"trusts": [{**{k: v for k, v in t.items() if k != "issuer"}, "points": sorted(t["points"])} for t in ts]}

    data = {
        "asOf": date.today().isoformat(),
        "latestPeriod": max(r["period_end"] for r in rows),
        "issuers": issuers,
        "issues": [{
            "trust": i["trust_name"], "form": i["form"], "filed": i["filing_date"], "reason": i["reason"],
            "url": f"https://www.sec.gov/Archives/edgar/data/{i['cik']}/{i['accession'].replace('-', '')}/{i['accession']}-index.htm",
        } for i in sorted(issues, key=lambda i: (i["trust_name"], i["filing_date"]))],
    }
    html = (ROOT / "template.html").read_text(encoding="utf-8")
    html = html.replace("/*__DATA__*/null", json.dumps(data, separators=(",", ":")))
    (ROOT / "index.html").write_text(html, encoding="utf-8")
    n = sum(len(v["trusts"]) for v in issuers.values())
    print(f"index.html: {n} trusts, {len(rows)} points, {len(issues)} issues, {len(html) / 1e3:.0f} KB")


if __name__ == "__main__":
    main()
