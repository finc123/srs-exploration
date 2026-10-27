"""BF6 vs GTA VI pre-order penetration of console owners (same panel + base rules, each anchored on its own pre-order open).

BF6: pre-orders 31 Jul 2025, launch 10 Oct 2025. GTA VI: pre-orders 25 Jun 2026, launch 19 Nov 2026.
Base = 6_12_12 panel, joined before the game's pre-order open, explicit/inferred console evidence dated before it.
Buyers = first console base-game purchase (PSN, MS Store, retail PS5/Xbox SKU); PC (Steam/EA app/Epic) excluded.
Run from gta/.cache:  python ../penetration/bf6_vs_gta6.py
"""
import sys
import pandas as pd

sys.path.insert(0, "../notes")
SEN, MSS = "Sony Entertainment Network", "Microsoft store"
GAMES = {"BF6": (pd.Timestamp("2025-07-31"), pd.Timestamp("2025-10-10")),
         "GTA6": (pd.Timestamp("2026-06-25"), pd.Timestamp("2026-11-19"))}

d = pd.read_parquet("desc_cls.parquet")[["MERCHANT_NAME", "H", "EXPLICIT_PS5", "EXPLICIT_XSX", "INF_PS5", "INF_XSX", "IS_GTA6"]]
r = pd.read_parquet("rows.parquet")
r["ORDER_DATE"] = pd.to_datetime(r["ORDER_DATE"])
r = r.merge(d, on=["MERCHANT_NAME", "H"], how="inner")
p = r["ITEM_PRICE"]
ok = p.isna() | p.eq(0) | p.between(150, 2000)
r["EXPLICIT_PS5"] &= ok
r["EXPLICIT_XSX"] &= ok
store = pd.read_parquet("store_mb.parquet")
store["FIRST_DATE"] = pd.to_datetime(store["FIRST_DATE"])
mb = pd.read_parquet("mailboxes.parquet")
mb["ENTRY_DATE"] = pd.to_datetime(mb["ENTRY_DATE"])
mb = mb[mb["IN_PANEL_61212"] == 1].set_index("MAILBOX_ID")


def platform(df):
    u = df["DESCRIPTION"].str.upper()
    plat = pd.Series(None, index=df.index, dtype=object)
    plat[u.str.contains("XBOX|SERIES X")] = "XSX"
    plat[u.str.contains("PS5|PLAYSTATION")] = "PS5"
    plat[df["MERCHANT_NAME"] == SEN] = "PS5"
    plat[df["MERCHANT_NAME"] == MSS] = "XSX"
    return plat


bf = pd.read_parquet("bf6.parquet")
u = bf["DESCRIPTION"].str.upper()
bf = bf[~u.str.contains(r"BETA|PACK|BFC|ADD-ON|TEXTURE|SHARED DATA|SINGLE PLAYER|MULTIPLAYER|MARKER|PRO -|BUNDLE|UPGRADE|SEASON")
        & ~bf["MERCHANT_NAME"].isin(["Steam", "Origin", "Epic Games", "Google Play"])
        & (bf["ITEM_PRICE"].isna() | bf["ITEM_PRICE"].between(40, 130))].copy()
bf["PLAT"] = platform(bf)
gt = pd.read_parquet("gta6.parquet")
gt["PLAT"] = platform(gt)
buys = {"BF6": bf, "GTA6": gt}

res = {}
for game, (open_, launch) in GAMES.items():
    pre = r[(r["ORDER_DATE"] < open_ - pd.Timedelta(days=1)) & ~r["IS_GTA6"]]
    ids = lambda col: set(pre.loc[pre[col], "MAILBOX_ID"])
    E = ids("EXPLICIT_PS5") | ids("EXPLICIT_XSX")
    B = E | ids("INF_PS5") | ids("INF_XSX")
    vis = set(store.loc[store["FIRST_DATE"] < open_ - pd.Timedelta(days=1), "MAILBOX_ID"])
    joined = set(mb.index[mb["ENTRY_DATE"] < open_])
    g = buys[game].copy()
    g["ORDER_DATE"] = pd.to_datetime(g["ORDER_DATE"])
    g = g[g["PLAT"].notna()]
    g["DTL"] = (g["ORDER_DATE"] - launch).dt.days          # days to launch (negative before)
    g["DSO"] = (g["ORDER_DATE"] - open_).dt.days.clip(lower=0)
    first = g.groupby("MAILBOX_ID")[["DTL", "DSO"]].min()
    for bname, base in {"E": E, "E+I": B, "E+I store-visible": B & vis}.items():
        base = base & joined
        f = first.reindex(list(base)).dropna()
        res[(game, bname)] = (len(base), f)
    print(game, "console buyers:", g["MAILBOX_ID"].nunique(), "| platform mix:", g.drop_duplicates("MAILBOX_ID")["PLAT"].value_counts(normalize=True).round(2).to_dict(),
          "| merchant mix:", g["MERCHANT_NAME"].value_counts(normalize=True).head(4).round(2).to_dict())

print("\nBF6 PC share of base-game buyers (all platforms):")
allbf = pd.read_parquet("bf6.parquet")
ua = allbf["DESCRIPTION"].str.upper()
allbf = allbf[~ua.str.contains(r"BETA|PACK|BFC|ADD-ON|TEXTURE|SHARED DATA|SINGLE PLAYER|MULTIPLAYER|MARKER|PRO -|BUNDLE|UPGRADE|SEASON")
              & (allbf["ITEM_PRICE"].isna() | allbf["ITEM_PRICE"].between(40, 130))]
pc = allbf["MERCHANT_NAME"].isin(["Steam", "Origin", "Epic Games"])
print(f"  PC {allbf.loc[pc,'MAILBOX_ID'].nunique():,} vs console {allbf.loc[~pc,'MAILBOX_ID'].nunique():,} mailboxes")

rows = []
for (game, bname), (n, f) in res.items():
    row = {"game": game, "base": bname, "n": n}
    for lbl, col, k in [("open+0", "DSO", 0), ("open+30", "DSO", 30), ("L-60", "DTL", -60), ("L-30", "DTL", -30),
                        ("L-23", "DTL", -23), ("L-0", "DTL", 0), ("L+10", "DTL", 10), ("L+30", "DTL", 30)]:
        row[lbl] = round(100 * (f[col] <= k).sum() / n, 2)
    rows.append(row)
out = pd.DataFrame(rows)
print("\ncumulative % of console-owner base (GTA6 L-23 = 27 Oct, latest; later GTA cells not yet observable)\n", out.to_string(index=False))
out.to_csv("../penetration/bf6_vs_gta6.csv", index=False)
