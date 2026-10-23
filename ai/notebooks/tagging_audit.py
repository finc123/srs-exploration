"""Brand-tagging audit of AI subscription payments in Omega 282 (2022 panel), transactions from 2025-01-01.

Pulls every panel transaction at a merchant whose descriptor matches the AI keyword list (keywords.py, plus Omega's
masked X Corp forms), with the brand ids Omega assigns in MID_MATCH_V1_0. The provider filters (filters/*.py) pick the
consumer plan payments; each is then labelled by tagging status:
  tagged        main brand = the provider's brand
  other_brand   a main brand, but a different one (e.g. GOOGLE PLAY)
  untagged      no main brand (payment / distribution brand may still be set)

Usage: python tagging_audit.py [--pull | --classify]   (default: report from the cached payments)
Outputs: .cache/card_core/audit_raw.parquet, audit_payments.parquet, ../docs/omega_282_ai_tagging_examples.xlsx
"""
import importlib
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from keywords import where_sql  # noqa: E402

CACHE = ROOT / ".cache" / "card_core"
OMEGA = "SHARE_CE_PRIME_ENRICHED_OMEGA_2822.PRIME_OMEGA"
GT = "SHARE_CE_PRIME_ENRICHED_OMEGA_2822.PRIME_GROUND_TRUTH"
START = "2025-01-01"
# provider -> (display name, expected main brand ids, filter module)
PROVIDERS = {
    "chatgpt": ("ChatGPT (OpenAI)", {27440}, "chatgpt"),
    "claude": ("Claude (Anthropic)", {29847}, "claude"),
    "gemini": ("Gemini (Google One)", {32111}, "gemini"),
    "perplexity": ("Perplexity", {29069}, "perplexity"),
    "muse": ("Muse (Meta)", {11021, 27954}, "muse"),
    "grok": ("Grok (xAI)", {32064}, "grok"),
    "grok_x": ("X Premium+ (X Corp)", {29913}, "grok"),  # X.COM (tags X Corp's Google Play billing)
}
MASKED_X = "(d.merchdesc ILIKE '%corp. paid%' OR d.merchdesc ILIKE '%corp paid%' OR d.merchdesc ILIKE '%corp. pa %')"


def pull():
    import snowflake.connector as sc
    cur = sc.connect(connection_name="default", warehouse="ANALYST_XL", network_timeout=7200).cursor()
    cur.execute("ALTER SESSION SET STATEMENT_TIMEOUT_IN_SECONDS = 7200")
    cur.execute(f"""
        WITH panel AS (
            SELECT cardlinkid FROM {OMEGA}.CARDLINK_PANEL_V1_0 p
            WHERE panel = 'aggregate_consistent_shopper_2022_v2'
              AND NOT EXISTS (SELECT 1 FROM {OMEGA}_STATIC.AFFECTED_ACCOUNTS_092026 a WHERE a.cardlinkid = p.cardlinkid)),
        mids AS (
            SELECT d.merchid, d.merchdesc, m.main_brand_id, m.payment_brand_id, m.distribution_brand_id
            FROM {OMEGA}.MID_V1_0 d LEFT JOIN {OMEGA}.MID_MATCH_V1_0 m ON m.merchid = d.merchid
            WHERE {where_sql('d.merchdesc')} OR {MASKED_X})
        SELECT t.transid, t.cardlinkid AS uid, t.trans_date AS dt, t.trans_amount AS amount, t.currency, t.transtype,
               c.merchid, c.merchdesc AS descr, c.main_brand_id, b.brand_name AS main_brand,
               c.payment_brand_id, pb.brand_name AS payment_brand, c.distribution_brand_id, db.brand_name AS distribution_brand
        FROM {OMEGA}.TRANS_V1_0 t
        JOIN mids c ON c.merchid = t.merchid
        JOIN panel p ON p.cardlinkid = t.cardlinkid
        LEFT JOIN {GT}.BRAND_V1_0 b ON b.brand_id = c.main_brand_id
        LEFT JOIN {GT}.BRAND_V1_0 pb ON pb.brand_id = c.payment_brand_id
        LEFT JOIN {GT}.BRAND_V1_0 db ON db.brand_id = c.distribution_brand_id
        WHERE t.filedate >= DATEADD(day, -7, '{START}'::DATE) AND t.trans_date >= '{START}'""")
    df = cur.fetch_pandas_all()
    df.columns = [c.lower() for c in df.columns]
    df["amount"] = df.amount.astype(float)
    df.to_parquet(CACHE / "audit_raw.parquet", index=False)
    return df


def classify(raw):
    out = []
    for mod in dict.fromkeys(m for _, _, m in PROVIDERS.values()):
        c = importlib.import_module(f"filters.{mod}").classify(raw, "omega")
        out.append(c[c.keep])
    c = pd.concat(out, ignore_index=True)
    c["dt"] = pd.to_datetime(c.dt)
    c["amount"] = c.amount.round(2)
    # back to the source row (transid + brand ids) on uid / date / amount / descriptor
    r = raw.assign(dt=pd.to_datetime(raw.dt), amount=raw.amount.round(2))
    m = c.merge(r, on=["uid", "dt", "amount", "descr"], how="left", suffixes=("", "_r")).drop_duplicates(
        ["uid", "dt", "amount", "descr", "provider"])
    exp = m.provider.map({k: v[1] for k, v in PROVIDERS.items()})
    m["status"] = [("tagged" if b in e else "other_brand") if pd.notna(b) else "untagged"
                   for b, e in zip(m.main_brand_id, exp)]
    m["provider_name"] = m.provider.map({k: v[0] for k, v in PROVIDERS.items()})
    return m


def family(d: str) -> str:
    """Descriptor with bank prefixes, phone numbers, states and reference codes stripped, for grouping."""
    import re
    d = re.sub(r"^(?:DC : PURCH|CC : CREDIT CARD PURCH|POINT OF SALE WITHDRAWAL \S+|POS\S*|CHECK|WITHDRAWAL|ACH WEB \S*)\s+", "",
               d.upper())
    d = re.sub(r"\b\d{4}\b.*$|\b(?:XXX-XXX-|855-|650-|888-|402-|G\.CO/HELPPA\S*|MOUNTAIN VIE\S*|SAN FRANCISC\S*)\b.*$", "", d)
    return re.sub(r"[ ,]+(?:CA|CAUS|US|TX|NY)?$", "", d).strip(" ,")


def report(m):
    m = m.copy()
    m["descriptor_family"] = m.descr.map(family)
    summ = (m.groupby(["provider_name", "status"]).agg(payments=("transid", "size"), members=("uid", "nunique"))
              .reset_index())
    summ["share_of_payments"] = summ.payments / summ.groupby("provider_name").payments.transform("sum")
    fam = (m.groupby(["provider_name", "status", "descriptor_family", "main_brand", "payment_brand"], dropna=False)
             .agg(payments=("transid", "size"), members=("uid", "nunique"), first=("dt", "min"), last=("dt", "max"),
                  median_amount=("amount", "median"), example_transid=("transid", "last"))
             .reset_index().sort_values(["provider_name", "status", "payments"], ascending=[True, False, False]))
    # up to 5 most recent examples per provider x status x descriptor family
    ex = (m[m.status != "tagged"].sort_values("dt", ascending=False)
            .groupby(["provider_name", "descriptor_family"]).head(5)
            [["provider_name", "status", "transid", "dt", "amount", "descr", "plan", "channel", "main_brand_id",
              "main_brand", "payment_brand_id", "payment_brand", "distribution_brand"]]
            .sort_values(["provider_name", "status", "descr", "dt"]))
    return summ, fam, ex


if __name__ == "__main__":
    raw = pull() if "--pull" in sys.argv or not (CACHE / "audit_raw.parquet").exists() else None
    if "--pull" in sys.argv or "--classify" in sys.argv or not (CACHE / "audit_payments.parquet").exists():
        m = classify(raw if raw is not None else pd.read_parquet(CACHE / "audit_raw.parquet"))
        m.to_parquet(CACHE / "audit_payments.parquet", index=False)
    else:
        m = pd.read_parquet(CACHE / "audit_payments.parquet")
    summ, fam, ex = report(m)
    with pd.ExcelWriter(ROOT / "docs" / "omega_282_ai_tagging_examples.xlsx") as xw:
        summ.to_excel(xw, sheet_name="summary", index=False)
        fam.to_excel(xw, sheet_name="by_descriptor", index=False)
        ex.assign(dt=ex.dt.dt.date).to_excel(xw, sheet_name="untagged_examples", index=False)
    pd.set_option("display.width", 250); pd.set_option("display.max_rows", 300); pd.set_option("display.max_colwidth", 55)
    print(summ.to_string(index=False))
    print(fam[fam.status != "tagged"].head(120).to_string(index=False))
