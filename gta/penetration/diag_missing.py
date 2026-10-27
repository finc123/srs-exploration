"""Diagnostics: is explicit-owner GTA VI penetration diluted by owners whose console-store receipts we can't see?"""
import pandas as pd
O = pd.Timestamp("2026-06-24"); LAST = pd.Timestamp("2026-10-26")
SEN, MSS = "Sony Entertainment Network", "Microsoft store"
mb = pd.read_parquet("mb_console_flags.parquet")
mb = mb[(mb.IN_PANEL_61212 == 1) & (mb.ENTRY_DATE < pd.Timestamp("2026-06-25"))]
g = pd.read_parquet("gta6.parquet"); g["ORDER_DATE"] = pd.to_datetime(g.ORDER_DATE); g = g[g.ORDER_DATE <= LAST]
buyers = set(g.MAILBOX_ID)
r = pd.read_parquet("rows.parquet", columns=["MAILBOX_ID", "MERCHANT_NAME", "ORDER_DATE"]); r["ORDER_DATE"] = pd.to_datetime(r.ORDER_DATE)
s = pd.read_parquet("store_mb.parquet"); s["FIRST_DATE"] = pd.to_datetime(s.FIRST_DATE); s["LAST_DATE"] = pd.to_datetime(s.LAST_DATE)
pre_store = s[s.FIRST_DATE < O]
ps_any = set(pre_store.loc[pre_store.MERCHANT_NAME == SEN, "MAILBOX_ID"]); ms_any = set(pre_store.loc[pre_store.MERCHANT_NAME == MSS, "MAILBOX_ID"])
# store rows in the 12 months before pre-orders, from row-level candidate rows (console-related items only)
rr = r[(r.ORDER_DATE < O) & (r.ORDER_DATE >= O - pd.DateOffset(years=1))]
ps_12 = set(rr.loc[rr.MERCHANT_NAME == SEN, "MAILBOX_ID"]); ms_12 = set(rr.loc[rr.MERCHANT_NAME == MSS, "MAILBOX_ID"])
act = pd.read_parquet("mb_activity.parquet").set_index("MAILBOX_ID")

def pen(ids, lbl):
    ids = pd.Index(ids); n = len(ids); b = ids.isin(list(buyers)).sum()
    print(f"{lbl:<62} n={n:>8,}  buyers={b:>6,}  pen={100*b/max(n,1):5.2f}%")

A = mb.index[mb.EXP_PS5_PRE | mb.EXP_XSX_PRE]; APS = mb.index[mb.EXP_PS5_PRE]; AXB = mb.index[mb.EXP_XSX_PRE]
B = mb.index[mb.EXP_PS5_PRE | mb.EXP_XSX_PRE | mb.INF_PS5_PRE | mb.INF_XSX_PRE]
print("== explicit owners split by console-store visibility (any PSN / MS Store receipt before 24 Jun 2026)")
pen(A, "Explicit, all")
vis = A[A.isin(list(ps_any | ms_any))]; pen(vis, "  with any PSN or MS Store receipt before pre-orders")
pen(A[~A.isin(list(ps_any | ms_any))], "  with no console-store receipt ever (pre)")
pen(APS[APS.isin(list(ps_any))], "Explicit PS5 owners with PSN receipts")
pen(APS[~APS.isin(list(ps_any))], "Explicit PS5 owners without PSN receipts")
pen(AXB[AXB.isin(list(ms_any))], "Explicit Xbox owners with MS Store receipts")
pen(AXB[~AXB.isin(list(ms_any))], "Explicit Xbox owners without MS Store receipts")
pen(A[A.isin(list(ps_12 | ms_12))], "Explicit, console-store item in prior 12 months (console-related items)")
pen(B[B.isin(list(ps_12 | ms_12))], "Explicit + inferred, same")
print("\n== share of GTA VI buyers (in panel base B) who bought at PSN/MS Store:",
      round(100 * g[g.MAILBOX_ID.isin(B)].groupby("MAILBOX_ID").MERCHANT_NAME.apply(lambda x: x.isin([SEN, MSS]).any()).mean(), 1), "%")
# explicit console purchase year
e = r.merge(pd.read_parquet("desc_cls.parquet")[["MERCHANT_NAME"]].head(0), how="left") if False else None
print("\n== explicit owners by receipt activity recency (last item any merchant)")
last = pd.to_datetime(act.LAST_ORDER).reindex(A)
pen(A[(last >= O).values], "Explicit, any receipt on/after 24 Jun 2026")
print("\n== panel overall store visibility")
P = mb.index
print("panel mailboxes with any PSN receipt pre:", f"{pd.Index(P).isin(list(ps_any)).mean()*100:.1f}%", " MS Store:", f"{pd.Index(P).isin(list(ms_any)).mean()*100:.1f}%")
