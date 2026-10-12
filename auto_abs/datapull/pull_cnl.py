"""Pull monthly cumulative gross and net losses (% of original pool balance) for Carvana and
CarMax auto ABS trusts (2020 onward) from each trust's 10-D servicer report (EX-99.1) on EDGAR.

Raw exhibits are cached under raw/ so reruns only fetch new filings.
Output: output/trust_losses.csv (one row per trust per collection period) and
output/parse_issues.csv (filings whose report could not be parsed).
Usage: python pull_cnl.py
"""
import csv
import html
import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from pathlib import Path

USER_AGENT = "SRS Research fintan.creedon@srsfund.com"
MIN_YEAR = 2020
ROOT = Path(__file__).parent
RAW_DIR = ROOT / "raw"
OUT_DIR = ROOT / "output"

# (issuer, name stem on EDGAR)
STEMS = [
    ("Carvana", "Carvana Auto Receivables Trust"),
    ("CarMax", "CarMax Auto Owner Trust"),
    ("CarMax", "CarMax Select Receivables Trust"),
]

_lock = threading.Lock()
_last = [0.0]


def http_get(url, tries=5):
    """GET with a shared throttle (<= ~8 req/s across threads) and backoff on 429/5xx."""
    for attempt in range(tries):
        with _lock:
            wait = _last[0] + 0.125 - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            _last[0] = time.monotonic()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=60) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503) and attempt < tries - 1:
                time.sleep(2 ** attempt * 2)
                continue
            raise
        except (urllib.error.URLError, TimeoutError):
            if attempt < tries - 1:
                time.sleep(2 ** attempt * 2)
                continue
            raise


def program_of(name):
    m = re.search(r"(\d{4})-([A-Z]+)?\d*$", name.strip(), re.I)
    suffix = (m.group(2) or "").upper() if m else ""
    if "carvana" in name.lower():
        return "Non-prime" if suffix == "N" else "Prime"
    return "Select" if "select" in name.lower() else "AOT"


def discover_trusts():
    trusts = []
    for issuer, stem in STEMS:
        start = 0
        while True:
            q = urllib.parse.urlencode({"action": "getcompany", "company": stem, "type": "",
                                        "owner": "include", "count": 100, "start": start})
            page = http_get("https://www.sec.gov/cgi-bin/browse-edgar?" + q).decode("utf-8", "replace")
            rows = re.findall(r'CIK=(\d{10})[^>]*>\d+</a></td>\s*<td[^>]*>([^<]+)', page)
            for cik, name in rows:
                m = re.search(r"(\d{4})-", name)
                if m and int(m.group(1)) >= MIN_YEAR:
                    trusts.append({"issuer": issuer, "cik": str(int(cik)), "edgar_name": name.strip(),
                                   "program": program_of(name), "issue_year": int(m.group(1))})
            if len(rows) < 100:
                break
            start += 100
    return trusts


def list_10d(cik):
    sub = json.loads(http_get(f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json"))
    blocks = [sub["filings"]["recent"]]
    for f in sub["filings"].get("files", []):
        blocks.append(json.loads(http_get(f"https://data.sec.gov/submissions/{f['name']}")))
    out = []
    for r in blocks:
        for i, form in enumerate(r["form"]):
            if form in ("10-D", "10-D/A"):
                out.append({"accession": r["accessionNumber"][i], "form": form, "filing_date": r["filingDate"][i]})
    return sub["name"], out


def fetch_ex99(cik, accession):
    """Return (exhibit text, exhibit url), cached on disk."""
    cache = RAW_DIR / cik / f"{accession}.txt"
    meta = RAW_DIR / cik / f"{accession}.url"
    if cache.exists() and meta.exists():
        return cache.read_text(encoding="utf-8"), meta.read_text(encoding="utf-8")
    base = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession.replace('-', '')}"
    idx = http_get(f"{base}/{accession}-index.htm").decode("utf-8", "replace")
    url = None
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", idx, re.S):
        href = re.search(r'href="([^"]+)"', row)
        if href and re.search(r">\s*EX-99(\.\d*)?\s*<", row) and not href.group(1).lower().endswith((".jpg", ".gif", ".png", ".pdf")):
            url = "https://www.sec.gov" + href.group(1)
            break
    text = text_of(http_get(url)) if url else ""
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(text, encoding="utf-8")
    meta.write_text(url or "", encoding="utf-8")
    return text, url or ""


def text_of(raw):
    s = raw.decode("utf-8", "replace")
    s = re.sub(r"(?is)<(script|style).*?</\1>", " ", s)
    s = re.sub(r"(?i)</(tr|p|div)\s*>|<br\s*/?>", "\n", s)
    s = re.sub(r"(?i)</t[dh]>", " | ", s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s).replace("\xa0", " ").replace("​", "")
    return "\n".join(re.sub(r"[ \t]+", " ", ln).strip() for ln in s.splitlines() if ln.strip())


# ---------------------------------------------------------------- parsing

NUM = r"\(?\$?\s*([\d,]+(?:\.\d+)?)\)?"
GAP = r"[\s$]*"


def _flatten(t):
    """One line, cell separators dropped, '(14 )' -> '(14)', '1.62 %' -> '1.62%'."""
    s = re.sub(r"[‐-―−]", "-", t)
    s = re.sub(r"[|\s]+", " ", s)
    s = re.sub(r"\(\s*(\d+)\s*\)", r"(\1)", s)
    return re.sub(r"(\d)\s+%", r"\1%", s)


def _num(s):
    return float(s.replace(",", ""))


def _first(pattern, text):
    m = re.search(pattern, text, re.I | re.S)
    return m


def _date(s):
    for fmt in ("%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def parse_carmax(t):
    flat = _flatten(t)
    period = _first(r"Collection Period" + GAP + r"(\d{1,2}/\d{1,2}/\d{2,4})\s*-\s*(\d{1,2}/\d{1,2}/\d{2,4})", flat)
    pool = _first(r"Initial Pool Balance" + GAP + NUM, flat)
    i = flat.lower().find("cumulative loss activity")
    cum = flat[i:] if i >= 0 else flat
    gross = _first(r"Defaulted Receivables \(charge-?offs\)" + GAP + r"[\d,]+" + GAP + NUM, cum)
    net_amt = _first(r"Cumulative Net Losses \(Ln[^)]*\)" + GAP + NUM, cum)
    ratio = _first(r"Ratio of Cumulative Net Losses to Initial Pool Balance(?: \(Ln[^)]*\))?" + GAP + r"(-?[\d.]+)%", cum)
    return _assemble(period, pool, gross, net_amt, ratio)


def parse_carvana(t):
    flat = _flatten(t)
    period = _first(r"Collection Period:?\s*(\d{1,2}/\d{1,2}/\d{2,4})\s*(?:Through|-|to)\s*(\d{1,2}/\d{1,2}/\d{2,4})", flat)
    pool = _first(r"Original Pool Balance as of (?:the )?Cut-?off Date\s*\(\d+\)" + GAP + NUM, flat)
    gross = _first(r"Aggregate Gross Charged-?Off Receivables? losses as of the last day of the current Collection Period\s*(?:\{[^}]*\}\s*)?\(\d+\)" + GAP + NUM, flat)
    net_amt = _first(r"aggregate amount of Net Charged-?Off Receivables? losses as of the last day of the current Collection Period\s*(?:\{[^}]*\}\s*)?\(\d+\)" + GAP + NUM, flat)
    # Columns are Original / [Prev. Month] / Current; the first period has no Prev. Month column.
    ratio = _first(r"Aggregate Realized Loss percentage[^(]*\{[^}]*\}\s*\(\d+\)(?:\s*\(?-?[\d.]+\)?%)*?\s*\(?(-?[\d.]+)\)?%(?!\s*\(?-?[\d.]+\)?%)", flat)
    return _assemble(period, pool, gross, net_amt, ratio)


def _assemble(period, pool, gross, net_amt, ratio):
    missing = [k for k, v in (("period", period), ("pool", pool), ("gross", gross), ("net", net_amt or ratio)) if not v]
    if missing:
        return None, "missing " + ", ".join(missing)
    start, end = _date(period.group(1)), _date(period.group(2))
    pool_v = _num(pool.group(1))
    gross_v = _num(gross.group(1))
    net_v = _num(net_amt.group(1)) if net_amt else None
    rep = float(ratio.group(1)) if ratio else None
    # Prefer the reported ratio when it carries 4 dp (CarMax); Carvana reports 2 dp, so use the
    # unrounded amount / pool, which matches the reported ratio to within rounding.
    if rep is not None and (net_v is None or len(ratio.group(1).split(".")[-1]) >= 4):
        net_pct = rep
    else:
        net_pct = net_v / pool_v * 100
    return {
        "period_start": start, "period_end": end, "original_pool_balance": pool_v,
        "cum_gross_loss": gross_v, "cum_net_loss": net_v,
        "gross_loss_pct": gross_v / pool_v * 100, "net_loss_pct": net_pct,
        "net_loss_pct_reported": rep,
    }, None


# ---------------------------------------------------------------- main

def process_trust(trust):
    name, filings = list_10d(trust["cik"])
    trust["trust_name"] = re.sub(r"\s+", " ", name).strip()
    parser = parse_carvana if trust["issuer"] == "Carvana" else parse_carmax
    rows, issues = [], []
    for f in filings:
        try:
            text, url = fetch_ex99(trust["cik"], f["accession"])
        except Exception as e:  # noqa: BLE001 - log and continue
            issues.append({**trust, **f, "reason": f"fetch failed: {e}", "url": ""})
            continue
        if not text:
            if f["form"] == "10-D/A":
                continue  # amendment of the cover page only; the original report stands
            issues.append({**trust, **f, "reason": "no EX-99 exhibit", "url": url})
            continue
        rec, why = parser(text)
        if rec is None:
            issues.append({**trust, **f, "reason": why, "url": url})
            continue
        # A 10-D is filed in the month after its collection period. CarMax has filed reports
        # with a stale header (e.g. AOT 2025-2 May/Jun 2025 both say April); trust the filing date.
        fd = date.fromisoformat(f["filing_date"])
        expected = date(fd.year, fd.month, 1) - timedelta(days=1)
        if f["form"] == "10-D" and (rec["period_end"].year, rec["period_end"].month) != (expected.year, expected.month):
            rec["period_note"] = f"header period {rec['period_end']} overridden by filing date"
            rec["period_start"], rec["period_end"] = expected.replace(day=1), expected
        rows.append({**trust, **f, **rec, "url": url})
    return trust, rows, issues


def month_diff(a, b):
    return (b.year - a.year) * 12 + (b.month - a.month)


def main():
    RAW_DIR.mkdir(exist_ok=True)
    OUT_DIR.mkdir(exist_ok=True)
    trusts = discover_trusts()
    print(f"{len(trusts)} trusts from {MIN_YEAR}")
    all_rows, all_issues = [], []
    with ThreadPoolExecutor(max_workers=4) as pool:
        for trust, rows, issues in pool.map(process_trust, trusts):
            print(f"  {trust['trust_name']}: {len(rows)} periods, {len(issues)} issues")
            all_rows += rows
            all_issues += issues

    # One row per trust per period: an amendment (10-D/A) supersedes the original, then latest filing wins.
    best = {}
    for r in sorted(all_rows, key=lambda r: (r["form"] == "10-D/A", r["filing_date"], r["accession"])):
        best[(r["cik"], r["period_end"])] = r
    rows = sorted(best.values(), key=lambda r: (r["issuer"], r["trust_name"], r["period_end"]))

    first = {}
    for r in rows:
        first.setdefault(r["cik"], r["period_end"])
    for r in rows:
        r["month"] = month_diff(first[r["cik"]], r["period_end"]) + 1

    cols = ["issuer", "program", "issue_year", "trust_name", "cik", "month", "period_start", "period_end",
            "form", "filing_date", "accession", "original_pool_balance", "cum_gross_loss", "cum_net_loss",
            "gross_loss_pct", "net_loss_pct", "net_loss_pct_reported", "period_note", "url"]
    with open(OUT_DIR / "trust_losses.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    icols = ["issuer", "trust_name", "cik", "form", "filing_date", "accession", "reason", "url"]
    with open(OUT_DIR / "parse_issues.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=icols, extrasaction="ignore")
        w.writeheader()
        w.writerows(all_issues)
    print(f"wrote {len(rows)} rows, {len(all_issues)} issues; as of {date.today()}")


if __name__ == "__main__":
    main()
