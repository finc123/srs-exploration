"""Inv 3: gaming-spend cohorts among explicit console owners, and GTA VI / BF6 penetration by cohort (NIQ Slice, 6_12_12 panel).

Base (same as gta6_penetration.py): active-panel mailboxes, joined before the game's pre-order open, explicit PS5/Series X|S
console purchase dated before open-1d. GTA VI open 25 Jun 2026 (outcome: console base-game order by 26 Oct 2026);
BF6 open 31 Jul 2025 (outcomes: by 17 Sep 2025 = L-23, matched to GTA's current days-to-launch; and by 30 Nov 2025).
Spend window = 12 months before open: [open-365d, open-2d] (open-1d excluded: midnight-ET pre-orders carry that date).

Spend = sum(item_price x qty), pre-tax, USD, over gaming items. Rules (see notes/inv3_spend_cohorts.md):
  * excluded as funding (double counting): Steam Wallet funds, Steam/Epic/Xbox/PSN/eShop gift cards, Epic account balance,
    "credit to Microsoft account", Battle.net balance, Roblox credit redemption; Microsoft 365 / Windows / Copilot etc.
  * Epic rows with order_total = 0 are free-game claims carrying list price -> $0.
  * hardware (consoles, Steam Deck, Portal, PSVR2, Switch) excluded from spend.
  * non-USD storefronts: per mailbox x merchant median price / SKU-modal-price in [1.2, 1.6] -> deflated by that ratio.
Retail = PS/Xbox-labelled items at other retailers (rows.parquet candidate rows, console_owners rules), consoles excluded.

Queries: penetration/inv3_spend_cohorts.sql (pulled to .cache/inv3_rows.parquet, inv3_desc.parquet).
Run from gta/penetration:  python inv3_spend_cohorts.py
"""
import re
import warnings
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", "This pattern")
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 40); pd.set_option("display.max_rows", 300)
C = "../.cache/"
OUT = "inv3_out/"
SEN, MSS = "Sony Entertainment Network", "Microsoft store"
GAMES = {
    "GTA6": dict(open="2026-06-25", outcomes={"by_26Oct26": "2026-10-26"}),
    "BF6": dict(open="2025-07-31", outcomes={"by_L-23_17Sep25": "2025-09-17", "by_30Nov25": "2025-11-30"}),
}
PC = ["Steam", "Epic Games", "Origin", "GOG.com", "Humble Bundle", "Green Man Gaming", "Ubisoft", "Blizzard Entertainment",
      "Riot Games", "Square Enix", "Minecraft"]
CHANNEL = {SEN: "PSN", MSS: "MS", "Nintendo": "Nintendo", "Roblox": "Roblox", "Rockstar Games": "Rockstar",
           "GameStop": "Retail", "Sony": "Retail", **{m: "PC" for m in PC}}

# ------------------------------------------------------------------ description classification (gaming merchants)
FUND = (r"WALLET FUNDS|WALLET CREDIT|GIFT CARD|DIGITAL GIFT|ACCOUNT BALANCE|EPIC WALLET|CREDIT TO MICROSOFT ACCOUNT|POSA|"
        r"BATTLE\.NET BALANCE|CREDIT REDEMPTION|ESHOP CARD|STORE CARD")
NONGAME = (r"MICROSOFT 365|\bOFFICE\b|WINDOWS 1\d|WINDOWS 10/11|SURFACE|COPILOT|ONEDRIVE|VIDEO EXTENSIONS|IMAGE EXTENSION|"
           r"CLIPCHAMP|\bVISIO\b|MICROSOFT PROJECT|SKYPE|\bTEAMS\b|DEFENDER|BY: MICROSOFT CORPORATION|BITDEFENDER|NORTON|MCAFEE|"
           r"BUSINESS (BASIC|STANDARD|PREMIUM)|PRODUCT REPLACEMENT|PROTECTION PLAN|TRADING CARD|POKEMON TCG|BOOSTER|ELITE TRAINER|"
           r"\bCAMERA\b|\bLENS\b|HEADPHONES|EARBUDS|\bBRAVIA\b|SOUNDBAR|ALPHA \d|\bFE \d|WH-1000|WF-1000|\bTV\b")
HW = (r"CONSOLE|STEAM DECK|PLAYSTATION.{0,3}PORTAL|PORTAL.{0,3}REMOTE PLAYER|PSVR|PS VR|PLAYSTATION.{0,3}VR|NINTENDO SWITCH 2$|"
      r"SWITCH 2 \+|SWITCH 2 CONSOLE|SWITCH OLED|^NINTENDO SWITCH$|SWITCH LITE")
SUB_PSPLUS = r"PLAYSTATION PLUS|PS PLUS"
SUB_GP = r"GAME PASS"
SUB_GTAP = r"GTA\+ ?\(SUBSCRIPTION|GTA\+ MEMBERSHIP|GTA\+ SUBSCRIPTION|^GTA\+$|^GTA\+ \((PS5|XBOX)|SUBSCRIPTION TO GTA\+"
SUB_OTHER = (r"EA PLAY|UBISOFT\+|FORTNITE CREW|SWITCH ONLINE|ROBLOX PREMIUM|^PREMIUM \d+ ROBUX|ROBLOX PLUS|GAMESTOP PRO|"
             r"XBOX LIVE|\(SUBSCRIPTION|SUBSCRIPTION TO |MEMBERSHIP|REALMS|VRCHAT\+|\bPASS\b.*MONTH")
VC = (r"V-BUCKS|ROBUX|POINTS|CREDITS|COINS|\bSTUBS\b|CURRENCY|MINECOIN|\bSILVER\b|ATOMS|LATTICE|CASH CARD|PLATINUM|EAGLES|CELLS|"
      r"GOLD BARS|\bRP\b|\bGEMS\b|SHARK CARD|BATTLE PASS|BLACKCELL|\bTOKENS?\b|ORBS|CRYSTALS|MOONSTONE|\bFUND\b|\bPACK\b")
ADDON = r"ADD-ON|UPGRADE|SEASON PASS|\bDLC\b|EXPANSION|AVATAR|THEME|SOUNDTRACK|\bBUNDLE\b.*PACK|COSMETIC|SKIN"
GTA = r"GRAND THEFT AUTO|\bGTA\b|GTA\+|SHARK CA(SH|RD)|GTA ONLINE"
GTA6 = r"GRAND THEFT AUTO[^A-Z0-9]{0,3}VI([^A-Z0-9]|$)"


def classify_desc(d):
    u = (d["DESCRIPTION"].fillna("").str.upper().str.replace("�", "", regex=False)
         .str.replace(r"[®™]", "", regex=True))
    m = d["MERCHANT_NAME"]
    cat = pd.Series("game_other", index=d.index)
    psn_tag = u.str.extract(r"\(([A-Z_\. -]+)\)?\s*(?:\(PRE-ORDER\))?\s*$")[0].fillna("")
    cat[u.str.contains(ADDON)] = "addon"
    cat[(m == SEN) & psn_tag.str.contains("ADD-ON|THEME|AVATAR|SOUNDTRACK")] = "addon"
    cat[u.str.contains(VC) | ((m == SEN) & psn_tag.eq("VIRTUAL CURRENCY")) |
        ((m == "Roblox") & ((u.str.contains("ROBUX") & ~u.str.contains("PREMIUM")) | u.eq("PAYMENT")))] = "vc"
    cat[u.str.contains(SUB_OTHER) | ((m == SEN) & psn_tag.str.contains("SUBSCRIPTION|STOREFRONT_CLASS.CLOUD"))] = "sub_other"
    cat[u.str.contains(SUB_GTAP)] = "sub_gtaplus"
    cat[u.str.contains(SUB_GP) & ~u.str.contains("PC GAME PASS")] = "sub_gamepass"
    cat[u.str.contains("PC GAME PASS")] = "sub_pcgamepass"
    cat[u.str.contains(SUB_PSPLUS)] = "sub_psplus"
    cat[(m == SEN) & psn_tag.isin(["APPLICATION", "APP", "STOREFRONT_CLASS.VIDEO"])] = "app"
    cat[(m == SEN) & psn_tag.str.contains("DEMO|BETA|TRIAL")] = "demo"
    cat[u.str.contains(HW) & ~u.str.contains(r"FOR (PS5|PLAYSTATION|XBOX)|GIFT") & (d["MED_PRICE"].fillna(0) >= 150)] = "hardware"
    cat[u.str.contains(FUND)] = "funding"
    cat[u.str.contains(NONGAME) & ~u.str.contains(r"GAME PASS|XBOX|BY: (XBOX|MICROSOFT STUDIOS)")] = "nongaming"
    cat[m.str.endswith("Cancellation")] = "cancellation"
    is_game = cat.eq("game_other") & ~((m == SEN) & ~psn_tag.isin(["GAME", "FULL GAME", "BUNDLE", "FULL GAME AND ADD-ON CONTENT",
                                                                   "DOWNLOADABLE GAME", "PRE-ORDER", ""]))
    gta = u.str.contains(GTA) & ~u.str.contains(GTA6)
    return pd.DataFrame({"CAT": cat, "IS_GAME": is_game, "GTA": gta,
                         "GTA_PLUS": cat.eq("sub_gtaplus"),
                         "PSP_TIER": np.select([u.str.contains("PREMIUM") & cat.eq("sub_psplus"),
                                                u.str.contains("EXTRA") & cat.eq("sub_psplus"),
                                                cat.eq("sub_psplus")], ["Premium", "Extra", "Essential"], ""),
                         "GP_TIER": np.select([u.str.contains("ULTIMATE") & cat.eq("sub_gamepass"),
                                               cat.eq("sub_gamepass")], ["Ultimate", "Core/Std/Ess/Prem"], "")},
                        index=d.index)


def load_gaming_rows():
    d = pd.read_parquet(C + "inv3_desc.parquet")
    d = pd.concat([d, classify_desc(d)], axis=1)
    r = pd.read_parquet(C + "inv3_rows.parquet")
    r = r.merge(d[["MERCHANT_NAME", "H", "DESCRIPTION", "CAT", "IS_GAME", "GTA", "GTA_PLUS", "PSP_TIER", "GP_TIER"]],
                on=["MERCHANT_NAME", "H"], how="left")
    r["ORDER_DATE"] = pd.to_datetime(r["ORDER_DATE"])
    r["V"] = r["ITEM_PRICE"].fillna(0) * r["ITEM_QUANTITY"].fillna(1).clip(lower=1)
    r["EPIC_FREE"] = (r["MERCHANT_NAME"] == "Epic Games") & r["ORDER_TOTAL"].eq(0)
    r.loc[r["EPIC_FREE"], "V"] = 0.0
    # non-USD storefront deflator per mailbox x merchant
    pos = r[r["ITEM_PRICE"] > 0]
    sku = pos.groupby(["MERCHANT_NAME", "H"])["ITEM_PRICE"].agg(MODE=lambda s: s.round(2).mode().iat[0], N="size")
    sku = sku[sku["N"] >= 200].reset_index()
    x = pos[["MAILBOX_ID", "MERCHANT_NAME", "H", "ITEM_PRICE"]].merge(sku, on=["MERCHANT_NAME", "H"])
    x["RAT"] = x["ITEM_PRICE"] / x["MODE"]
    fx = x.groupby(["MAILBOX_ID", "MERCHANT_NAME"])["RAT"].agg(["median", "size"])
    fx = fx[(fx["size"] >= 3) & fx["median"].between(1.2, 1.6)]["median"].rename("FX").reset_index()
    r = r.merge(fx, on=["MAILBOX_ID", "MERCHANT_NAME"], how="left")
    r["V_USD"] = r["V"] / r["FX"].fillna(1.0)
    r["CHANNEL"] = r["MERCHANT_NAME"].map(CHANNEL).fillna("Other")
    r["SPEND"] = ~r["CAT"].isin(["funding", "nongaming", "hardware", "cancellation"]) & (r["V_USD"] > 0)
    return r, d


def load_retail_rows():
    """PS/Xbox-labelled items at non-gaming retailers (Best Buy, Target, Walmart, Amazon, ...)."""
    d = pd.read_parquet(C + "desc_cls.parquet")
    keep = (d["AGN_PS"] | d["AGN_XB"] | d["INF_PS5"] | d["INF_XSX"] | d["INF_PS5_XGEN"] | d["INF_XSX_XGEN"]) \
        & ~d["IS_CANCEL"] & ~d["EXPLICIT_PS5"] & ~d["EXPLICIT_XSX"] & ~d["MERCHANT_NAME"].isin(list(CHANNEL) + [SEN, MSS])
    d = d[keep].copy()
    u = d["DESCRIPTION"].str.upper()
    d = d[~u.str.contains(HW + r"|GIFT|PREPAID|DIGITAL CODE.*\$|EGIFT|WALLET|STORE CARD|PSN CARD|USD ?\d+|\$\d+ |"
                                r"XBOX ONE [SX]\b|PLAYSTATION CLASSIC|RENTAL")
          & ~d["IS_MARKETPLACE"] & ~d["MERCHANT_NAME"].isin(["Redbox", "Amazon Luna", "Whatnot", "TikTok", "Mercari", "eBay",
                                                               "Etsy", "Temu", "OfferUp", "StockX", "Facebook"])]
    u = d["DESCRIPTION"].str.upper()
    acc = (r"CONTROLLER|WIRELESS|ELITE|PULSE|DUALSENSE|DUALSHOCK|HEADSET|CHARG|CABLE|\bSTAND\b|\bCASE\b|SKIN|COVER|DOCK|BATTERY|STEERING|WHEEL|MOUNT|"
           r"ADAPTER|\bDRIVE\b|SSD|REMOTE|CAMERA|KEYBOARD|MOUSE|COOLING|\bFAN\b|MICROPHONE|MONITOR|\bBAG\b|LIGHT|SPEAKER|GRIP|"
           r"THUMB|EXPANSION CARD|MEMORY|STORAGE|EARBUD|HEADPHONE|PLATE|DECAL|STICKER|SHIRT|HOODIE|FIGURE|AMIIBO")
    d["CAT"] = np.select([u.str.contains(SUB_PSPLUS + "|" + SUB_GP + r"|XBOX LIVE"), u.str.contains(acc),
                          u.str.contains(VC)], ["sub_other", "accessory", "vc"], "game_other")
    d["IS_GAME"] = d["CAT"].eq("game_other")
    d["GTA"] = u.str.contains(GTA) & ~u.str.contains(GTA6)
    r = pd.read_parquet(C + "rows.parquet")
    r = r.merge(d[["MERCHANT_NAME", "H", "DESCRIPTION", "CAT", "IS_GAME", "GTA", "IS_MARKETPLACE"]], on=["MERCHANT_NAME", "H"])
    r["ORDER_DATE"] = pd.to_datetime(r["ORDER_DATE"])
    p = r["ITEM_PRICE"]
    r = r[p.isna() | (p < 300)]                        # remove residual hardware / bulk
    r["V_USD"] = r["ITEM_PRICE"].fillna(0)
    r["CHANNEL"] = "Retail"
    r["SPEND"] = r["V_USD"] > 0
    r["ORDER_ID"] = r["MAILBOX_ID"] + "|" + r["MERCHANT_NAME"] + "|" + r["ORDER_DATE"].astype(str)
    for c in ["GTA_PLUS"]:
        r[c] = False
    r["PSP_TIER"] = ""; r["GP_TIER"] = ""; r["EPIC_FREE"] = False
    return r


# ------------------------------------------------------------------ bases and outcomes (as gta6_penetration.py)
def explicit_rows():
    d = pd.read_parquet(C + "desc_cls.parquet")[["MERCHANT_NAME", "H", "EXPLICIT_PS5", "EXPLICIT_XSX"]]
    r = pd.read_parquet(C + "rows.parquet", columns=["MAILBOX_ID", "MERCHANT_NAME", "H", "ORDER_DATE", "ITEM_PRICE"])
    r = r.merge(d, on=["MERCHANT_NAME", "H"])
    r = r[r["EXPLICIT_PS5"] | r["EXPLICIT_XSX"]]
    p = r["ITEM_PRICE"]
    r = r[p.isna() | p.eq(0) | p.between(150, 2000)]
    r["ORDER_DATE"] = pd.to_datetime(r["ORDER_DATE"])
    return r


def platform(df):
    u = df["DESCRIPTION"].str.upper()
    plat = pd.Series(None, index=df.index, dtype=object)
    plat[u.str.contains("XBOX|SERIES X")] = "XSX"
    plat[u.str.contains("PS5|PLAYSTATION")] = "PS5"
    plat[df["MERCHANT_NAME"] == SEN] = "PS5"
    plat[df["MERCHANT_NAME"] == MSS] = "XSX"
    return plat


def game_buyers(game):
    if game == "GTA6":
        g = pd.read_parquet(C + "gta6.parquet")
    else:
        g = pd.read_parquet(C + "bf6.parquet")
        g = g[~g["DESCRIPTION"].str.upper().str.contains(
            r"BETA|PACK|BFC|ADD-ON|TEXTURE|SHARED DATA|SINGLE PLAYER|MULTIPLAYER|MARKER|PRO -|BUNDLE|UPGRADE|SEASON")
              & ~g["MERCHANT_NAME"].isin(["Steam", "Origin", "Epic Games", "Google Play"])
              & (g["ITEM_PRICE"].isna() | g["ITEM_PRICE"].between(40, 130))]
    g = g.assign(ORDER_DATE=pd.to_datetime(g["ORDER_DATE"]), PLAT=platform(g))
    g = g[g["PLAT"].notna()]
    return g.groupby("MAILBOX_ID").agg(FIRST=("ORDER_DATE", "min"),
                                       VIA_STORE=("MERCHANT_NAME", lambda s: s.isin([SEN, MSS]).any()))


# ------------------------------------------------------------------ per-mailbox features
def features(rows, base_ids, open_):
    w0, w1 = open_ - pd.Timedelta(days=365), open_ - pd.Timedelta(days=2)
    x = rows[rows["MAILBOX_ID"].isin(base_ids) & rows["ORDER_DATE"].between(w0, w1)]
    s = x[x["SPEND"]]
    f = pd.DataFrame(index=pd.Index(sorted(base_ids), name="MAILBOX_ID"))
    piv = s.pivot_table(index="MAILBOX_ID", columns="CHANNEL", values="V_USD", aggfunc="sum")
    for ch in ["PSN", "MS", "PC", "Nintendo", "Roblox", "Rockstar", "Retail"]:
        f["USD_" + ch] = piv[ch] if ch in piv else 0.0
    f = f.fillna(0.0)
    f["USD_STORE"] = f["USD_PSN"] + f["USD_MS"]
    f["USD_CONSOLE"] = f["USD_STORE"] + f["USD_Retail"]
    f["USD_ALL"] = f[[c for c in f if c.startswith("USD_") and c not in ("USD_STORE", "USD_CONSOLE")]].sum(axis=1)
    cat = s.pivot_table(index="MAILBOX_ID", columns="CAT", values="V_USD", aggfunc="sum").fillna(0)
    for c in ["game_other", "vc", "addon", "sub_psplus", "sub_gamepass", "sub_pcgamepass", "sub_gtaplus", "sub_other", "accessory"]:
        f["CAT_" + c] = cat[c] if c in cat else 0.0
    f = f.fillna(0.0)
    f["N_TXN"] = s.groupby("MAILBOX_ID")["ORDER_ID"].nunique().reindex(f.index).fillna(0)
    f["N_TXN_STORE"] = s[s["CHANNEL"].isin(["PSN", "MS"])].groupby("MAILBOX_ID")["ORDER_ID"].nunique().reindex(f.index).fillna(0)
    f["N_MONTHS"] = s.groupby("MAILBOX_ID")["ORDER_DATE"].apply(lambda d: d.dt.to_period("M").nunique()).reindex(f.index).fillna(0)
    last = s.groupby("MAILBOX_ID")["ORDER_DATE"].max()
    f["DAYS_SINCE"] = ((open_ - last).dt.days).reindex(f.index)
    aaa = s[s["IS_GAME"] & s["V_USD"].between(59.0, 150) & s["CAT"].eq("game_other")]
    f["N_AAA"] = aaa.groupby("MAILBOX_ID")["ORDER_ID"].nunique().reindex(f.index).fillna(0)
    f["N_AAA_STORE"] = aaa[aaa["CHANNEL"].isin(["PSN", "MS"])].groupby("MAILBOX_ID")["ORDER_ID"].nunique().reindex(f.index).fillna(0)
    any_ = x.groupby("MAILBOX_ID")
    f["ANY_ROW"] = any_.size().reindex(f.index).fillna(0) > 0
    f["ANY_STORE_ROW"] = x[x["CHANNEL"].isin(["PSN", "MS"])].groupby("MAILBOX_ID").size().reindex(f.index).fillna(0) > 0
    f["ZERO_ONLY_STORE"] = f["ANY_STORE_ROW"] & (f["USD_STORE"] == 0)
    g = x[x["GTA"] | x["GTA_PLUS"]]
    f["GTA_ANY"] = f.index.isin(g["MAILBOX_ID"])
    f["GTA_PAID"] = f.index.isin(g.loc[g["SPEND"], "MAILBOX_ID"])
    f["GTA_PLUS"] = f.index.isin(g.loc[g["GTA_PLUS"], "MAILBOX_ID"])
    f["GTA_SHARK"] = f.index.isin(g.loc[g["DESCRIPTION"].str.upper().str.contains("SHARK"), "MAILBOX_ID"])
    f["ROCKSTAR_ROW"] = f.index.isin(x.loc[x["MERCHANT_NAME"] == "Rockstar Games", "MAILBOX_ID"])
    sub = x[x["CAT"].str.startswith("sub_") & (x["V_USD"] > 0)]
    f["SUB_PSPLUS"] = f.index.isin(sub.loc[sub["CAT"] == "sub_psplus", "MAILBOX_ID"])
    f["SUB_PSP_TIER"] = sub[sub["CAT"] == "sub_psplus"].groupby("MAILBOX_ID")["PSP_TIER"].agg(
        lambda t: "Premium" if (t == "Premium").any() else ("Extra" if (t == "Extra").any() else "Essential")).reindex(f.index).fillna("")
    f["SUB_GAMEPASS"] = f.index.isin(sub.loc[sub["CAT"] == "sub_gamepass", "MAILBOX_ID"])
    f["SUB_GPU"] = f.index.isin(sub.loc[sub["GP_TIER"] == "Ultimate", "MAILBOX_ID"])
    f["SUB_OTHER"] = f.index.isin(sub.loc[sub["CAT"].isin(["sub_other", "sub_pcgamepass", "sub_gtaplus"]), "MAILBOX_ID"])
    f["FX_ADJ"] = f.index.isin(x.loc[x["FX"].notna(), "MAILBOX_ID"]) if "FX" in x else False
    return f


def auc(score, y):
    """Mann-Whitney AUC with ties = 0.5."""
    rk = pd.Series(score).rank(method="average").values
    y = np.asarray(y, bool)
    n1, n0 = y.sum(), (~y).sum()
    return (rk[y].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)


def pen_table(f, col, ycols, order=None):
    t = f.groupby(col, observed=True).agg(n=(ycols[0], "size"), **{y: (y, "mean") for y in ycols})
    for y in ycols:
        t[y] = (100 * t[y]).round(2)
        t["lift_" + y] = (t[y] / (100 * f[y].mean())).round(2)
    t["share_%"] = (100 * t["n"] / len(f)).round(1)
    if order is not None:
        t = t.reindex([o for o in order if o in t.index])
    return t


BUCKETS = [-0.01, 0, 50, 100, 250, 500, 1000, 1e9]
BLAB = ["$0", "$1-50", "$50-100", "$100-250", "$250-500", "$500-1000", "$1000+"]


def cohort_cols(f):
    f["B_ALL"] = pd.cut(f["USD_ALL"], BUCKETS, labels=BLAB)
    f["B_STORE"] = pd.cut(f["USD_STORE"], BUCKETS, labels=BLAB)
    f["B_CONSOLE"] = pd.cut(f["USD_CONSOLE"], BUCKETS, labels=BLAB)
    pos = f["USD_ALL"] > 0
    f["DEC_ALL"] = "D0 ($0)"
    f.loc[pos, "DEC_ALL"] = "D" + (pd.qcut(f.loc[pos, "USD_ALL"].rank(method="first"), 10, labels=False) + 1).astype(str).str.zfill(2)
    pos = f["USD_STORE"] > 0
    f["DEC_STORE"] = np.where(f["ZERO_ONLY_STORE"], "D0 ($0 rows only)", "D0 (no store row)")
    f.loc[pos, "DEC_STORE"] = "D" + (pd.qcut(f.loc[pos, "USD_STORE"].rank(method="first"), 10, labels=False) + 1).astype(str).str.zfill(2)
    f["B_TXN"] = pd.cut(f["N_TXN"], [-1, 0, 2, 5, 12, 25, 1e9], labels=["0", "1-2", "3-5", "6-12", "13-25", "26+"])
    f["B_MONTHS"] = pd.cut(f["N_MONTHS"], [-1, 0, 2, 5, 9, 12], labels=["0", "1-2", "3-5", "6-9", "10-12"])
    f["B_REC"] = pd.cut(f["DAYS_SINCE"].fillna(9999), [0, 30, 90, 180, 365, 1e9],
                        labels=["<=30d", "31-90d", "91-180d", "181-365d", "none in 12m"])
    f["B_AAA"] = pd.cut(f["N_AAA"], [-1, 0, 1, 2, 4, 1e9], labels=["0", "1", "2", "3-4", "5+"])
    f["B_GTA"] = np.select([f["GTA_PLUS"], f["GTA_SHARK"], f["GTA_PAID"], f["GTA_ANY"] | f["ROCKSTAR_ROW"]],
                           ["GTA+ subscriber", "Shark Cards (no GTA+)", "other paid GTA (V/Online)", "GTA $0 row / Rockstar acct"],
                           "no GTA signal")
    f["B_SUB"] = np.select([f["SUB_PSPLUS"] & f["SUB_GAMEPASS"], f["SUB_PSP_TIER"].isin(["Premium", "Extra"]),
                            f["SUB_PSP_TIER"].eq("Essential"), f["SUB_GPU"], f["SUB_GAMEPASS"], f["SUB_OTHER"]],
                           ["PS Plus + Game Pass", "PS Plus Extra/Premium", "PS Plus Essential", "Game Pass Ultimate",
                            "Game Pass other tier", "other gaming sub only"], "no paid sub")
    return f


def main():
    import os
    os.makedirs(OUT, exist_ok=True)
    gr, gdesc = load_gaming_rows()
    rr = load_retail_rows()
    cols = ["MAILBOX_ID", "MERCHANT_NAME", "ORDER_ID", "ORDER_DATE", "DESCRIPTION", "V_USD", "CHANNEL", "SPEND", "CAT",
            "IS_GAME", "GTA", "GTA_PLUS", "PSP_TIER", "GP_TIER", "FX"]
    rr["FX"] = np.nan
    rows = pd.concat([gr[cols], rr[cols]], ignore_index=True)
    rows.to_parquet(C + "inv3_rows_cls.parquet")
    print("rows:", len(rows), "| category $ (gaming merchants, all panel, full pull):")
    print((gr.groupby(["CHANNEL", "CAT"])["V"].sum() / 1e6).round(2).unstack(fill_value=0).to_string())

    ex = explicit_rows()
    mb = pd.read_parquet(C + "mailboxes.parquet")
    mb["ENTRY_DATE"] = pd.to_datetime(mb["ENTRY_DATE"])
    mb = mb[mb["IN_PANEL_61212"] == 1].set_index("MAILBOX_ID")
    store = pd.read_parquet(C + "store_mb.parquet")
    store["FIRST_DATE"] = pd.to_datetime(store["FIRST_DATE"])

    allf = {}
    for game, cfg in GAMES.items():
        open_ = pd.Timestamp(cfg["open"])
        pre = ex[ex["ORDER_DATE"] < open_ - pd.Timedelta(days=1)]
        ps5, xsx = set(pre.loc[pre["EXPLICIT_PS5"], "MAILBOX_ID"]), set(pre.loc[pre["EXPLICIT_XSX"], "MAILBOX_ID"])
        joined = set(mb.index[mb["ENTRY_DATE"] < open_])
        base = (ps5 | xsx) & joined
        f = features(rows, base, open_)
        f["PLAT"] = np.where(f.index.isin(ps5) & f.index.isin(xsx), "both", np.where(f.index.isin(ps5), "PS5", "XSX"))
        f["FULL12"] = mb.loc[f.index, "ENTRY_DATE"] <= open_ - pd.Timedelta(days=365)
        vis = set(store.loc[store["FIRST_DATE"] < open_ - pd.Timedelta(days=1), "MAILBOX_ID"])
        f["STORE_VISIBLE_EVER"] = f.index.isin(vis)
        b = game_buyers(game)
        for oname, odate in cfg["outcomes"].items():
            f["Y_" + oname] = f.index.isin(b.index[b["FIRST"] <= pd.Timestamp(odate)])
        f = cohort_cols(f)
        f.to_parquet(f"{OUT}features_{game}.parquet")
        allf[game] = f
        print(f"\n{game}: base {len(f):,}  " + "  ".join(f"{k} {100*f[k].mean():.2f}%" for k in f if k.startswith("Y_")))
    return allf


def md(t, index=True):
    t = t.reset_index() if index else t
    cols = [str(c) for c in t.columns]
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for _, r in t.iterrows():
        lines.append("| " + " | ".join("" if pd.isna(v) else (f"{v:,.2f}".rstrip("0").rstrip(".") if isinstance(v, float) else str(v))
                                       for v in r.values) + " |")
    return "\n".join(lines)


Y = {"GTA6": ["Y_by_26Oct26"], "BF6": ["Y_by_L-23_17Sep25", "Y_by_30Nov25"]}


def analyse(allf):
    rep = []
    for game, f in allf.items():
        rep.append(f"\n## {game} base n={len(f):,}\n")
        d = {"any gaming $ (12m)": (f["USD_ALL"] > 0).mean(), "any PSN/MS $": (f["USD_STORE"] > 0).mean(),
             "any PSN/MS row (incl $0)": f["ANY_STORE_ROW"].mean(), "PSN/MS $0 rows only": f["ZERO_ONLY_STORE"].mean(),
             "store-visible ever (pre-open)": f["STORE_VISIBLE_EVER"].mean(), "full 12m tenure": f["FULL12"].mean(),
             "FX-adjusted (non-USD) mailbox": f["FX_ADJ"].mean()}
        for ch in ["PSN", "MS", "PC", "Nintendo", "Roblox", "Rockstar", "Retail"]:
            d[f"any {ch} $"] = (f["USD_" + ch] > 0).mean()
        rep.append(md(pd.Series(d).mul(100).round(1).rename("%").to_frame()))
        qs = [.1, .25, .5, .75, .9, .95, .99, .999]
        dist = pd.DataFrame({c: f.loc[f[c] > 0, c].quantile(qs) for c in ["USD_ALL", "USD_STORE", "USD_CONSOLE", "N_TXN", "N_AAA"]})
        dist.loc["mean (spenders)"] = [f.loc[f[c] > 0, c].mean() for c in dist]
        dist.loc["mean (all base)"] = [f[c].mean() for c in dist]
        dist.loc["max"] = [f[c].max() for c in dist]
        rep.append("\nPercentiles among mailboxes with >0:\n" + md(dist.round(1)))
        sh = f[[c for c in f if c.startswith("USD_") and c not in ("USD_ALL", "USD_STORE", "USD_CONSOLE")]].sum()
        rep.append("\nChannel share of base $: " + ", ".join(f"{k[4:]} {100*v/sh.sum():.0f}%" for k, v in sh.items()))
        cs = f[[c for c in f if c.startswith("CAT_")]].sum()
        rep.append("\nCategory share of base $: " + ", ".join(f"{k[4:]} {100*v/cs.sum():.0f}%" for k, v in cs.items()))
        ys = Y[game]
        for col, order in [("B_ALL", BLAB), ("B_STORE", BLAB), ("B_CONSOLE", BLAB), ("DEC_ALL", None), ("DEC_STORE", None),
                           ("B_TXN", None), ("B_MONTHS", None), ("B_REC", None), ("B_AAA", None), ("B_GTA", None),
                           ("B_SUB", None), ("PLAT", None)]:
            t = pen_table(f, col, ys, order)
            if col.startswith("DEC"):
                v = "USD_ALL" if col == "DEC_ALL" else "USD_STORE"
                t["min$"] = f.groupby(col)[v].min().round(0)
                t["med$"] = f.groupby(col)[v].median().round(0)
            t.to_csv(f"{OUT}{game}_{col}.csv")
            rep.append(f"\n### {game} by {col}\n" + md(t))
        v = f[f["STORE_VISIBLE_EVER"]]
        rep.append(f"\n### {game} by B_STORE, store-visible-ever subset (n={len(v):,})\n" + md(pen_table(v, "B_STORE", ys, BLAB)))
        v = f[f["FULL12"]]
        rep.append(f"\n### {game} by B_ALL, full-12m-tenure subset (n={len(v):,})\n" + md(pen_table(v, "B_ALL", ys, BLAB)))
        mets = {"USD_ALL": f["USD_ALL"], "USD_STORE": f["USD_STORE"], "USD_CONSOLE": f["USD_CONSOLE"], "USD_PSN": f["USD_PSN"],
                "USD_MS": f["USD_MS"], "USD_PC": f["USD_PC"], "N_TXN": f["N_TXN"], "N_TXN_STORE": f["N_TXN_STORE"],
                "N_MONTHS": f["N_MONTHS"], "recency (-days)": -f["DAYS_SINCE"].fillna(9999), "N_AAA": f["N_AAA"],
                "N_AAA_STORE": f["N_AAA_STORE"], "CAT_vc $": f["CAT_vc"], "CAT_game $": f["CAT_game_other"],
                "GTA engagement (ordinal)": f["B_GTA"].map({"GTA+ subscriber": 4, "Shark Cards (no GTA+)": 3,
                                                            "other paid GTA (V/Online)": 2, "GTA $0 row / Rockstar acct": 1}).fillna(0),
                "any paid sub": (f["B_SUB"] != "no paid sub").astype(int),
                "store-visible ever": f["STORE_VISIBLE_EVER"].astype(int)}
        a = pd.DataFrame({"coverage_%": {k: round(100 * (m > 0).mean(), 1) if not k.startswith("recency") else
                                         round(100 * f["DAYS_SINCE"].notna().mean(), 1) for k, m in mets.items()}})
        vv = f["STORE_VISIBLE_EVER"].values
        for y in ys:
            a["AUC " + y] = {k: round(auc(m.values, f[y].values), 3) for k, m in mets.items()}
            a["AUC visible-only " + y] = {k: round(auc(m.values[vv], f[y].values[vv]), 3) for k, m in mets.items()}
        a.to_csv(f"{OUT}{game}_auc.csv")
        rep.append(f"\n### {game} AUC (rank predictive power, 0.5 = none)\n" + md(a))
    cands = {
        "all explicit owners": lambda f: pd.Series(True, index=f.index),
        "any gaming $ > 0": lambda f: f["USD_ALL"] > 0,
        "PSN/MS $ > 0": lambda f: f["USD_STORE"] > 0,
        "gaming $ >= 100": lambda f: f["USD_ALL"] >= 100,
        "gaming $ >= 250": lambda f: f["USD_ALL"] >= 250,
        "gaming $ >= 500": lambda f: f["USD_ALL"] >= 500,
        "PSN/MS $ >= 100": lambda f: f["USD_STORE"] >= 100,
        "PSN/MS $ >= 250": lambda f: f["USD_STORE"] >= 250,
        "PSN/MS $ >= 500": lambda f: f["USD_STORE"] >= 500,
        "top decile gaming $ (base-relative)": lambda f: f["USD_ALL"] >= f["USD_ALL"].quantile(.9),
        "top quintile gaming $": lambda f: f["USD_ALL"] >= f["USD_ALL"].quantile(.8),
        "AAA >= 1": lambda f: f["N_AAA"] >= 1,
        "AAA >= 2": lambda f: f["N_AAA"] >= 2,
        "AAA >= 3": lambda f: f["N_AAA"] >= 3,
        "active months >= 6": lambda f: f["N_MONTHS"] >= 6,
        "purchased in last 90d": lambda f: f["DAYS_SINCE"] <= 90,
        "GTA paid (V/Online/Shark/GTA+)": lambda f: f["GTA_PAID"] | f["GTA_PLUS"],
        "paid sub (PS Plus/Game Pass/other)": lambda f: f["B_SUB"] != "no paid sub",
        "AAA>=1 & gaming $>=250": lambda f: (f["N_AAA"] >= 1) & (f["USD_ALL"] >= 250),
        "AAA>=2 | GTA paid": lambda f: (f["N_AAA"] >= 2) | f["GTA_PAID"] | f["GTA_PLUS"],
        "core: AAA>=1 | GTA paid | PSN/MS $>=250": lambda f: (f["N_AAA"] >= 1) | f["GTA_PAID"] | f["GTA_PLUS"] | (f["USD_STORE"] >= 250),
    }
    rows = []
    for name, fn in cands.items():
        row = {"cohort": name}
        for game, f in allf.items():
            msk = fn(f)
            yy = Y[game][-1]
            row[f"{game} n"] = int(msk.sum()); row[f"{game} %base"] = round(100 * msk.mean(), 1)
            row[f"{game} pen%"] = round(100 * f.loc[msk, yy].mean(), 2)
            row[f"{game} lift"] = round(f.loc[msk, yy].mean() / f[yy].mean(), 2)
            row[f"{game} %buyers"] = round(100 * f.loc[msk, yy].sum() / f[yy].sum(), 1)
            if game == "BF6":
                row["BF6 L-23 pen%"] = round(100 * f.loc[msk, Y[game][0]].mean(), 2)
        rows.append(row)
    ct = pd.DataFrame(rows)
    ct.to_csv(f"{OUT}candidate_cohorts.csv", index=False)
    rep.append("\n## Candidate cohorts (GTA6 by 26 Oct 2026; BF6 by 30 Nov 2025, plus L-23)\n" + md(ct, index=False))
    g, b = allf["GTA6"], allf["BF6"]
    both = g.index.intersection(b.index)
    st = pd.DataFrame({"BF6yr": b.loc[both, "B_ALL"].astype(str), "GTAyr": g.loc[both, "B_ALL"].astype(str)})
    tr = pd.crosstab(st["BF6yr"], st["GTAyr"], normalize="index").reindex(index=BLAB, columns=BLAB).mul(100).round(0)
    rep.append(f"\n## Stability: gaming-$ bucket in BF6 window (rows) vs GTA window (cols), n={len(both):,}, row %\n" + md(tr))
    rho = np.corrcoef(b.loc[both, "USD_ALL"].rank(), g.loc[both, "USD_ALL"].rank())[0, 1]
    rep.append(f"\nSpearman rank corr of 12m gaming $ across the two windows: {rho:.2f}")
    t = g.loc[both].assign(BF6_BUYER=b.loc[both, "Y_by_30Nov25"].values, B_ALL_PRIOR=b.loc[both, "B_ALL"].values,
                           AAA_PRIOR=b.loc[both, "B_AAA"].values)
    rep.append("\n### GTA6 penetration by prior-year (BF6-window) gaming $ bucket\n" + md(pen_table(t, "B_ALL_PRIOR", ["Y_by_26Oct26"], BLAB)))
    rep.append("\n### GTA6 penetration by prior-year AAA count\n" + md(pen_table(t, "AAA_PRIOR", ["Y_by_26Oct26"])))
    rep.append("\n### GTA6 penetration by BF6 console purchase\n" + md(pen_table(t, "BF6_BUYER", ["Y_by_26Oct26"])))
    open(f"{OUT}tables.md", "w", encoding="utf-8").write("\n".join(rep))
    print("\n".join(rep))


def dq(allf):
    """Data-quality numbers for the notes (GTA base, GTA window)."""
    r = pd.read_parquet(C + "inv3_rows_cls.parquet")
    g = r[r["MAILBOX_ID"].isin(allf["GTA6"].index) & r["ORDER_DATE"].between("2025-06-25", "2026-06-23")]
    out = []
    t = g.groupby(["CHANNEL", "CAT"]).agg(rows=("V_USD", "size"), usd=("V_USD", "sum"), zero=("V_USD", lambda v: (v == 0).sum()))
    t["usd"] = t["usd"].round(0)
    out.append("### Rows / $ by channel x category (GTA base, GTA window; before exclusions)\n" + md(t))
    f = allf["GTA6"]
    top = f.sort_values("USD_ALL", ascending=False).head(15)[
        ["USD_ALL", "USD_PSN", "USD_MS", "USD_PC", "USD_Nintendo", "USD_Roblox", "USD_Retail", "N_TXN", "N_AAA", "CAT_vc", "Y_by_26Oct26"]]
    out.append("\n### Top 15 spenders (GTA base)\n" + md(top.round(0)))
    open(f"{OUT}dq.md", "w", encoding="utf-8").write("\n".join(out))
    print("\n".join(out))


TIERS = {
    "gaming$ tier (all channels)": lambda f: pd.cut(f["USD_ALL"], [-0.01, 0, 250, 500, 1e9],
                                                    labels=["none ($0)", "light ($1-250)", "mid ($250-500)", "high ($500+)"]),
    "PSN/MS$ tier": lambda f: pd.Series(np.select([~f["ANY_STORE_ROW"], f["USD_STORE"] == 0, f["USD_STORE"] < 250, f["USD_STORE"] < 500],
                                                  ["no store row", "store $0 rows only", "light ($1-250)", "mid ($250-500)"],
                                                  "high ($500+)"), index=f.index),
    "AAA count tier": lambda f: pd.cut(f["N_AAA"], [-1, 0, 1, 1e9], labels=["0", "1", "2+"]),
}


def extras(allf):
    rep = []
    for name, fn in TIERS.items():
        parts = []
        for game, f in allf.items():
            yy = Y[game][-1]
            t = f.assign(T=fn(f)).groupby("T", observed=True).agg(n=(yy, "size"), pen=(yy, "mean"), buyers=(yy, "sum"))
            t["%base"] = (100 * t["n"] / len(f)).round(1); t["pen%"] = (100 * t["pen"]).round(2)
            t["lift"] = (t["pen"] / f[yy].mean()).round(2); t["%buyers"] = (100 * t["buyers"] / f[yy].sum()).round(1)
            parts.append(t[["n", "%base", "pen%", "lift", "%buyers"]].add_prefix(game + " "))
        rep.append(f"\n### Recommended tier: {name}\n" + md(pd.concat(parts, axis=1)))
    for game, f in allf.items():
        yy = Y[game][-1]
        res = (f["USD_Retail"] >= 5000) | (f["N_AAA"] >= 30)
        rep.append(f"\n{game}: probable reseller / bulk buyers (retail $>=5k or >=30 AAA in 12m): {res.sum()} mailboxes, "
                   f"pen {100*f.loc[res, yy].mean():.1f}%; mean gaming $ with/without them {f['USD_ALL'].mean():.0f} / "
                   f"{f.loc[~res, 'USD_ALL'].mean():.0f}")
        t = f.groupby(["PLAT", "B_STORE"], observed=True)[yy].agg(["size", "mean"])
        t["mean"] = (100 * t["mean"]).round(2)
        rep.append(f"\n### {game} by platform x PSN/MS $ bucket (pen %)\n" + md(t["mean"].unstack().reindex(columns=BLAB)))
        ex_vc = f["USD_ALL"] - f["CAT_vc"]
        rep.append(f"{game} AUC gaming $ excl. virtual currency: {auc(ex_vc.values, f[yy].values):.3f}; "
                   f"store $ + AAA>=2 combined score: {auc((f['USD_STORE'].rank() + 0.5 * f['N_AAA'].rank()).values, f[yy].values):.3f}")
    open(f"{OUT}extras.md", "w", encoding="utf-8").write("\n".join(rep))
    print("\n".join(rep))


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "extras":
        extras({g: pd.read_parquet(f"{OUT}features_{g}.parquet") for g in GAMES})
        sys.exit()
    if len(sys.argv) > 1 and sys.argv[1] == "analyse":
        allf = {g: pd.read_parquet(f"{OUT}features_{g}.parquet") for g in GAMES}
    else:
        allf = main()
    analyse(allf)
    dq(allf)
    extras(allf)
