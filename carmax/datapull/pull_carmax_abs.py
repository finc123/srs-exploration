"""Pull loan-level ABS-EE (EX-102) data from SEC EDGAR for selected CarMax trusts
and write one Excel workbook per trust.

Source: each trust's first monthly servicing report after closing.
Usage: python pull_carmax_abs.py
"""
import json
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

import xlsxwriter

USER_AGENT = "SRS Research fintan.creedon@srsfund.com"
ROOT = Path(__file__).parent
RAW_DIR = ROOT / "raw"
OUT_DIR = ROOT / "output"

# (trust name, CIK, accession, filing date, reporting period end)
TRUSTS = [
    ("CarMax Auto Owner Trust 2025-3", "2074530", "0002074530-25-000003", "2025-08-15", "2025-07-31"),
    ("CarMax Select Receivables Trust 2025-B", "2083722", "0002083722-25-000003", "2025-10-15", "2025-09-30"),
    ("CarMax Auto Owner Trust 2026-2", "2117307", "0002117307-26-000003", "2026-05-15", "2026-04-30"),
    ("CarMax Select Receivables Trust 2026-B", "2137261", "0002137261-26-000003", "2026-07-15", "2026-06-30"),
]

# Column order matches the 72degree AutoABS detail files
COLUMNS = [
    "assetTypeNumber", "assetNumber", "reportingPeriodBeginningDate", "reportingPeriodEndingDate",
    "zeroBalanceEffectiveDate", "zeroBalanceCode", "modificationTypeCode", "paymentExtendedNumber",
    "chargedoffPrincipalAmount", "recoveredAmount", "repossessedProceedsAmount", "originatorName",
    "originationDate", "originalLoanAmount", "originalLoanTerm", "loanMaturityDate",
    "originalInterestRatePercentage", "interestCalculationTypeCode", "originalInterestRateTypeCode",
    "originalFirstPaymentDate", "underwritingIndicator", "gracePeriodNumber", "paymentTypeCode",
    "subvented", "vehicleManufacturerName", "vehicleModelName", "vehicleNewUsedCode",
    "vehicleModelYear", "vehicleTypeCode", "vehicleValueAmount", "vehicleValueSourceCode",
    "obligorCreditScoreType", "obligorCreditScore", "obligorIncomeVerificationLevelCode",
    "obligorEmploymentVerificationCode", "coObligorIndicator", "paymentToIncomePercentage",
    "obligorGeographicLocation", "assetAddedIndicator", "remainingTermToMaturityNumber",
    "reportingPeriodModificationIndicator", "servicingAdvanceMethodCode",
    "reportingPeriodBeginningLoanBalanceAmount", "nextReportingPeriodPaymentAmountDue",
    "reportingPeriodInterestRatePercentage", "nextInterestRatePercentage", "servicingFeePercentage",
    "otherAssessedUncollectedServicerFeeAmount", "scheduledInterestAmount", "scheduledPrincipalAmount",
    "otherPrincipalAdjustmentAmount", "reportingPeriodActualEndBalanceAmount",
    "reportingPeriodScheduledPaymentAmount", "totalActualAmountPaid", "actualInterestCollectedAmount",
    "actualPrincipalCollectedAmount", "actualOtherCollectedAmount", "interestPaidThroughDate",
    "currentDelinquencyStatus", "primaryLoanServicerName", "assetSubjectDemandIndicator",
    "repossessedIndicator", "servicerAdvancedAmount", "otherServicerFeeRetainedByServicer",
    "originalInterestOnlyTermNumber",
]

# Fields kept as text even when they look numeric
TEXT_FIELDS = {
    "assetTypeNumber", "assetNumber", "originatorName", "vehicleManufacturerName",
    "vehicleModelName", "obligorCreditScoreType", "obligorGeographicLocation",
    "primaryLoanServicerName",
}

BALANCE_FIELD = "reportingPeriodBeginningLoanBalanceAmount"


def http_get(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    time.sleep(0.2)
    return urllib.request.urlopen(req)


def local_name(tag):
    return tag.rsplit("}", 1)[-1]


def find_ex102(cik, accession):
    base = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession.replace('-', '')}"
    with http_get(f"{base}/index.json") as resp:
        items = json.load(resp)["directory"]["item"]
    xmls = [i for i in items if i["name"].lower().endswith(".xml") and not i["name"].lower().startswith("exhibit103")]
    if not xmls:
        raise RuntimeError(f"No EX-102 XML found in {base}")
    best = max(xmls, key=lambda i: int(i.get("size") or 0))
    return f"{base}/{best['name']}", f"{base}/{accession}-index.htm"


def download(url, dest):
    if dest.exists() and dest.stat().st_size > 0:
        print(f"  using cached {dest.name}")
        return
    tmp = dest.with_suffix(".part")
    with http_get(url) as resp, open(tmp, "wb") as f:
        while chunk := resp.read(1 << 20):
            f.write(chunk)
    tmp.replace(dest)
    print(f"  downloaded {dest.name} ({dest.stat().st_size / 1e6:.0f} MB)")


def convert(field, value):
    if value is None or value == "" or field in TEXT_FIELDS:
        return value
    try:
        num = float(value)
    except ValueError:
        return value
    return int(num) if num.is_integer() and "." not in value else num


def parse_loans(path):
    for _, elem in ET.iterparse(path, events=("end",)):
        if local_name(elem.tag) != "assets":
            continue
        yield {local_name(child.tag): (child.text or "").strip() for child in elem}
        elem.clear()


def write_workbook(trust, cik, accession, filing_date, period, xml_path, index_url, dest):
    wb = xlsxwriter.Workbook(dest, {"constant_memory": True, "strings_to_numbers": False})
    bold = wb.add_format({"bold": True})
    loans_ws = wb.add_worksheet("Loans")
    info_ws = wb.add_worksheet("Info")

    columns = list(COLUMNS)
    rows = 0
    balance = 0.0
    loans = parse_loans(xml_path)
    first = next(loans, None)
    if first is None:
        raise RuntimeError(f"No loans parsed from {xml_path}")
    columns += [k for k in first if k not in columns]  # append any unexpected tags
    loans_ws.write_row(0, 0, columns, bold)

    for loan in _chain(first, loans):
        extra = [k for k in loan if k not in columns]
        if extra:
            raise RuntimeError(f"Unexpected tags after header written: {extra}")
        rows += 1
        loans_ws.write_row(rows, 0, [convert(c, loan.get(c)) for c in columns])
        bal = convert(BALANCE_FIELD, loan.get(BALANCE_FIELD))
        if isinstance(bal, (int, float)):
            balance += bal

    loans_ws.freeze_panes(1, 0)
    loans_ws.autofilter(0, 0, rows, len(columns) - 1)

    info = [
        ("Trust", trust), ("CIK", cik), ("Accession", accession), ("Filing date", filing_date),
        ("Reporting period end", period), ("EDGAR filing", index_url), ("Loan count", rows),
        ("Total beginning balance", round(balance, 2)),
        ("Generated", datetime.now().strftime("%Y-%m-%d %H:%M")),
    ]
    for r, (k, v) in enumerate(info):
        info_ws.write(r, 0, k, bold)
        info_ws.write(r, 1, v)
    info_ws.set_column(0, 0, 24)
    info_ws.set_column(1, 1, 90)
    wb.close()
    return rows, balance


def _chain(first, rest):
    yield first
    yield from rest


def main():
    RAW_DIR.mkdir(exist_ok=True)
    OUT_DIR.mkdir(exist_ok=True)
    for trust, cik, accession, filing_date, period in TRUSTS:
        print(f"{trust} ({period})")
        xml_url, index_url = find_ex102(cik, accession)
        slug = trust.lower().replace(" ", "_")
        xml_path = RAW_DIR / f"{slug}_{period}.xml"
        download(xml_url, xml_path)
        dest = OUT_DIR / f"{trust} - {period}.xlsx"
        rows, balance = write_workbook(trust, cik, accession, filing_date, period, xml_path, index_url, dest)
        print(f"  wrote {dest.name}: {rows:,} loans, beginning balance ${balance:,.2f}")


if __name__ == "__main__":
    main()
