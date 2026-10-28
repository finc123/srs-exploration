"""Cumulative pre-order penetration of explicit console owners: GTA VI vs Battlefield 6 (NIQ Slice, 6_12_12 active panel).

For each game, base = active-panel mailboxes that joined before the game's pre-order open and have an explicit
PS5 / Xbox Series X|S console purchase dated before it. Numerator = first console base-game order per mailbox (gross;
cancellations not netted). PC purchases (Steam, EA app, Epic) are excluded.
Day 0 = pre-order open (GTA VI 25 Jun 2026, BF6 31 Jul 2025). Orders dated the day before open count as day 0
(midnight-ET orders carry the user-local date).
Run from gta/penetration:  python gta6_penetration.py
"""
import json
import pandas as pd

C = "../.cache/"
SEN, MSS = "Sony Entertainment Network", "Microsoft store"
GAMES = {
    "GTA6": {"open": "2026-06-25", "launch": "2026-11-19", "last": "2026-10-26", "rows": "gta6.parquet"},   # 27 Oct partial
    "BF6": {"open": "2025-07-31", "launch": "2025-10-10", "last": "2025-11-30", "rows": "bf6.parquet"},
}
BF6_EXCLUDE = r"BETA|PACK|BFC|ADD-ON|TEXTURE|SHARED DATA|SINGLE PLAYER|MULTIPLAYER|MARKER|PRO -|BUNDLE|UPGRADE|SEASON"
PC_STORES = ["Steam", "Origin", "Epic Games", "Google Play"]
HI_SPEND = 250   # high-spender cohort threshold, USD in the 12 months before pre-order open

# explicit console rows (same rules as console_owners.py: description flags + row-level price check)
d = pd.read_parquet(C + "desc_cls.parquet")[["MERCHANT_NAME", "H", "EXPLICIT_PS5", "EXPLICIT_XSX"]]
r = pd.read_parquet(C + "rows.parquet", columns=["MAILBOX_ID", "MERCHANT_NAME", "H", "ORDER_DATE", "ITEM_PRICE"])
r = r.merge(d, on=["MERCHANT_NAME", "H"], how="inner")
r = r[r["EXPLICIT_PS5"] | r["EXPLICIT_XSX"]]
p = r["ITEM_PRICE"]
r = r[p.isna() | p.eq(0) | p.between(150, 2000)]
r["ORDER_DATE"] = pd.to_datetime(r["ORDER_DATE"])

mb = pd.read_parquet(C + "mailboxes.parquet")
mb["ENTRY_DATE"] = pd.to_datetime(mb["ENTRY_DATE"])
mb = mb[mb["IN_PANEL_61212"] == 1]


def platform(df):
    u = df["DESCRIPTION"].str.upper()
    plat = pd.Series(None, index=df.index, dtype=object)
    plat[u.str.contains("XBOX|SERIES X")] = "XSX"
    plat[u.str.contains("PS5|PLAYSTATION")] = "PS5"
    plat[df["MERCHANT_NAME"] == SEN] = "PS5"
    plat[df["MERCHANT_NAME"] == MSS] = "XSX"
    return plat


def buyers(game, cfg):
    g = pd.read_parquet(C + cfg["rows"])
    if game == "BF6":
        g = g[~g["DESCRIPTION"].str.upper().str.contains(BF6_EXCLUDE) & ~g["MERCHANT_NAME"].isin(PC_STORES)
              & (g["ITEM_PRICE"].isna() | g["ITEM_PRICE"].between(40, 130))]
    g = g.assign(ORDER_DATE=pd.to_datetime(g["ORDER_DATE"]), PLAT=platform(g))
    g = g[g["PLAT"].notna() & (g["ORDER_DATE"] <= pd.Timestamp(cfg["last"]))]
    g["DAY"] = (g["ORDER_DATE"] - pd.Timestamp(cfg["open"])).dt.days.clip(lower=0)
    return g


out = {"games": {}}
for game, cfg in GAMES.items():
    open_ = pd.Timestamp(cfg["open"])
    pre = r[r["ORDER_DATE"] < open_ - pd.Timedelta(days=1)]
    joined = set(mb.loc[mb["ENTRY_DATE"] < open_, "MAILBOX_ID"])
    bases = {"PS5": set(pre.loc[pre["EXPLICIT_PS5"], "MAILBOX_ID"]) & joined,
             "XSX": set(pre.loc[pre["EXPLICIT_XSX"], "MAILBOX_ID"]) & joined}
    bases["ANY"] = bases["PS5"] | bases["XSX"]
    # high spenders: $250+ PSN + MS Store gaming spend in the 12 months before open (features from inv3_spend_cohorts.py)
    feat = pd.read_parquet(f"inv3_out/features_{game}.parquet")
    bases["HI"] = bases["ANY"] & set(feat.index[feat["USD_STORE"] >= HI_SPEND])
    # zero spenders: no paid PSN + MS Store gaming spend in the same window (incl. owners with no store row at all)
    bases["ZERO"] = bases["ANY"] & set(feat.index[feat["USD_STORE"].fillna(0) == 0])
    bases["NOTHI"] = bases["ANY"] - bases["HI"]   # everyone below $250, incl. $0
    g = buyers(game, cfg)
    last_day = (pd.Timestamp(cfg["last"]) - open_).days
    gd = {"open": cfg["open"], "launch_day": (pd.Timestamp(cfg["launch"]) - open_).days, "last_day": last_day,
          "last_date": cfg["last"], "series": {}}
    for key, base in bases.items():
        rows = g if key in ("ANY", "HI", "ZERO", "NOTHI") else g[g["PLAT"] == key]
        first = rows.groupby("MAILBOX_ID")["DAY"].min().reindex(list(base)).dropna()
        cnt = first.value_counts().reindex(range(last_day + 1), fill_value=0).cumsum()
        gd["series"][key] = {"base": len(base), "buyers": int(len(first)),
                             "cum_pct": [round(100 * v / len(base), 4) for v in cnt]}
        print(f"{game} {key}: base {len(base):,}  buyers {len(first):,}  day0 {100*cnt[0]/len(base):.2f}%  "
              f"launch {100*cnt[min(gd['launch_day'], last_day)]/len(base):.2f}%  latest {100*cnt.iloc[-1]/len(base):.2f}%")
    out["games"][game] = gd
json.dump(out, open("gta6_penetration.json", "w"))
