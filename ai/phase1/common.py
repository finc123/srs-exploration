"""Shared loaders and gap/episode logic for the Phase 1 renewal-consistency study."""
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).parent
C = HERE.parent / ".cache" / "receipts"
D = HERE / "data"
OUTD = HERE / "out"
PROVS = ["chatgpt", "claude", "gemini", "grok", "perplexity", "muse"]
PMAP = {p: p for p in PROVS} | {"grok_x": "grok"}
CYC = {"M": 30.44, "Q": 91.31, "A": 365.25}
TOL = {"M": 4, "Q": 5, "A": 7}  # day tolerance for "aligned to the billing anchor"
EU_CC = {"united kingdom": "uk", "germany": "de", "france": "fr", "spain": "es", "italy": "it"}


def _bool(s):
    return s.astype(str).str.lower().isin(["true", "1", "1.0"])


def load(region: str) -> pd.DataFrame:
    """Kept, classified rows for the six providers. region 'us' or 'eu'. Adds prov (grok_x -> grok), country."""
    x = pd.read_parquet(C / f"{region}_classified.parquet",
                        columns=["uid", "dt", "country", "provider", "tier", "cadence", "plan", "channel", "kind",
                                 "amount", "renews", "keep", "end_date", "text", "period_months"])
    x = x[_bool(x["keep"])].copy()
    x["prov"] = x["provider"].astype(str).map(PMAP)
    x = x[x["prov"].notna()].copy()
    for c in ["provider", "tier", "cadence", "plan", "channel", "kind", "country"]:
        x[c] = x[c].astype(str)
    x["renews"] = _bool(x["renews"])
    x["amount"] = pd.to_numeric(x["amount"], errors="coerce")
    x["dt"] = pd.to_datetime(x["dt"]).astype("datetime64[ns]")
    x["uid"] = x["uid"].astype(str)
    x.loc[x["period_months"] == 3, "cadence"] = "Q"
    x["cadence"] = x["cadence"].where(x["cadence"].isin(["M", "Q", "A"]), "M")
    x["region"] = region
    x["country"] = x["country"].str.lower() if region == "eu" else "us"
    return x


def charges(x: pd.DataFrame) -> pd.DataFrame:
    """One paid receipt per uid x prov x channel x day."""
    c = x[x["kind"] == "charge"].sort_values(["uid", "prov", "channel", "dt", "amount"], ascending=[1, 1, 1, 1, 0])
    return c.drop_duplicates(["uid", "prov", "channel", "dt"]).reset_index(drop=True)


def add_months(d: pd.Series, k: pd.Series) -> pd.Series:
    ym = d.dt.year * 12 + d.dt.month - 1 + k.astype(int)
    first = pd.to_datetime(pd.DataFrame({"year": ym // 12, "month": ym % 12 + 1, "day": 1}))
    day = np.minimum(d.dt.day, first.dt.days_in_month)
    return first + pd.to_timedelta(day - 1, unit="D")


def gaps(c: pd.DataFrame, key=("uid", "prov", "channel")) -> pd.DataFrame:
    """Consecutive paid-receipt pairs within key. Columns: d0, d1, gap, cad (of d0), k (cycles), aligned, kind:
    'renew' (gap <= 1.5 cycles), 'missed' (longer, aligned to the billing anchor = continued with missed emails),
    'break' (longer, not aligned = lapse and resubscribe, or billing-retry re-anchor)."""
    key = list(key)
    c = c.sort_values([*key, "dt"])
    g = c.groupby(key, sort=False)
    out = c[[*key, "country", "region", "plan", "cadence", "dt", "renews"]].rename(columns={"dt": "d0", "cadence": "cad"})
    out["d1"] = g["dt"].shift(-1)
    out["plan1"] = g["plan"].shift(-1)
    out = out[out["d1"].notna()].copy()
    out["gap"] = (out["d1"] - out["d0"]).dt.days
    cyc = out["cad"].map(CYC)
    out["k"] = np.maximum(1, np.round(out["gap"] / cyc)).astype(int)
    months = out["k"] * out["cad"].map({"M": 1, "Q": 3, "A": 12})
    target = add_months(out["d0"], months)
    out["off"] = (out["d1"] - target).dt.days
    out["aligned"] = out["off"].abs() <= out["cad"].map(TOL)
    long = out["gap"] > 1.5 * cyc
    out["kind"] = np.where(~long, "renew", np.where(out["aligned"], "missed", "break"))
    return out.reset_index(drop=True)


def episodes(c: pd.DataFrame, gp: pd.DataFrame, key=("uid", "prov", "channel")) -> pd.DataFrame:
    """Episodes = runs of receipts split at 'break' gaps. Adds per-receipt episode id; returns episode table."""
    key = list(key)
    c = c.sort_values([*key, "dt"]).reset_index(drop=True)
    g = c.groupby(key, sort=False)
    nxt_kind = gp.set_index([*key, "d0"])["kind"]
    c["kind_next"] = nxt_kind.reindex(pd.MultiIndex.from_frame(c[[*key, "dt"]])).to_numpy()
    c["new"] = g["kind_next"].shift().isna() | g["kind_next"].shift().eq("break")
    c["ep"] = c["new"].cumsum()
    return c


def cycles_between(gp):
    return gp["k"].where(gp["kind"] != "break", 1)


def us_mailboxes():
    m = pd.read_parquet(C / "us_mailboxes.parquet")
    m["uid"] = m["uid"].astype(str)
    m["entry_date"] = pd.to_datetime(m["entry_date"])
    return m.set_index("uid")["entry_date"]


def eu_users():
    u = pd.read_parquet(C / "eu_users.parquet")
    u["uid"] = u["uid"].astype(str)
    u["created"] = pd.to_datetime(u["created"])
    return u.set_index("uid")["created"]


def eu_last_active():
    s = pd.read_parquet(C / "eu_spells.parquet")
    s["uid"] = s["uid"].astype(str)
    return pd.to_datetime(s.groupby("uid")["spell_end"].max())


def q(s, ps=(0.5, 0.9, 0.95, 0.99, 0.995)):
    s = pd.Series(s).dropna()
    d = {f"p{int(p * 1000) / 10:g}": s.quantile(p) for p in ps}
    d["max"] = s.max()
    return d


WINDOWS_FILE = "t2b_windows.csv"  # t7c switches to t2c_windows.csv (Google One storage removed from references)


def windows(subset="live_any", min_gaps=2000):
    """Lapse window W (days) per region x prov x channel = p99 continuing gap in the reliable subset (t2b); cells with
    fewer than min_gaps gaps fall back to the provider pooled across channels, then the channel pooled across
    providers; unknown 62."""
    w = pd.read_csv(OUTD / WINDOWS_FILE)
    w = w[w["subset"] == subset]
    own = w[(w["prov"] != "ALL") & (w["channel"] != "ALL") & (w["n_gaps"] >= min_gaps)].set_index(["region", "prov", "channel"])["p99"]
    prov = w[(w["channel"] == "ALL") & (w["n_gaps"] >= min_gaps)].set_index(["region", "prov"])["p99"]
    pool = w[w["prov"] == "ALL"].set_index(["region", "channel"])["p99"]

    def get(region, prov_, channel):
        if (region, prov_, channel) in own.index:
            return int(np.ceil(own[(region, prov_, channel)]))
        if (region, prov_) in prov.index:
            return int(np.ceil(prov[(region, prov_)]))
        if (region, channel) in pool.index:
            return int(np.ceil(pool[(region, channel)]))
        return 62
    return get
