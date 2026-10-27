"""Console-owner flags for NIQ Slice mailboxes (GTA VI pre-order scaling base).

Inputs (pulled by the queries in console_owners.sql, cached in ../.cache/):
  desc.parquet         merchant x description aggregate of candidate rows (q_desc)
  rows.parquet         row-level candidate rows: mailbox, merchant, hash(description), date, price (q_rows)
  store_mb.parquet     mailbox-level PSN / Microsoft Store activity (q_store_mb)
  supra_mb.parquet     SUPRA google.com app-install / account-link emails for Xbox / PlayStation apps
  mailboxes.parquet    mailboxes_enhanced + 6_12_12 panel flag (q_mb)
  mb_activity.parquet  per-mailbox first/last item date (q_mb_activity)
  gta6.parquet         GTA VI base-game pre-order rows (filter from slice_items_gta6.md)
Run from the gta/.cache directory:  python ../notes/console_owners.py
"""
import sys
import pandas as pd

sys.path.insert(0, "../notes")
from console_owners_rules import classify, SEN, MSS  # noqa: E402

pd.set_option("display.width", 250)
pd.set_option("display.max_columns", 40)
pd.set_option("display.max_colwidth", 100)
GTA_START = pd.Timestamp("2026-06-24")
COHORT_CUT = pd.Timestamp("2020-06-01")

# ---------------------------------------------------------------- description rules -> rows
d = classify(pd.read_parquet("desc.parquet"))
d.to_parquet("desc_cls.parquet")
FLAGS = ["EXPLICIT_PS5", "EXPLICIT_XSX", "INF_PS5", "INF_XSX", "INF_PS5_XGEN", "INF_XSX_XGEN",
         "INF_PS5_MULTI", "INF_XSX_MULTI", "AGN_PS", "AGN_XB", "AGN_MULTI", "SEN_FREE", "IS_GTA6",
         "IS_MARKETPLACE"]
r = pd.read_parquet("rows.parquet")
r["ORDER_DATE"] = pd.to_datetime(r["ORDER_DATE"])
r = r.merge(d[["MERCHANT_NAME", "H"] + FLAGS], on=["MERCHANT_NAME", "H"], how="inner")
# row-level price check for explicit consoles (description-level median already checked)
p = r["ITEM_PRICE"]
row_price_ok = p.isna() | p.eq(0) | p.between(150, 2000)
for f in ["EXPLICIT_PS5", "EXPLICIT_XSX"]:
    r[f] &= row_price_ok
r["PRE_GTA"] = r["ORDER_DATE"] < GTA_START          # for the recall check (excludes GTA VI-era rows)


def mb_flags(rows: pd.DataFrame, suffix: str = "") -> pd.DataFrame:
    g = rows.groupby("MAILBOX_ID")
    out = pd.DataFrame({
        "EXP_PS5": g["EXPLICIT_PS5"].any(),
        "EXP_XSX": g["EXPLICIT_XSX"].any(),
        "INF_PS5": g["INF_PS5"].any(),
        "INF_XSX": g["INF_XSX"].any(),
        "INF_PS5_XGEN": g["INF_PS5_XGEN"].any(),
        "INF_XSX_XGEN": g["INF_XSX_XGEN"].any(),
        "INF_PS5_MULTI": g["INF_PS5_MULTI"].any(),
        "INF_XSX_MULTI": g["INF_XSX_MULTI"].any(),
        "AGN_PS_TXT": g["AGN_PS"].any(),
        "AGN_XB_TXT": g["AGN_XB"].any(),
    })
    # inferred PS5 excluding $0 PSN claims (PS Plus monthly games can be claimed without a PS5)
    paid = rows[rows["INF_PS5"] & ~rows["SEN_FREE"]]
    out["INF_PS5_PAID"] = out.index.isin(paid["MAILBOX_ID"].unique())
    # model-agnostic excluding generic multi-platform accessories (headsets etc.)
    nm = rows[(rows["AGN_PS"] | rows["AGN_XB"]) & ~rows["AGN_MULTI"]]
    out["AGN_PS_NOMULTI"] = out.index.isin(nm.loc[nm["AGN_PS"], "MAILBOX_ID"].unique())
    out["AGN_XB_NOMULTI"] = out.index.isin(nm.loc[nm["AGN_XB"], "MAILBOX_ID"].unique())
    return out.add_suffix(suffix)


F = mb_flags(r)
F_pre = mb_flags(r[r["PRE_GTA"] & ~r["IS_GTA6"]], "_PRE")

# ---------------------------------------------------------------- mailbox base
mb = pd.read_parquet("mailboxes.parquet").set_index("MAILBOX_ID")
mb["ENTRY_DATE"] = pd.to_datetime(mb["ENTRY_DATE"])
act = pd.read_parquet("mb_activity.parquet").set_index("MAILBOX_ID")
mb["HAS_ITEMS"] = mb.index.isin(act.index)
LAUNCH = pd.Timestamp("2020-11-12")
mb["RECEIPTS_POST_LAUNCH"] = mb.index.isin(act.index[pd.to_datetime(act["LAST_ORDER"]) >= LAUNCH])
mb = mb.join(F).join(F_pre)
for c in list(F.columns) + list(F_pre.columns):
    mb[c] = mb[c].astype("boolean").fillna(False).astype(bool)

store = pd.read_parquet("store_mb.parquet")
store["FIRST_DATE"] = pd.to_datetime(store["FIRST_DATE"])
sen = store[store["MERCHANT_NAME"] == SEN]
mb["SEN_ANY"] = mb.index.isin(sen["MAILBOX_ID"])
mb["SEN_ANY_PRE"] = mb.index.isin(sen.loc[sen["FIRST_DATE"] < GTA_START, "MAILBOX_ID"])
mb["SEN_POST_PS5"] = mb.index.isin(sen.loc[sen["N_ROWS_POST_PS5"] > 0, "MAILBOX_ID"])

supra = pd.read_parquet("supra_mb.parquet").merge(
    pd.read_parquet("supra_subj.parquet")[["SUBJECT_ID", "SUBJECT"]], on="SUBJECT_ID")
supra["PS"] = supra["SUBJECT"].str.contains("PlayStation", case=False)
supra["XB"] = supra["SUBJECT"].str.contains("Xbox", case=False)
mb["SUPRA_PS"] = mb.index.isin(supra.loc[supra["PS"], "MAILBOX_ID"])
mb["SUPRA_XB"] = mb.index.isin(supra.loc[supra["XB"], "MAILBOX_ID"])

# ---------------------------------------------------------------- headline groups
mb["A_PS5"] = mb["EXP_PS5"]
mb["A_XSX"] = mb["EXP_XSX"]
mb["A_ANY"] = mb["A_PS5"] | mb["A_XSX"]
mb["B_PS5"] = mb["A_PS5"] | mb["INF_PS5"]
mb["B_XSX"] = mb["A_XSX"] | mb["INF_XSX"]
mb["B_ANY"] = mb["B_PS5"] | mb["B_XSX"]
mb["B_ANY_XGEN"] = mb["B_ANY"] | mb["INF_PS5_XGEN"] | mb["INF_XSX_XGEN"]
mb["B_ANY_XGEN_MULTI"] = mb["B_ANY_XGEN"] | mb["INF_PS5_MULTI"] | mb["INF_XSX_MULTI"]
mb["B_ANY_PAIDPSN"] = mb["A_ANY"] | mb["INF_PS5_PAID"] | mb["INF_XSX"]
mb["C_PS"] = mb["AGN_PS_TXT"] | mb["SEN_ANY"] | mb["A_PS5"] | mb["B_PS5"]
mb["C_XB"] = mb["AGN_XB_TXT"] | mb["A_XSX"] | mb["B_XSX"]
mb["C_ANY"] = mb["C_PS"] | mb["C_XB"]
mb["C_ANY_NOMULTI"] = (mb["AGN_PS_NOMULTI"] | mb["AGN_XB_NOMULTI"] | mb["SEN_ANY"] | mb["B_ANY"])
mb["C_ANY_SUPRA"] = mb["C_ANY"] | mb["SUPRA_PS"] | mb["SUPRA_XB"]
# recall-check versions: only evidence dated before GTA VI pre-orders opened (and never the GTA VI row itself)
mb["A_ANY_PRE"] = mb["EXP_PS5_PRE"] | mb["EXP_XSX_PRE"]
mb["B_ANY_PRE"] = mb["A_ANY_PRE"] | mb["INF_PS5_PRE"] | mb["INF_XSX_PRE"]
mb["B_ANY_XGEN_PRE"] = mb["B_ANY_PRE"] | mb["INF_PS5_XGEN_PRE"] | mb["INF_XSX_XGEN_PRE"]
mb["C_ANY_PRE"] = mb["B_ANY_XGEN_PRE"] | mb["AGN_PS_TXT_PRE"] | mb["AGN_XB_TXT_PRE"] | mb["SEN_ANY_PRE"]
mb.to_parquet("mb_console_flags.parquet")

ROWS = [
    ("(a) Explicit PS5 or Series X|S console purchase", "A_ANY"),
    ("    PS5 console", "A_PS5"),
    ("    Xbox Series X|S console", "A_XSX"),
    ("    PS5 only", "A_PS5_ONLY"),
    ("    Xbox Series only", "A_XSX_ONLY"),
    ("    both", "A_BOTH"),
    ("(b) Explicit + inferred current-gen (strict)", "B_ANY"),
    ("    PS5 (explicit or inferred)", "B_PS5"),
    ("    Series X|S (explicit or inferred)", "B_XSX"),
    ("    sens: + cross-gen titles ('PS4 & PS5')", "B_ANY_XGEN"),
    ("    sens: + cross-gen + multi-platform accessories", "B_ANY_XGEN_MULTI"),
    ("    sens: strict but excl. $0 PSN claims", "B_ANY_PAIDPSN"),
    ("(c) Model-agnostic PlayStation or Xbox", "C_ANY"),
    ("    PlayStation (any gen / PSN / PS Plus)", "C_PS"),
    ("    Xbox (any gen / Game Pass / Live)", "C_XB"),
    ("    sens: excl. multi-platform accessories", "C_ANY_NOMULTI"),
    ("    sens: + SUPRA app-install/account-link emails", "C_ANY_SUPRA"),
]
mb["A_PS5_ONLY"] = mb["A_PS5"] & ~mb["A_XSX"]
mb["A_XSX_ONLY"] = mb["A_XSX"] & ~mb["A_PS5"]
mb["A_BOTH"] = mb["A_PS5"] & mb["A_XSX"]


def table(base: pd.DataFrame) -> pd.DataFrame:
    bases = {
        "All mailboxes": base,
        "Receipts since PS5 launch (Nov-2020)": base[base["RECEIPTS_POST_LAUNCH"]],
        "Active 6_12_12 panel": base[base["IN_PANEL_61212"] == 1],
    }
    out = []
    for label, col in ROWS:
        row = {"group": label}
        for bl, b in bases.items():
            n = int(b[col].sum())
            row[f"{bl} n"] = n
            row[f"{bl} %"] = round(100 * n / len(b), 2)
        out.append(row)
    den = {"group": "Denominator (mailboxes)"}
    for bl, b in bases.items():
        den[f"{bl} n"] = len(b)
        den[f"{bl} %"] = 100.0
    return pd.DataFrame(out + [den])


if __name__ == "__main__":
    full = table(mb)
    pre = table(mb[mb["ENTRY_DATE"] < COHORT_CUT])
    full.to_csv("../notes/console_owners_all.csv", index=False)
    pre.to_csv("../notes/console_owners_pre2020.csv", index=False)
    print("ALL MAILBOXES\n", full.to_string(index=False))
    print("\nJOINED BEFORE 2020-06-01\n", pre.to_string(index=False))

    # -------- sanity 1: explicit console purchases by year (first explicit purchase per mailbox)
    e = r[r["EXPLICIT_PS5"] | r["EXPLICIT_XSX"]].copy()
    e["Y"] = e["ORDER_DATE"].dt.year
    e["PLAT"] = e["EXPLICIT_PS5"].map({True: "PS5", False: "XSX"})
    by_year = e.groupby(["Y", "PLAT"])["MAILBOX_ID"].nunique().unstack(fill_value=0)
    first = e.sort_values("ORDER_DATE").drop_duplicates(["MAILBOX_ID", "PLAT"])
    by_year_first = first.groupby(["Y", "PLAT"]).size().unstack(fill_value=0)
    rows_y = e.groupby(["Y", "PLAT"]).size().unstack(fill_value=0)
    print("\nexplicit console rows by year\n", rows_y)
    print("\nmailboxes buying a console, by year\n", by_year)
    print("\nfirst explicit console purchase per mailbox, by year\n", by_year_first)
    e["MKT"] = e["IS_MARKETPLACE"]
    print("\nmarketplace share of explicit rows", round(e["MKT"].mean() * 100, 1))
    # panel size by year (distinct mailboxes with any item row; from q_items_by_year in console_owners.sql)
    active_y = pd.Series({2020: 3545001, 2021: 3585855, 2022: 3790073, 2023: 3852529, 2024: 3596047,
                          2025: 3077290, 2026: 2457326})
    per100k = (by_year.loc[2020:].div(active_y, axis=0) * 1e5).round(0)
    per100k["PS5 share %"] = (100 * by_year["PS5"] / by_year.sum(axis=1)).round(1)
    print("\nconsole-buying mailboxes per 100k receipt-active mailboxes\n", per100k)
    pd.concat({"rows": rows_y, "mailboxes": by_year, "first_purchase": by_year_first,
               "per100k_active": per100k}, axis=1).to_csv(
        "../notes/console_owners_by_year.csv")

    # -------- sanity 2: top descriptions per rule
    tops = []
    for f in ["EXPLICIT_PS5", "EXPLICIT_XSX", "INF_PS5", "INF_XSX", "INF_PS5_XGEN", "INF_XSX_XGEN", "AGN_PS", "AGN_XB"]:
        x = d[d[f]].nlargest(15, "N_MB")[["MERCHANT_NAME", "DESCRIPTION", "N_ROWS", "N_MB", "MED_PRICE"]]
        x.insert(0, "RULE", f)
        tops.append(x)
    pd.concat(tops).to_csv("../notes/console_owners_top_descriptions.csv", index=False)
    # merchant mix of explicit console rows
    mm = e.groupby("MERCHANT_NAME").agg(rows=("H", "size"), mailboxes=("MAILBOX_ID", "nunique"),
                                        med_price=("ITEM_PRICE", "median")).nlargest(20, "rows")
    print("\nexplicit console rows by merchant\n", mm)

    # -------- sanity 3: recall on GTA VI pre-orderers
    g = pd.read_parquet("gta6.parquet")
    g["PLAT"] = "Retail"
    g.loc[g["MERCHANT_NAME"] == SEN, "PLAT"] = "PSN (PS5 by definition)"
    g.loc[g["MERCHANT_NAME"] == MSS, "PLAT"] = "MS Store (Series X|S by definition)"
    rec = []
    for plat, gg in [("All GTA VI pre-orderers", g)] + list(g.groupby("PLAT")):
        ids = gg["MAILBOX_ID"].unique()
        x = mb.reindex(ids)
        x = x[x.index.isin(mb.index)]
        row = {"segment": plat, "mailboxes": len(ids), "in mailboxes_enhanced": len(x)}
        for lbl, col in [("(a) explicit", "A_ANY_PRE"), ("(b) +inferred strict", "B_ANY_PRE"),
                         ("(b) +cross-gen", "B_ANY_XGEN_PRE"), ("(c) model-agnostic", "C_ANY_PRE"),
                         ("(a) explicit incl. post-Jun-24", "A_ANY"), ("(b) strict incl. GTA-era", "B_ANY")]:
            row[lbl] = round(100 * x[col].mean(), 1)
        rec.append(row)
    rec = pd.DataFrame(rec)
    rec.to_csv("../notes/console_owners_gta_recall.csv", index=False)
    print("\nGTA VI pre-orderer recall (% of pre-orderers already flagged)\n", rec.to_string(index=False))
    panel_rec = mb.reindex(g["MAILBOX_ID"].unique()).dropna(subset=["ENTRY_DATE"])
    panel_rec = panel_rec[panel_rec["IN_PANEL_61212"] == 1]
    print("\nrecall within 6_12_12 panel pre-orderers (n=%d):" % len(panel_rec),
          {c: round(100 * panel_rec[c].mean(), 1) for c in ["A_ANY_PRE", "B_ANY_PRE", "B_ANY_XGEN_PRE", "C_ANY_PRE"]})
