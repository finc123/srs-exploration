"""inv2: Roblox payers x GTA VI pre-orderers overlap in NIQ Slice e-receipts.

Inputs (all local caches, read-only Snowflake pulls):
  .cache/roblox_rows.parquet   <- penetration/inv2_roblox.sql (every row mentioning roblox/robux, or merchant Roblox*, 2015..2026-10-27)
  .cache/gta6.parquet          GTA VI base-game pre-order rows (orders only, cancellations excluded)
  .cache/mailboxes.parquet     mailbox metadata (ENTRY_DATE, IN_PANEL_61212)
  .cache/mb_console_flags.parquet  console-owner flags (notes/console_owners.md), for the MSc "a third" check

Outputs: printed tables + penetration/inv2_roblox_out/*.csv
Run:  python penetration/inv2_roblox.py
"""
import os
import re
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
C = os.path.join(ROOT, ".cache")
OUT = os.path.join(ROOT, "penetration", "inv2_roblox_out")
os.makedirs(OUT, exist_ok=True)
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 40); pd.set_option("display.max_rows", 300)

# ---------------------------------------------------------------- classification
GIFT_RX = re.compile(r"gift|e-?card|egift|\bvgc\b|game ?card|digital code|gift code|game code|universal \$|"
                     r"digital download|\[online game code\]", re.I)
MERCH_RX = re.compile(r"song|feat\.|diary of|book|paperback|guide|t-shirt|shirt|\btee\b|plush|figure|toy|nerf|"
                      r"blaster|mystery|backpack|advent|playset|socks|costume|poster|sticker|cupcake|lego|"
                      r"thumbnail|edit your|unofficial|cloud phone|skins maker|customuse|studio introduction|"
                      r"game development|happykids|annual \d{4}|hoodie|pajama|bundle by", re.I)


def classify(d: pd.DataFrame) -> pd.DataFrame:
    m = d.MERCHANT_NAME.fillna("")
    t = d.DESCRIPTION.fillna("")
    tl = t.str.lower()
    qty = d.ITEM_QUANTITY.fillna(1).clip(lower=1)
    amt = d.ITEM_PRICE * qty
    # Roblox direct / Xsolla: item_price sometimes null while order_total carries the charge (single-item emails)
    direct_m = m.isin(["Roblox", "Xsolla"])
    amt = amt.where(amt.notna() | ~direct_m, d.ORDER_TOTAL)
    d = d.assign(amt=amt.fillna(0.0))
    rbx = tl.str.contains(r"robux|roblox", regex=True)
    cancel = m.str.endswith(" Cancellation")
    merch = tl.str.contains(MERCH_RX)
    gift = tl.str.contains(GIFT_RX) | m.eq("CashStar")

    ch = pd.Series(None, index=d.index, dtype=object)
    ch[m.eq("Roblox") & ~tl.str.contains("credit redemption|psplusitem")] = "direct"
    ch[m.eq("Xsolla") & rbx] = "direct"
    ch[m.eq("iTunes") & tl.str.contains(r"robux|^roblox\b|roblox (?:premium|plus)", regex=True) & ~merch] = "apple"
    ch[m.eq("Google Play") & tl.str.contains(r"\(roblox\)", regex=True)] = "google_play"
    ch[m.eq("Sony Entertainment Network") & rbx] = "psn"
    ch[m.eq("Microsoft store") & rbx & tl.str.contains("xbox")] = "ms_xbox"
    ch[m.eq("Microsoft store") & rbx & ~tl.str.contains("xbox")] = "ms_other"   # Windows app or unlabelled
    ch[m.isin(["Amazon", "Samsung", "Meta"]) & tl.str.contains(r"robux|roblox premium|roblox: ", regex=True)
       & ~gift & ~merch] = "other_app"   # Amazon Appstore (Fire), Galaxy Store, Meta Quest
    # gift cards: any merchant, separate class (retail / CashStar-bought codes, Walmart 'Robux for Xbox' codes)
    is_gc = gift & rbx & ~merch & ~m.isin(["Roblox", "Xsolla", "iTunes", "Google Play", "Sony Entertainment Network",
                                           "Microsoft store"])
    is_gc |= m.eq("Walmart") & tl.str.contains("robux for xbox")
    ch[is_gc] = "gift_card"
    ch[m.eq("Roblox") & tl.str.contains("credit redemption")] = "gc_redeem"
    ch[cancel] = None
    d["channel"] = ch
    d["paid"] = d.channel.notna() & (d.amt > 0)
    # gift-card redemptions carry no price; treat as a Roblox-spend signal in the 'incl. gift cards' variant
    d.loc[d.channel.eq("gc_redeem"), "paid"] = True
    return d


GROUP = {"direct": "direct", "apple": "mobile", "google_play": "mobile", "other_app": "mobile",
         "psn": "console", "ms_xbox": "console", "ms_other": "console", "gift_card": "gift_card",
         "gc_redeem": "gift_card"}
PAY_CH = ["direct", "apple", "google_play", "other_app", "psn", "ms_xbox", "ms_other"]


def load():
    d = pd.read_parquet(os.path.join(C, "roblox_rows.parquet"))
    d["ORDER_DATE"] = pd.to_datetime(d.ORDER_DATE)
    d = d.drop_duplicates(["MAILBOX_ID", "MERCHANT_NAME", "ORDER_ID", "DESCRIPTION", "ITEM_PRICE"])
    d = classify(d)
    r = d[d.paid].copy()
    r["grp"] = r.channel.map(GROUP)
    g = pd.read_parquet(os.path.join(C, "gta6.parquet"))
    g["ORDER_DATE"] = pd.to_datetime(g.ORDER_DATE)
    gfirst = g.groupby("MAILBOX_ID").ORDER_DATE.min()
    mb = pd.read_parquet(os.path.join(C, "mailboxes.parquet"), columns=["MAILBOX_ID", "ENTRY_DATE", "IN_PANEL_61212"])
    mb["ENTRY_DATE"] = pd.to_datetime(mb.ENTRY_DATE)
    return d, r, gfirst, mb


def monthly(r):
    x = r[(r.ORDER_DATE >= "2025-01-01")].copy()
    x["month"] = x.ORDER_DATE.dt.to_period("M").astype(str)
    tx = x.groupby(["month", "channel"]).ORDER_ID.nunique().unstack(fill_value=0)[PAY_CH + ["gift_card", "gc_redeem"]]
    mbx = x.groupby(["month", "channel"]).MAILBOX_ID.nunique().unstack(fill_value=0)[PAY_CH + ["gift_card", "gc_redeem"]]
    usd = x.groupby(["month", "channel"]).amt.sum().unstack(fill_value=0)[PAY_CH + ["gift_card"]].round(0)
    return tx, mbx, usd


def pct(a, b):
    return round(100 * a / b, 2) if b else np.nan


def forward(r, gfirst, mb, T, panel_only, months=6, incl_gc=False):
    """Roblox payers in (T-months, T] -> % with GTA VI pre-order by T; channel + spend splits."""
    T = pd.Timestamp(T); S = T - pd.DateOffset(months=months)
    x = r[(r.ORDER_DATE > S) & (r.ORDER_DATE <= T)]
    if not incl_gc:
        x = x[x.channel.isin(PAY_CH)]
    if panel_only:
        x = x[x.MAILBOX_ID.isin(mb.loc[mb.IN_PANEL_61212 == 1, "MAILBOX_ID"])]
    gset = set(gfirst[gfirst <= T].index)
    per = x.groupby("MAILBOX_ID").agg(spend=("amt", "sum"), n_tx=("ORDER_ID", "nunique"))
    for gname in ["console", "mobile", "direct", "gift_card"]:
        per[gname] = x[x.grp == gname].groupby("MAILBOX_ID").size().reindex(per.index).notna()
    per["psn"] = x[x.channel == "psn"].groupby("MAILBOX_ID").size().reindex(per.index).notna()
    per["xbox"] = x[x.channel.isin(["ms_xbox", "ms_other"])].groupby("MAILBOX_ID").size().reindex(per.index).notna()
    per["gta"] = per.index.isin(gset)
    rows = []

    def add(label, s):
        rows.append({"segment": label, "roblox_payers": len(s), "gta_preorderers": int(s.gta.sum()),
                     "pct_gta": pct(s.gta.sum(), len(s)),
                     "avg_spend_gta": round(s.loc[s.gta, "spend"].mean(), 2),
                     "avg_spend_non": round(s.loc[~s.gta, "spend"].mean(), 2),
                     "med_spend_gta": round(s.loc[s.gta, "spend"].median(), 2),
                     "med_spend_non": round(s.loc[~s.gta, "spend"].median(), 2)})
    add("all Roblox payers", per)
    add("any console (PSN/MS)", per[per.console])
    add("  PSN", per[per.psn])
    add("  MS Store / Xbox", per[per.xbox])
    add("any mobile (Apple/GP/other app)", per[per.mobile])
    add("any direct (roblox.com/Xsolla)", per[per.direct])
    add("console only", per[per.console & ~per.mobile & ~per.direct])
    add("mobile only", per[per.mobile & ~per.console & ~per.direct])
    add("direct only", per[per.direct & ~per.console & ~per.mobile])
    add("multi-channel", per[(per[["console", "mobile", "direct"]].sum(axis=1) >= 2)])
    out = pd.DataFrame(rows)
    # spend quintiles
    per["spend_q"] = pd.qcut(per.spend.rank(method="first"), 5, labels=["Q1 low", "Q2", "Q3", "Q4", "Q5 high"])
    sq = per.groupby("spend_q", observed=True).agg(payers=("gta", "size"), gta=("gta", "sum"),
                                                    min_spend=("spend", "min"), max_spend=("spend", "max"))
    sq["pct_gta"] = (100 * sq.gta / sq.payers).round(2)
    return out, sq, per


def reverse(r, gfirst, mb, T, panel_only=True):
    """GTA VI pre-orderers by T: % with a Roblox paid transaction in window before T."""
    T = pd.Timestamp(T)
    g = gfirst[gfirst <= T]
    if panel_only:
        g = g[g.index.isin(mb.loc[mb.IN_PANEL_61212 == 1, "MAILBOX_ID"])]
    ent = mb.set_index("MAILBOX_ID").ENTRY_DATE.reindex(g.index)
    x = r[r.MAILBOX_ID.isin(g.index) & (r.ORDER_DATE <= T)]
    rows = []
    for wname, S in [("6m", T - pd.DateOffset(months=6)), ("12m", T - pd.DateOffset(months=12)),
                     ("24m", T - pd.DateOffset(months=24)), ("all history", pd.Timestamp("2015-01-01"))]:
        w = x[x.ORDER_DATE > S]
        for cname, sel in [("console (PSN + any MS Store)", w.grp.eq("console")),
                           ("console strict (PSN + 'for Xbox')", w.channel.isin(["psn", "ms_xbox"])),
                           ("PSN", w.channel.eq("psn")),
                           ("mobile (Apple/GP/other app)", w.grp.eq("mobile")),
                           ("direct (roblox.com/Xsolla)", w.grp.eq("direct")),
                           ("any paying channel", w.channel.isin(PAY_CH)),
                           ("any incl. gift cards", w.channel.notna())]:
            ids = set(w.loc[sel, "MAILBOX_ID"])
            tenured = ent <= S
            rows.append({"window": wname, "channel": cname, "gta_base": len(g), "with_roblox": len(ids),
                         "pct": pct(len(ids), len(g)),
                         "base_tenured": int(tenured.sum()),
                         "pct_tenured": pct(len(ids & set(g.index[tenured])), int(tenured.sum()))})
    return pd.DataFrame(rows)


def main():
    d, r, gfirst, mb = load()
    print("rows", len(d), "paid roblox rows", len(r))
    print("\nUnclassified roblox-text rows by merchant (top 15, excluded as merch/other):")
    print(d[d.channel.isna() & ~d.MERCHANT_NAME.str.endswith(" Cancellation", na=False)]
          .MERCHANT_NAME.value_counts().head(15).to_string())
    print("\nZero/unpriced rows in paying channels (excluded):")
    print(d[d.channel.isin(PAY_CH) & ~d.paid].channel.value_counts().to_string())

    tx, mbx, usd = monthly(r)
    print("\n== Task 1: paid Roblox transactions (distinct order_id) by channel by month ==\n", tx.to_string())
    print("\n== mailboxes by channel by month ==\n", mbx.to_string())
    print("\n== $ by channel by month ==\n", usd.to_string())
    tx.to_csv(f"{OUT}/t1_tx_by_channel_month.csv"); mbx.to_csv(f"{OUT}/t1_mb_by_channel_month.csv")
    usd.to_csv(f"{OUT}/t1_usd_by_channel_month.csv")

    print("\n== Task 2: Roblox payers (6m) -> % pre-ordered GTA VI ==")
    for T in ["2026-10-11", "2026-10-26"]:
        for panel in [True, False]:
            for gc in [False, True]:
                out, sq, per = forward(r, gfirst, mb, T, panel, incl_gc=gc)
                tag = f"T={T} {'6_12_12 panel' if panel else 'all mailboxes'} {'incl GC' if gc else 'excl GC'}"
                print(f"\n-- {tag}\n", out.to_string(index=False))
                fn = f"t2_{T}_{'panel' if panel else 'all'}_{'gc' if gc else 'nogc'}"
                out.to_csv(f"{OUT}/{fn}.csv", index=False)
                if not gc:
                    print(sq.to_string()); sq.to_csv(f"{OUT}/{fn}_spendq.csv")
                if panel and not gc and T == "2026-10-26":
                    cf = pd.read_parquet(os.path.join(C, "mb_console_flags.parquet"), columns=["B_ANY", "C_ANY"])
                    cf = cf[cf.index.isin(per.index)]
                    print("\nMSc 'nearly a third of Roblox spenders have PS/Xbox purchase' check (panel, 6m payers):")
                    print(" model-agnostic PS/Xbox evidence (C_ANY): %.1f%%" % (100 * cf.C_ANY.mean()))
                    print(" current-gen console owner (B_ANY):        %.1f%%" % (100 * cf.B_ANY.mean()))
                    print(" Roblox console channel itself:            %.1f%%" % (100 * per.console.mean()))

    print("\n== Task 2b: window sensitivity (T=2026-10-11, excl GC, all Roblox payers) ==")
    sens = []
    for months in [3, 6, 12, 24]:
        for panel in [True, False]:
            out, _, _ = forward(r, gfirst, mb, "2026-10-11", panel, months=months)
            sens.append({"window_m": months, "base": "6_12_12 panel" if panel else "all mailboxes",
                         **out.iloc[0].drop("segment").to_dict()})
    sens = pd.DataFrame(sens)
    print(sens.to_string(index=False))
    sens.to_csv(f"{OUT}/t2b_window_sensitivity.csv", index=False)

    print("\n== Task 3: GTA VI pre-orderers -> % with Roblox payment (T=2026-10-26) ==")
    for panel in [True, False]:
        rv = reverse(r, gfirst, mb, "2026-10-26", panel)
        print(f"\n-- {'6_12_12 panel' if panel else 'all mailboxes'}\n", rv.to_string(index=False))
        rv.to_csv(f"{OUT}/t3_reverse_{'panel' if panel else 'all'}.csv", index=False)
    rv = reverse(r, gfirst, mb, "2026-10-18", True)   # MSc data thru ~17-18 Oct
    print("\n-- 6_12_12 panel, T=2026-10-18\n", rv.to_string(index=False))
    rv.to_csv(f"{OUT}/t3_reverse_panel_1018.csv", index=False)


if __name__ == "__main__":
    main()
