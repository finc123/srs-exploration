"""Steam share of card spend (Earnest US, Fable EU5) vs Steam share of mailbox spend (Slice US, Fox EU5): quarterly share Y/Y
and trailing-91-day share Y/Y (364-day shift), same regional weighting as the web page."""
from datetime import date, timedelta
from pathlib import Path
import polars as pl

pl.Config.set_tbl_rows(40); pl.Config.set_tbl_cols(-1); pl.Config.set_tbl_width_chars(250)
D = Path(__file__).resolve().parent.parent / "data"
POP = {"US": 335.0, "UK": 68.3, "DE": 84.5, "FR": 68.4, "IT": 59.0, "ES": 48.6}
EU5 = ["UK", "DE", "FR", "IT", "ES"]
REGIONS = {"US": ["US"], "EU5": EU5}
TYPES = ["game", "edition", "dlc", "ingame", "sub", "hardware", "wallet"]
END = {"US": date(2026, 11, 15), **{c: date(2026, 11, 8) for c in EU5}}   # e-receipt last complete days
SHIFT = 364

# ---- card daily (country, date, steam, total) ----
us = pl.read_parquet(D / "card_steam_us.parquet").with_columns(country=pl.lit("US"), date=pl.col("date").cast(pl.Date),
                                                               steam=pl.col("steam").cast(pl.Float64), total=pl.col("total").cast(pl.Float64))
eu_raw = pl.read_parquet(D / "card_steam_eu.parquet").with_columns(pl.col("date").cast(pl.Date))
print("Fable spend by transaction type, 2025 (share of consumer debits, and Steam):")
print(eu_raw.filter(pl.col("date").dt.year() == 2025).group_by("country", "txntype").agg(pl.col("total", "steam").sum())
      .with_columns(pct=(pl.col("total") / pl.col("total").sum().over("country") * 100).round(1)).filter(pl.col("pct") > 1)
      .sort("country", "pct", descending=[False, True]))
CARD_TYPES = ["CARD PAYMENT"]
eu = (eu_raw.filter(pl.col("txntype").is_in(CARD_TYPES)).group_by("country", "date").agg(pl.col("steam", "total").sum()))
card = pl.concat([us.select("country", "date", "steam", "total"), eu.select("country", "date", "steam", "total")])
# vetted tables: Consumer Edge MU aggregate (US) and Fable's srs aggregate (EU5; same panel per country as the raw pull:
# FR on V3, the rest on V2), all source types and channels, Steam = 'steam games' tag over all merchant tags
FABLE_PANEL = {"UK": ("EU V2", "United Kingdom"), "DE": ("EU V2", "Germany"), "FR": ("EU V3", "France"), "IT": ("EU V2", "Italy"), "ES": ("EU V2", "Spain")}
mu = pl.read_parquet(D / "card_steam_us_mu.parquet").with_columns(country=pl.lit("US"), date=pl.col("date").cast(pl.Date),
                                                                 steam=pl.col("steam").cast(pl.Float64), total=pl.col("total").cast(pl.Float64))
agg_raw = pl.read_parquet(D / "card_steam_eu_agg.parquet").with_columns(pl.col("date").cast(pl.Date))
agg = pl.concat([agg_raw.filter(pl.col("panel") == pn, pl.col("country") == name).group_by("date").agg(pl.col("steam", "total").sum())
                 .with_columns(country=pl.lit(c)) for c, (pn, name) in FABLE_PANEL.items()])
vetted = pl.concat([mu.select("country", "date", "steam", "total"), agg.select("country", "date", "steam", "total")])

# ---- e-receipt daily ----
st = (pl.read_parquet(D / "steam_daily_types.parquet").pivot("grp", index=["country", "order_date"], values="spend", aggregate_function="sum")
      .fill_null(0.0))
tot = pl.read_parquet(D / "mailbox_total_daily.parquet")
rec = (tot.join(st, on=["country", "order_date"], how="left").fill_null(0.0).rename({"order_date": "date"})
       .with_columns(all_=pl.sum_horizontal([t for t in TYPES if t in st.columns]),
                     excl=pl.sum_horizontal([t for t in TYPES if t in st.columns and t != "wallet"])))

def cut(df, end_map):   # common end per region so card and receipt compare the same days
    return pl.concat([df.filter(pl.col("country") == c, pl.col("date") <= e) for c, e in end_map.items()])

CARD_END = {c: min(df.filter(pl.col("country") == c)["date"].max() for df in (card, vetted)) for c in POP}
print("card last day:", {c: str(d) for c, d in CARD_END.items()})
# card days settle late: drop the last 10 days of each card panel; compare on the earlier of the two ends
E = {c: min(END[c], CARD_END[c] - timedelta(days=10)) for c in POP}
E = {c: min(E[k] for k in (["US"] if c == "US" else EU5)) for c in POP}
print("comparison ends:", {c: str(d) for c, d in E.items()})

def quarterly(df, steam_col):
    d = cut(df.select("country", "date", steam=pl.col(steam_col), total="total"), E)
    prior = d.select("country", date=pl.col("date") + timedelta(days=SHIFT), steam_ly="steam", total_ly="total")
    d = d.join(prior, on=["country", "date"], how="left").with_columns(q=pl.col("date").dt.truncate("1q"))
    out = []
    for r, cs in REGIONS.items():
        g = (d.filter(pl.col("country").is_in(cs)).group_by("country", "q").agg(pl.col("steam", "total", "steam_ly", "total_ly").sum())
             .with_columns(s=pl.col("steam") / pl.col("total"), s_ly=pl.col("steam_ly") / pl.col("total_ly"),
                           w=pl.col("country").replace_strict(POP, return_dtype=pl.Float64))
             .group_by("q").agg(share=(pl.col("s") * pl.col("w")).sum() / pl.col("w").sum(), share_ly=(pl.col("s_ly") * pl.col("w")).sum() / pl.col("w").sum()))
        out.append(g.with_columns(region=pl.lit(r)))
    return pl.concat(out).with_columns(yoy=pl.col("share") / pl.col("share_ly") - 1)

def rolling(df, steam_col, w=91):
    d = (cut(df.select("country", "date", steam=pl.col(steam_col), total="total"), E).sort("country", "date")
         .with_columns(pl.col("steam", "total").rolling_sum(w).over("country")).with_columns(s=pl.col("steam") / pl.col("total")))
    d = d.join(d.select("country", date=pl.col("date") + timedelta(days=SHIFT), s_ly="s"), on=["country", "date"], how="left")
    out = []
    for r, cs in REGIONS.items():
        g = (d.filter(pl.col("country").is_in(cs), pl.col("s_ly").is_not_null()).with_columns(w=pl.col("country").replace_strict(POP, return_dtype=pl.Float64))
             .group_by("date").agg(n=pl.len(), share=(pl.col("s") * pl.col("w")).sum() / pl.col("w").sum(), share_ly=(pl.col("s_ly") * pl.col("w")).sum() / pl.col("w").sum())
             .filter(pl.col("n") == len(cs)))
        out.append(g.with_columns(region=pl.lit(r), yoy=pl.col("share") / pl.col("share_ly") - 1).select("region", "date", "share", "yoy"))
    return pl.concat(out)

S = {"card": quarterly(card, "steam"), "vetted": quarterly(vetted, "steam"), "receipt_all": quarterly(rec, "all_"), "receipt_excl_wallet": quarterly(rec, "excl")}
for r in REGIONS:
    rows = None
    for k, q in S.items():
        g = q.filter(pl.col("region") == r, pl.col("q") >= date(2024, 1, 1)).select("q", pl.col("share").mul(100).round(3).alias(f"{k}_share%"),
                                                                                     pl.col("yoy").mul(100).round(1).alias(f"{k}_yoy%"))
        rows = g if rows is None else rows.join(g, on="q", how="full", coalesce=True)
    print(f"\n{r}: Steam share and share Y/Y by calendar quarter (last quarter to date)")
    print(rows.sort("q"))
R = {k: rolling(x, c) for k, (x, c) in {"card": (card, "steam"), "vetted": (vetted, "steam"), "receipt_all": (rec, "all_"), "receipt_excl_wallet": (rec, "excl")}.items()}
for r in REGIONS:
    m = (R["card"].filter(pl.col("region") == r).select("date", card="yoy")
         .join(R["vetted"].filter(pl.col("region") == r).select("date", vet="yoy"), on="date")
         .join(R["receipt_all"].filter(pl.col("region") == r).select("date", rall="yoy"), on="date")
         .join(R["receipt_excl_wallet"].filter(pl.col("region") == r).select("date", rex="yoy"), on="date")
         .filter(pl.col("date") >= date(2024, 4, 1)))
    print(f"{r}: correlation of trailing-91-day share Y/Y since Apr-2024, card vs receipt (incl wallet / excl wallet):",
          round(m.select(pl.corr("card", "rall")).item(), 2), "/", round(m.select(pl.corr("card", "rex")).item(), 2),
          "| mean abs gap pp:", round((m["card"] - m["rall"]).abs().mean() * 100, 1), "/", round((m["card"] - m["rex"]).abs().mean() * 100, 1))
    print(f"{r}: vetted card vs raw card / receipt incl wallet / receipt excl wallet:",
          *[round(m.select(pl.corr("vet", k)).item(), 2) for k in ("card", "rall", "rex")],
          "| mean abs gap pp:", *[round((m["vet"] - m[k]).abs().mean() * 100, 1) for k in ("card", "rall", "rex")])
    m.write_parquet(D / f"_card_vs_receipt_{r}.parquet")
