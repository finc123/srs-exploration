"""Run every provider filter over each card panel, then build subscriptions, the daily index and flows.

Outputs (.cache/metrics/):
  payments.parquet       classified kept payments (all panels)
  subs_{level}.parquet   subscriptions per level (plan / provider) with outcome flags
  daily_{level}.parquet  daily subs, gross adds, reactivations, churn per panel x key
  removed_{level}.parquet gross adds later removed for panel exit, by start month
  active.parquet         active panel members per panel x day

Usage: python run_metrics.py [panel ...]
"""
import importlib, re, sys
from pathlib import Path
import pandas as pd
import subs as S
from keywords import KEYWORDS

HERE = Path(__file__).parent
CACHE, OUT = HERE / ".cache", HERE / ".cache" / "metrics"
PANELS = ["omega", "uk", "de", "fr", "es", "it"]
FILTERS = ["chatgpt", "claude", "gemini", "grok", "muse", "cursor", "perplexity"]
START = pd.Timestamp("2024-01-01")
# Series end overrides where a provider's billing data breaks (not a panel hole). Google One charges collapse in
# every panel from 2026-09-21 while total panel volume is flat; until explained, Gemini stops there so the gap
# is not read as churn.
PROVIDER_END = {}  # Gemini gap fixed by the Google One SKU descriptors (2026-09-15+)


def classify_panel(panel: str) -> pd.DataFrame:
    raw = pd.read_parquet(CACHE / f"{panel}_ai_txn.parquet")
    low = raw["descr"].str.lower()
    out = []
    for f in FILTERS:
        path = HERE / "filters" / f"{f}.py"
        if not path.exists():
            print(f"  {panel}: no filter for {f} yet", flush=True)
            continue
        mod = importlib.import_module(f"filters.{f}")
        # Each filter only sees rows matching its own prefilter keywords (keeps memory down on the US panel).
        rx = "|".join("^" + re.escape(k).replace("%", ".*") + "$" for k in KEYWORDS[f])
        c = mod.classify(raw[low.str.match(rx)].reset_index(drop=True), panel)
        out.append(c.assign(panel=panel))
        print(f"  {panel}/{f}: {c['keep'].sum():,} kept of {len(c):,}", flush=True)
    return pd.concat(out, ignore_index=True)


def spells_for(panel: str) -> pd.DataFrame:
    sp = pd.read_parquet(CACHE / f"{panel}_spells.parquet")
    for c in ("spell_start", "spell_end"):
        sp[c] = pd.to_datetime(sp[c])
    if panel != "omega":  # consumer users only
        users = pd.read_parquet(CACHE / "fable_users.parquet", columns=["uid", "usertype"]).drop_duplicates("uid", keep="last")
        sp = sp[sp["uid"].isin(users.loc[users["usertype"] == "C", "uid"])]
    return sp


def main(panels):
    OUT.mkdir(parents=True, exist_ok=True)
    pays, subs_all, daily_all, removed_all, active_all = [], {"plan": [], "provider": []}, {"plan": [], "provider": []}, {"plan": [], "provider": []}, []
    for panel in panels:
        print(panel, flush=True)
        cls = classify_panel(panel)
        pay = cls[cls["keep"]].copy()
        pay["dt"] = pd.to_datetime(pay["dt"])
        pays.append(pay)
        sp = spells_for(panel)
        data_end = sp["spell_end"].max()
        days = pd.date_range(START, data_end)
        active_all.append(S.active_members(sp, days).to_frame().assign(panel=panel).rename_axis("date").reset_index())
        for level in ("plan", "provider"):
            by = ("provider",) if level == "plan" else ()
            for prov, pp in pay.groupby("provider"):
                end = min(data_end, PROVIDER_END.get(prov, data_end))
                p = pp.loc[pp["dt"] <= end, ["uid", "dt", "cadence", "plan", "provider"]].copy()
                p.attrs["by"] = list(by)
                s = S.subscriptions(p, sp, level, end).assign(panel=panel)
                d = S.daily(s, level, days, by=by)
                if d.empty:
                    continue
                d = d.assign(panel=panel)
                d.loc[d["date"] > end, ["subs", "gross_adds", "reactivations", "churn"]] = float("nan")
                subs_all[level].append(s)
                daily_all[level].append(d)
                removed_all[level].append(S.removed_adds(s, level, by=by).assign(panel=panel))
    pd.concat(pays).to_parquet(OUT / "payments.parquet", index=False)
    pd.concat(active_all).to_parquet(OUT / "active.parquet", index=False)
    for level in ("plan", "provider"):
        pd.concat(subs_all[level]).to_parquet(OUT / f"subs_{level}.parquet", index=False)
        pd.concat(daily_all[level]).to_parquet(OUT / f"daily_{level}.parquet", index=False)
        r = pd.concat(removed_all[level])
        r["month"] = r["month"].astype(str)
        r.to_parquet(OUT / f"removed_{level}.parquet", index=False)
    print("done", flush=True)


if __name__ == "__main__":
    main(sys.argv[1:] or PANELS)
