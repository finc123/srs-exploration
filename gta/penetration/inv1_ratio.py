"""inv1: why is our GTA VI / Battlefield 6 pre-order multiple (8.5x) so far above Yipit (3.7x B6) and M Science (3.2x MWII)?

Sections (each prints tables; the summary is in notes/inv1_gta_bf6_ratio.md):
  H1  channel: GTA/BF6 ratio by channel (PSN, MS Store, retail); digital-share trend for annual franchises;
      per-member PSN / MS Store receipt volume 2024-01..2026-10 (fixed cohort)
  H2  alignment: same days since open, same % of pre-order window, same days to launch
  H3  units vs penetration, PC, ownership requirement, active panel vs all mailboxes
  H4  base effects: base composition; fixed common cohort
  H5  own GTA VI vs MWII (pre-beta), Hogwarts Legacy, Spider-Man 2 (first 110 days), plus BO6/BO7 context

Pull step (read-only Snowflake; writes gta/.cache/inv1_<name>.parquet):  python inv1_ratio.py pull [names...]
Analysis (from caches):                                                  python inv1_ratio.py
Run from gta/penetration.
"""
import re
import sys
import numpy as np
import pandas as pd

pd.set_option("display.width", 250); pd.set_option("display.max_columns", 40); pd.set_option("display.max_rows", 400)
C = "../.cache/"
SEN, MSS = "Sony Entertainment Network", "Microsoft store"
PC_STORES = ["Steam", "Origin", "Epic Games", "Blizzard Entertainment", "Battle.net", "Green Man Gaming", "Humble Bundle"]
MARKETPLACES = ["eBay", "Etsy", "Temu", "TikTok", "Mercari", "Whatnot"]


# ----------------------------------------------------------------------------------------------- pull
def pull(names):
    sys.path.insert(0, C)
    from q import q
    sql = open("inv1_ratio.sql").read()
    blocks = dict(re.findall(r"-- @name (\w+)\n(.*?)(?=\n-- @name |\Z)", sql, re.S))
    for n in names or blocks:
        d = q(blocks[n], f"{C}inv1_{n}.parquet")
        print(n, d.shape)


# ------------------------------------------------------------------------------------------ helpers
def channel(df):
    m = df["MERCHANT_NAME"]
    u = df["DESCRIPTION"].str.upper()
    ch = pd.Series("RETAIL", index=df.index, dtype=object)
    ch[m == SEN] = "PSN"
    ch[m == MSS] = "MSS"
    pc = m.isin(PC_STORES) | (u.str.contains(r"\bPC\b|WINDOWS|EA APP|STEAM") & ~u.str.contains("XBOX|PLAYSTATION|PS5|PS4"))
    ch[pc] = "PC"
    return ch


def platform(df):
    u = df["DESCRIPTION"].str.upper()
    plat = pd.Series(None, index=df.index, dtype=object)
    plat[u.str.contains(r"XBOX|SERIES X|\bXBO\b|XBO\.")] = "XSX"
    plat[u.str.contains(r"PS5|PS4|PLAYSTATION")] = "PS5"
    plat[df["MERCHANT_NAME"] == SEN] = "PS5"
    plat[df["MERCHANT_NAME"] == MSS] = "XSX"
    plat[df["CH"] == "PC"] = "PC"
    return plat


BF6_X = (r"BETA|PACK|BFC|ADD-ON|TEXTURE|SHARED DATA|SINGLE PLAYER|MULTIPLAYER|MARKER|PRO -|BUNDLE|UPGRADE|SEASON|"
         r"CONTENT|COINS|SKIN|META\)|WITH PURCHASE|LAPTOP|DESKTOP")


def load_bf6():
    g = pd.read_parquet(C + "bf6.parquet")
    g = g[~g["DESCRIPTION"].str.upper().str.contains(BF6_X) & ~g["MERCHANT_NAME"].isin(["Google Play", "iTunes", "Shopify"])
          & (g["ITEM_PRICE"].isna() | g["ITEM_PRICE"].between(40, 140))].copy()
    return g


def load_gta():
    return pd.read_parquet(C + "gta6.parquet").copy()


GAMES = {  # open, launch, last observed date
    "GTA6": dict(open="2026-06-25", launch="2026-11-19", last="2026-10-26", load=load_gta),
    "BF6": dict(open="2025-07-31", launch="2025-10-10", last="2025-11-30", load=load_bf6),
}


def prep(game):
    cfg = GAMES[game]
    g = cfg["load"]()
    g["ORDER_DATE"] = pd.to_datetime(g["ORDER_DATE"])
    g["CH"] = channel(g)
    g["PLAT"] = platform(g)
    g = g[g["PLAT"].notna() & (g["ORDER_DATE"] <= pd.Timestamp(cfg["last"]))]
    o, l = pd.Timestamp(cfg["open"]), pd.Timestamp(cfg["launch"])
    g["DSO"] = (g["ORDER_DATE"] - o).dt.days.clip(lower=0)           # day before open -> day 0 (tz artefact)
    g["DTL"] = (g["ORDER_DATE"] - l).dt.days
    g = g[(g["ORDER_DATE"] >= o - pd.Timedelta(days=1))]
    # units = distinct mailbox x merchant x date x description (GTA cache is already distinct on these)
    g = g.drop_duplicates(["MAILBOX_ID", "MERCHANT_NAME", "ORDER_DATE", "DESCRIPTION"])
    return g


# ------------------------------------------------------------------------------------------- bases
def load_bases():
    d = pd.read_parquet(C + "desc_cls.parquet", columns=["MERCHANT_NAME", "H", "EXPLICIT_PS5", "EXPLICIT_XSX", "IS_GTA6"])
    r = pd.read_parquet(C + "rows.parquet", columns=["MAILBOX_ID", "MERCHANT_NAME", "H", "ORDER_DATE", "ITEM_PRICE"])
    r = r.merge(d, on=["MERCHANT_NAME", "H"], how="inner")
    r = r[(r["EXPLICIT_PS5"] | r["EXPLICIT_XSX"]) & ~r["IS_GTA6"]]
    p = r["ITEM_PRICE"]
    r = r[p.isna() | p.eq(0) | p.between(150, 2000)]
    r["ORDER_DATE"] = pd.to_datetime(r["ORDER_DATE"])
    mb = pd.read_parquet(C + "mailboxes.parquet", columns=["MAILBOX_ID", "ENTRY_DATE", "EXIT_DATE", "IN_PANEL_61212"])
    mb["ENTRY_DATE"] = pd.to_datetime(mb["ENTRY_DATE"])
    mb["EXIT_DATE"] = pd.to_datetime(mb["EXIT_DATE"])
    return r, mb


def owner_base(r, mb, open_, panel_only=True):
    """explicit PS5/XSX console purchase dated before open-1, joined before open (active panel by default)."""
    o = pd.Timestamp(open_)
    pre = r[r["ORDER_DATE"] < o - pd.Timedelta(days=1)]
    m = mb[mb["ENTRY_DATE"] < o]
    if panel_only:
        m = m[m["IN_PANEL_61212"] == 1]
    joined = set(m["MAILBOX_ID"])
    ps = set(pre.loc[pre["EXPLICIT_PS5"], "MAILBOX_ID"]) & joined
    xb = set(pre.loc[pre["EXPLICIT_XSX"], "MAILBOX_ID"]) & joined
    first_console = pre.groupby("MAILBOX_ID")["ORDER_DATE"].min()
    return {"PS5": ps, "XSX": xb, "ANY": ps | xb}, joined, first_console


def cum_at(first, col, k):
    return int((first[col] <= k).sum())


# ------------------------------------------------------------------------------------------- main
def main():
    G = {k: prep(k) for k in GAMES}
    r, mb = load_bases()
    panel = set(mb.loc[mb["IN_PANEL_61212"] == 1, "MAILBOX_ID"])
    bases, joined, fc = {}, {}, {}
    for k, cfg in GAMES.items():
        bases[k], joined[k], fc[k] = owner_base(r, mb, cfg["open"])

    # alignment points: (label, GTA (col, k), BF6 (col, k))
    gl = (pd.Timestamp(GAMES["GTA6"]["last"]) - pd.Timestamp(GAMES["GTA6"]["open"])).days      # 123
    gw = (pd.Timestamp(GAMES["GTA6"]["launch"]) - pd.Timestamp(GAMES["GTA6"]["open"])).days    # 147
    bw = (pd.Timestamp(GAMES["BF6"]["launch"]) - pd.Timestamp(GAMES["BF6"]["open"])).days      # 71
    gdtl = (pd.Timestamp(GAMES["GTA6"]["last"]) - pd.Timestamp(GAMES["GTA6"]["launch"])).days  # -24
    y_day = (pd.Timestamp("2026-10-18") - pd.Timestamp(GAMES["GTA6"]["open"])).days            # Yipit Vol.17 cut
    ALIGN = [
        ("A. ours: same days to launch (L-24)", ("DSO", gl), ("DTL", gdtl)),
        ("B. same %% of window (GTA 84%% -> BF6 day %d)" % round(gl / gw * bw), ("DSO", gl), ("DSO", round(gl / gw * bw))),
        ("C. Yipit Vol.17: GTA thru 10/18 (77%%) vs BF6 at 77%% (day %d)" % round(y_day / gw * bw), ("DSO", y_day), ("DSO", round(y_day / gw * bw))),
        ("D. same days since open, BF6 full pre-order window (day 70 = L-1)", ("DSO", gl), ("DTL", -1)),
        ("E. same days since open = 47 (BF6 L-24)", ("DSO", 47), ("DSO", 47)),
        ("F. same days since open = 30", ("DSO", 30), ("DSO", 30)),
        ("G. same days since open = 7", ("DSO", 7), ("DSO", 7)),
        ("H. GTA to date vs BF6 incl. launch week (L+7)", ("DSO", gl), ("DTL", 7)),
    ]

    def first_by(g, keys=("MAILBOX_ID",)):
        return g.groupby(list(keys))[["DSO", "DTL"]].min()

    # =============================================================== H2 + H3: one grid of definitions x alignments
    print("\n=== H2/H3: GTA/BF6 multiple by definition and alignment ===")
    defs = {}
    bf_all, gt_all = G["BF6"], G["GTA6"]
    bf_con = bf_all[bf_all["CH"] != "PC"]
    E = {k: bases[k]["ANY"] for k in GAMES}
    J = joined

    def series(g, k, unit, pop):
        """returns function(col, thr) -> count. unit: buyers|units. pop: None (all mailboxes), set of mailbox ids."""
        x = g if pop is None else g[g["MAILBOX_ID"].isin(pop[k] if isinstance(pop, dict) else pop)]
        if unit == "buyers":
            f = first_by(x)
            return lambda col, t: int((f[col] <= t).sum())
        return lambda col, t: int((x[col] <= t).sum())

    configs = [
        # name, unit, BF6 rows, population, normalise by base size?
        ("1 ours: explicit owners, console, buyers %", "buyers", bf_con, E, True),
        ("2 explicit owners, console + BF6 PC, buyers %", "buyers", bf_all, E, True),
        ("3 active panel joined pre-open, console, buyers %", "buyers", bf_con, J, True),
        ("4 active panel joined pre-open, console + BF6 PC, buyers %", "buyers", bf_all, J, True),
        ("5 active panel (current), console, raw buyers", "buyers", bf_con, panel, False),
        ("6 active panel (current), console + BF6 PC, raw buyers", "buyers", bf_all, panel, False),
        ("7 all mailboxes, console, raw units", "units", bf_con, None, False),
        ("8 all mailboxes, console + BF6 PC, raw units", "units", bf_all, None, False),
        ("9 all mailboxes, console, raw buyers", "buyers", bf_con, None, False),
        ("10 all mailboxes, console + BF6 PC, raw buyers", "buyers", bf_all, None, False),
    ]
    grid = []
    for name, unit, bfrows, pop, norm in configs:
        fg = series(gt_all, "GTA6", unit, pop)
        fb = series(bfrows, "BF6", unit, pop)
        if isinstance(pop, dict):
            ng, nb = len(pop["GTA6"]), len(pop["BF6"])
        else:
            ng = nb = 1
        row = {"definition": name}
        for lbl, (gc, gk), (bc, bk) in ALIGN:
            a, b = fg(gc, gk), fb(bc, bk)
            row[lbl[:2].strip(". ")] = round((a / ng) / (b / nb), 2) if b else np.nan
            if lbl.startswith("A."):
                row["GTA n"], row["BF6 n"] = a, b
                row["GTA base"], row["BF6 base"] = (ng, nb) if norm else ("", "")
        grid.append(row)
    grid = pd.DataFrame(grid)
    # panel-size normalisation for the all-mailbox rows: receipt-active mailboxes in the open month
    act = pd.read_parquet(C + "inv1_active_all.parquet"); act["MON"] = pd.to_datetime(act["MON"]); act = act.set_index("MON")["MB_ANY"]
    shrink = act[pd.Timestamp("2025-07-01")] / act[pd.Timestamp("2026-06-01")]
    print(f"receipt-active mailboxes Jul-2025 / Jun-2026 = {shrink:.3f} (all-mailbox rows below are NOT adjusted; multiply by this to normalise)")
    print("alignment key:"); [print("  ", a[0]) for a in ALIGN]
    print(grid.to_string(index=False))
    grid.to_csv("inv1_grid.csv", index=False)

    # ======================================================================= H2b: Yipit back-test
    print("\n=== H2b: back-test vs Yipit's published GTA/B6 multiples (all mailboxes, raw units, console GTA vs all-platform BF6) ===")
    yip = [("2026-06-28", 10.0), ("2026-07-12", 6.0), ("2026-07-26", 3.4), ("2026-09-27", 3.4), ("2026-10-04", 3.4), ("2026-10-11", 3.5), ("2026-10-18", 3.7)]
    o = pd.Timestamp(GAMES["GTA6"]["open"])
    yrows = []
    for d, yv in yip:
        dd = (pd.Timestamp(d) - o).days
        a = (gt_all["DSO"] <= dd).sum()
        pct_day = round(dd / gw * bw)
        dtl = (pd.Timestamp(d) - pd.Timestamp(GAMES["GTA6"]["launch"])).days
        r_pct = a / (bf_all["DSO"] <= pct_day).sum(); r_pct_c = a / (bf_con["DSO"] <= pct_day).sum()
        r_dso = a / (bf_all["DSO"] <= dd).sum() if dd <= 70 else np.nan
        r_dtl = a / (bf_all["DTL"] <= dtl).sum() if dtl >= -71 else np.nan
        yrows.append({"Yipit date": d, "GTA day": dd, "Yipit x": yv, "same % window (BF6 day)": pct_day, "x %win all-plat": round(r_pct, 2),
                      "x %win console": round(r_pct_c, 2), "x same day-since-open all-plat": round(r_dso, 2),
                      "x same days-to-launch all-plat": round(r_dtl, 2)})
    yrows = pd.DataFrame(yrows); print(yrows.to_string(index=False)); yrows.to_csv("inv1_yipit_backtest.csv", index=False)

    # ======================================================================= H1: channel-by-channel ratio
    print("\n=== H1a: GTA/BF6 by channel (explicit owners base, first purchase in that channel; and raw all-mailbox units) ===")
    rows = []
    for ch in ["PSN", "MSS", "RETAIL", "PC"]:
        for lbl, (gc, gk), (bc, bk) in ALIGN[:4]:
            g = gt_all[gt_all["CH"] == ch]; b = bf_all[bf_all["CH"] == ch]
            fg = first_by(g[g["MAILBOX_ID"].isin(E["GTA6"])]); fb = first_by(b[b["MAILBOX_ID"].isin(E["BF6"])])
            pg, pb = (fg[gc] <= gk).sum() / len(E["GTA6"]), (fb[bc] <= bk).sum() / len(E["BF6"])
            ug, ub = (g[gc] <= gk).sum(), (b[bc] <= bk).sum()
            rows.append({"channel": ch, "align": lbl[:1], "GTA pen %": round(100 * pg, 3), "BF6 pen %": round(100 * pb, 3),
                         "pen ratio": round(pg / pb, 2) if pb else np.nan, "GTA units": ug, "BF6 units": ub,
                         "unit ratio": round(ug / ub, 2) if ub else np.nan})
    h1 = pd.DataFrame(rows)
    print(h1.to_string(index=False))
    h1.to_csv("inv1_channel.csv", index=False)

    print("\n=== H1b: channel mix of base-game units at alignment A (GTA L-24 / BF6 L-24) ===")
    for k, g, (c, t) in [("GTA6", gt_all, ("DSO", gl)), ("BF6", bf_all, ("DTL", gdtl)), ("BF6 L-1", bf_all, ("DTL", -1)),
                         ("BF6 L+30", bf_all, ("DTL", 30))]:
        x = g[g[c] <= t]
        print(f"  {k:9s} n={len(x):6,d} ", (x["CH"].value_counts(normalize=True) * 100).round(1).to_dict(),
              "| PS share of console:", round(100 * (x.loc[x.CH != 'PC', 'PLAT'] == 'PS5').mean(), 1))

    # =========================================================================== H4: base effects
    print("\n=== H4: base composition and fixed cohort ===")
    fgt = first_by(gt_all[gt_all["CH"] != "PC"]); fbf = first_by(bf_con)
    for k in GAMES:
        b = bases[k]["ANY"]
        fcb = fc[k].reindex(list(b))
        ent = mb.set_index("MAILBOX_ID").loc[list(b), "ENTRY_DATE"]
        o = pd.Timestamp(GAMES[k]["open"])
        print(f"  {k} base {len(b):,}  PS5-only {len(bases[k]['PS5'] - bases[k]['XSX'])/len(b):.1%}  XSX-only {len(bases[k]['XSX'] - bases[k]['PS5'])/len(b):.1%}"
              f"  both {len(bases[k]['PS5'] & bases[k]['XSX'])/len(b):.1%}  | median console age at open {(o - fcb).dt.days.median()/365:.2f}y"
              f"  bought console in prior 12m {((o - fcb).dt.days < 365).mean():.1%}  | median tenure {(o - ent).dt.days.median()/365:.2f}y")
    gb, bb = bases["GTA6"]["ANY"], bases["BF6"]["ANY"]
    common, new = gb & bb, gb - bb
    print(f"  GTA base {len(gb):,} | in BF6 base too {len(common):,} | GTA-only {len(new):,} | BF6-only (not in GTA base) {len(bb - gb):,}")
    def pen(f, pop, col, t):
        return (f.reindex(list(pop)).dropna()[col] <= t).sum() / len(pop)
    cohort = []
    for lbl, (gc, gk), (bc, bk) in ALIGN[:4]:
        pg_all, pb_all = pen(fgt, gb, gc, gk), pen(fbf, bb, bc, bk)
        pg_c, pb_c = pen(fgt, common, gc, gk), pen(fbf, common, bc, bk)
        cohort.append({"align": lbl[:1], "GTA full %": round(100 * pg_all, 2), "BF6 full %": round(100 * pb_all, 2), "ratio full": round(pg_all / pb_all, 2),
                       "GTA common %": round(100 * pg_c, 2), "BF6 common %": round(100 * pb_c, 2), "ratio common": round(pg_c / pb_c, 2),
                       "GTA in GTA-only %": round(100 * pen(fgt, new, gc, gk), 2)})
    print(pd.DataFrame(cohort).to_string(index=False))
    # GTA among BF6 pre-orderers / BF6 among GTA pre-orderers (overlap)
    bf_buyers = set(fbf.index[fbf["DTL"] <= -1]); gt_buyers = set(fgt.index)
    print(f"  overlap: {len(bf_buyers & gt_buyers):,} of {len(bf_buyers):,} BF6 console pre-orderers ({len(bf_buyers & gt_buyers)/len(bf_buyers):.1%}) have pre-ordered GTA VI;"
          f" of {len(gt_buyers):,} GTA pre-orderers {len(bf_buyers & gt_buyers)/len(gt_buyers):.1%} pre-ordered BF6")
    # BF6 pre-orderers still in data in 2026? (survivorship of the current active-panel snapshot)
    allbf = set(first_by(bf_con).query("DTL <= -1").index)
    print(f"  BF6 console pre-orderers (all mailboxes) {len(allbf):,}; in current active panel {len(allbf & panel):,} ({len(allbf & panel)/len(allbf):.1%});"
          f" GTA pre-orderers in active panel {len(gt_buyers & panel)/len(gt_buyers):.1%}")

    # ====================================================== H1c/H1d: Snowflake pulls (franchise channel share, volume)
    h1_trend()
    # ============================================================================ H5: comparison titles
    h5_titles(r, mb)


# --------------------------------------------------------------------------------- H1 trend (Snowflake)
FR = [  # key, regex on upper description, include-year pattern
    ("CoD", r"CALL OF DUTY|BLACK OPS|MODERN WARFARE"),
    ("Madden", r"MADDEN NFL 2\d"),
    ("NBA 2K", r"NBA 2K2\d"),
    ("CFB", r"COLLEGE FOOTBALL 2\d"),
    ("EA FC", r"EA SPORTS FC|\bFC 2[5-7]\b"),
]
FR_X = (r"POINTS|\bCP\b|PACK|BUNDLE|UPGRADE|VC\b|VIRTUAL CURRENCY|FC POINTS|COINS|BATTLE PASS|BLACKCELL|ADD-ON|DLC|"
        r"SEASON PASS|TRACKER|OPERATOR|SKIN|CONTROLLER|GUIDE|POSTER|SHIRT|HOODIE|FIGURE|CARD|TOKEN|DOUBLE XP|ENERGY|"
        r"MOUNTAIN DEW|DORITOS|JERKY|SNACK|BURGER|CEREAL|GIFT|VOUCHER|SUBSCRIPTION|GAME PASS|BETA|DEMO|TRIAL|CONSOLE")


def classify_franchise(f):
    u = f["DESCRIPTION"].str.upper().str.replace(r"[®™�]", "", regex=True)
    f["FR"] = None
    for k, pat in FR:
        f.loc[f["FR"].isna() & u.str.contains(pat), "FR"] = k
    f = f[f["FR"].notna() & ~u.str.contains(FR_X)]
    f = f[f["MED_PRICE"].isna() | f["MED_PRICE"].between(40, 130)]
    m = f["MERCHANT_NAME"]
    u = f["DESCRIPTION"].str.upper()
    f["CH"] = np.select([m == SEN, m == MSS, m.isin(PC_STORES) | u.str.contains(r"\bPC\b|WINDOWS|STEAM")],
                        ["PSN", "MSS", "PC"], "RETAIL")
    # retail must name a console platform (drops toys/books/apparel that slipped through)
    f = f[(f["CH"] != "RETAIL") | u.str.contains(r"PS5|PS4|PLAYSTATION|XBOX|SERIES X")]
    return f


def h1_trend():
    try:
        f = pd.read_parquet(C + "inv1_franchise.parquet")
    except FileNotFoundError:
        print("\n(H1 trend: inv1_franchise.parquet missing; run pull)"); return
    f = classify_franchise(f)
    f["MON"] = pd.to_datetime(f["MON"])
    f["YEAR"] = f["MON"].dt.year
    print("\n=== H1c: annual console franchises (CoD, Madden, NBA 2K, CFB, EA FC) base-game rows, channel share (console only) ===")
    con = f[f["CH"] != "PC"]
    t = con.pivot_table(index=["YEAR"], columns="CH", values="N_ROWS", aggfunc="sum").fillna(0)
    t["digital %"] = (100 * (t["PSN"] + t["MSS"]) / t[["PSN", "MSS", "RETAIL"]].sum(axis=1)).round(1)
    t["PSN of PS %"] = np.nan
    print(t.round(0).to_string())
    # same-season comparison: Aug-Nov of each year (launch season), by franchise
    s = con[con["MON"].dt.month.between(7, 11)]
    t2 = s.pivot_table(index="FR", columns=["YEAR", "CH"], values="N_ROWS", aggfunc="sum").fillna(0)
    out = {}
    for y in [2024, 2025, 2026]:
        if (y, "PSN") in t2:
            tot = t2[y][["PSN", "MSS", "RETAIL"]].sum(axis=1)
            out[f"{y} rows"] = tot
            out[f"{y} digital %"] = (100 * (t2[y]["PSN"] + t2[y]["MSS"]) / tot).round(1)
    print("\nJul-Nov launch season, digital share of console base-game rows, by franchise (2026 = Jul-Oct 26):")
    print(pd.DataFrame(out).to_string())
    m = con.pivot_table(index="MON", columns="CH", values="N_ROWS", aggfunc="sum").fillna(0)
    m["digital %"] = (100 * (m["PSN"] + m["MSS"]) / m.sum(axis=1)).round(1)
    print("\nmonthly (all five franchises):"); print(m.astype({"PSN": int, "MSS": int, "RETAIL": int}).to_string())
    m.to_csv("inv1_franchise_monthly.csv")

    try:
        v = pd.read_parquet(C + "inv1_volume.parquet")
    except FileNotFoundError:
        print("(volume missing)"); return
    v["MON"] = pd.to_datetime(v["MON"])
    print("\n=== H1d: active 6_12_12 panel, members joined before 2024-01 (fixed cohort): per-member receipt volume ===")
    x = v[v["FIXED"] == 1].sort_values("MON").set_index("MON")
    out = pd.DataFrame({
        "mb_any": x["MB_ANY"], "rows/mb": (x["ROWS_ANY"] / x["MB_ANY"]).round(1),
        "PSN mb %": (100 * x["MB_PSN"] / x["MB_ANY"]).round(2), "PSN rows/100mb": (100 * x["ROWS_PSN"] / x["MB_ANY"]).round(1),
        "PSN paid mb %": (100 * x["MB_PSN_PAID"] / x["MB_ANY"]).round(2),
        "PSN game>=$20 mb %": (100 * x["MB_PSN_GAME"] / x["MB_ANY"]).round(3), "PSN game rows/100mb": (100 * x["ROWS_PSN_GAME"] / x["MB_ANY"]).round(2),
        "MSS mb %": (100 * x["MB_MSS"] / x["MB_ANY"]).round(2), "MSS>=$20 mb %": (100 * x["MB_MSS_20"] / x["MB_ANY"]).round(3),
        "PC store mb %": (100 * x["MB_PC"] / x["MB_ANY"]).round(2)})
    print(out.to_string())
    out.to_csv("inv1_volume_fixed.csv")


# ------------------------------------------------------------------------------------ H5 (Snowflake)
TITLES = {  # open (first pre-order day), launch, cut for MSc-style compare, base-game regex, exclusion regex
    "MWII": dict(open="2022-06-08", launch="2022-10-28", beta="2022-09-16",
                 inc=r"MODERN WARFARE\s*(?:II|2)\b", exc=r"REMASTER|CAMPAIGN REMASTERED|\b2009\b|MODERN WARFARE\s*(?:III|3)\b|MW3|WARZONE|COD POINTS|POINTS|BLACKCELL|TRACKER|PACK|BUNDLE|UPGRADE|BETA|CONTROLLER|GUIDE|POSTER|CONSOLE|HEADSET|DOUBLE XP|DEW|DORITOS|VAULT EDITION UPGRADE"),
    "HOGWARTS": dict(open=None, launch="2023-02-10",
                     inc=r"HOGWARTS LEGACY", exc=r"GUIDE|BOOK|POSTER|SHIRT|FIGURE|PLUSH|FUNKO|CONTROLLER|CONSOLE|BUNDLE|UPGRADE|PACK|ART OF|CAKE|LEGO|MUG|PIN\b|HOODIE|COSTUME|SOUNDTRACK|VINYL|WAND|JOURNAL|PUZZLE|SWITCH|NINTENDO"),
    "SPIDERMAN2": dict(open=None, launch="2023-10-20",
                       inc=r"SPIDER-?\s*MAN\s*2\b", exc=r"GUIDE|BOOK|POSTER|SHIRT|FIGURE|PLUSH|FUNKO|CONTROLLER|CONSOLE|BUNDLE|UPGRADE|PACK|ART OF|CAKE|LEGO|MUG|HOODIE|COSTUME|SOUNDTRACK|VINYL|PUZZLE|COVER|SKIN|FACEPLATE|LIMITED EDITION PS5|INTO THE|ACROSS THE|SPIDER-VERSE|SPIDERVERSE|MILES MORALES\b(?!.*2)|DVD|BLU|4K|MOVIE|COMIC|TOY|MASK|SUIT\b|LAMP|BACKPACK|WATCH"),
    "BO6": dict(open="2024-06-09", launch="2024-10-25",
                inc=r"BLACK OPS\s*6\b", exc=r"POINTS|BLACKCELL|TRACKER|PACK|BUNDLE(?!.*CROSS)|UPGRADE|BETA|CONTROLLER|GUIDE|POSTER|CONSOLE|HEADSET|DOUBLE XP|DEW|DORITOS|BATTLE PASS|OPERATOR|SKIN|VAULT EDITION UPGRADE|JERKY|BURGER"),
    "BO7": dict(open="2025-08-19", launch="2025-11-14",
                inc=r"BLACK OPS\s*7\b", exc=r"POINTS|BLACKCELL|TRACKER|PACK|BUNDLE(?!.*CROSS)|UPGRADE|BETA|CONTROLLER|GUIDE|POSTER|CONSOLE|HEADSET|DOUBLE XP|DEW|DORITOS|BATTLE PASS|OPERATOR|SKIN|VAULT EDITION UPGRADE|JERKY|BURGER"),
}


def load_title(t, raw):
    cfg = TITLES[t]
    x = raw[raw["TITLE"] == t].copy()
    u = x["DESCRIPTION"].str.upper().str.replace(r"[®™�]", "", regex=True)
    x = x[u.str.contains(cfg["inc"]) & ~u.str.contains(cfg["exc"]) & ~x["MERCHANT_NAME"].str.contains("Cancellation")]
    x = x[x["ITEM_PRICE"].isna() | x["ITEM_PRICE"].between(35, 140)]
    x["ORDER_DATE"] = pd.to_datetime(x["ORDER_DATE"])
    x = x[x["ORDER_DATE"] < pd.Timestamp(cfg["launch"])]
    x["CH"] = channel(x)
    x["PLAT"] = platform(x)
    x = x.drop_duplicates(["MAILBOX_ID", "MERCHANT_NAME", "ORDER_DATE", "DESCRIPTION"])
    return x


def h5_titles(r, mb):
    try:
        raw = pd.read_parquet(C + "inv1_titles.parquet")
    except FileNotFoundError:
        print("\n(H5: inv1_titles.parquet missing; run pull)"); return
    act = pd.read_parquet(C + "inv1_active_all.parquet")
    act["MON"] = pd.to_datetime(act["MON"]); act = act.set_index("MON")["MB_ANY"]
    G = {"GTA6": prep("GTA6"), "BF6": prep("BF6")}
    G["GTA6"] = G["GTA6"][G["GTA6"]["DTL"] < 0]
    for t in TITLES:
        G[t] = load_title(t, raw)
    print("\n=== H5: comparison titles: weekly base-game rows before launch (to locate pre-order open) ===")
    for t in TITLES:
        x = G[t]
        w = x.groupby(x["ORDER_DATE"].dt.to_period("W")).size()
        first = w[w >= max(5, 0.02 * w.max())].index.min()
        print(f"  {t}: rows {len(x):,}  mb {x.MAILBOX_ID.nunique():,}  first week >=2% of peak: {first}  configured open {TITLES[t]['open']}")
        if TITLES[t]["open"] is None:
            # open = first day with >= 10 rows
            d = x.groupby("ORDER_DATE").size()
            TITLES[t]["open"] = str(d[d >= 10].index.min().date())
            print(f"     inferred open {TITLES[t]['open']} (first day >= 10 rows)")
        print("    channel mix:", (x["CH"].value_counts(normalize=True) * 100).round(1).to_dict(),
              " top desc:", x["DESCRIPTION"].value_counts().head(4).to_dict())
    opens = {**{t: TITLES[t]["open"] for t in TITLES}, "GTA6": GAMES["GTA6"]["open"], "BF6": GAMES["BF6"]["open"]}
    for t, x in G.items():
        x["DSO"] = (x["ORDER_DATE"] - pd.Timestamp(opens[t])).dt.days.clip(lower=0)
        G[t] = x[x["ORDER_DATE"] >= pd.Timestamp(opens[t]) - pd.Timedelta(days=1)]

    def n_active(t):  # receipt-active mailboxes in the open month (all mailboxes) for normalisation
        return act.get(pd.Timestamp(opens[t]).to_period("M").to_timestamp(), np.nan)

    print("\n=== H5: GTA VI vs comparison titles, cumulative pre-launch base-game units at same days since open ===")
    print("   (units = distinct mailbox x merchant x date x description; all mailboxes; 'norm' divides by receipt-active mailboxes in the open month)")
    mw_beta = (pd.Timestamp(TITLES["MWII"]["beta"]) - pd.Timestamp(opens["MWII"])).days - 1
    rows = []
    for t, day, note in [("MWII", mw_beta, "MSc: pre-beta (day %d)" % mw_beta), ("MWII", 95, "pre-beta ramp (day 95, 11 Sep)"), ("MWII", 100, "day 100"),
                         ("HOGWARTS", 110, "MSc: first 110 days"), ("SPIDERMAN2", 110, "MSc: first 110 days"),
                         ("BF6", 47, "day 47"), ("BF6", 70, "full window (day 70)"), ("BO6", 110, "first 110 days"), ("BO7", 70, "day 70")]:
        for scope, keep in [("console", lambda x: x["CH"] != "PC"), ("all platforms", lambda x: x.index == x.index)]:
            a, b = G["GTA6"], G[t]
            a, b = a[keep(a)], b[keep(b)]
            ua, ub = (a["DSO"] <= day).sum(), (b["DSO"] <= day).sum()
            ba, bb = a.loc[a["DSO"] <= day, "MAILBOX_ID"].nunique(), b.loc[b["DSO"] <= day, "MAILBOX_ID"].nunique()
            na, nb = n_active("GTA6"), n_active(t)
            # day available for GTA?
            gday = min(day, (pd.Timestamp(GAMES['GTA6']['last']) - pd.Timestamp(opens['GTA6'])).days)
            rows.append({"comp": t, "window": note, "scope": scope, "GTA units": ua, "comp units": ub, "units x": round(ua / ub, 2) if ub else np.nan,
                         "buyers x": round(ba / bb, 2) if bb else np.nan,
                         "norm units x": round((ua / na) / (ub / nb), 2) if ub else np.nan, "PSN units x": round(((a.CH == 'PSN') & (a.DSO <= day)).sum() / max(1, ((b.CH == 'PSN') & (b.DSO <= day)).sum()), 2),
                         "retail units x": round(((a.CH == 'RETAIL') & (a.DSO <= day)).sum() / max(1, ((b.CH == 'RETAIL') & (b.DSO <= day)).sum()), 2)})
    h5 = pd.DataFrame(rows)
    print(h5.to_string(index=False))
    h5.to_csv("inv1_titles.csv", index=False)
    print("  receipt-active mailboxes in open month:", {t: int(n_active(t)) for t in opens})
    # channel mix by title (console only) at the comparison window
    print("\n  console channel mix at window (PSN / MSS / RETAIL %):")
    for t, day in [("GTA6", 123), ("MWII", mw_beta), ("HOGWARTS", 110), ("SPIDERMAN2", 110), ("BO6", 110), ("BF6", 70), ("BO7", 70)]:
        x = G[t]; x = x[(x["CH"] != "PC") & (x["DSO"] <= day)]
        print(f"   {t:10s} n={len(x):6,d}", (x["CH"].value_counts(normalize=True) * 100).round(1).to_dict(),
              "| PC share of all-platform:", round(100 * ((G[t]['CH'] == 'PC') & (G[t]['DSO'] <= day)).sum() / max(1, (G[t]['DSO'] <= day).sum()), 1))
    # cumulative curves for chart / reuse
    cur = {t: G[t].groupby("DSO").size().reindex(range(0, 160), fill_value=0).cumsum() for t in G}
    pd.DataFrame(cur).to_csv("inv1_title_curves.csv")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "pull":
        pull(sys.argv[2:])
    else:
        main()
