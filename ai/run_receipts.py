"""Run every receipt filter over the US (NIQ) and EU (Fox) extracts, then build subscriptions, daily index and flows.

Panels: 'us' and one per EU country (uk/de/fr/es/it), matching the card report. ChatGPT direct (sign-up receipts
only) is reported two ways: provider 'chatgpt' uses the modelled survival of the panel's renewing ChatGPT channels;
'chatgpt_raw' keeps direct subscribers until a cancellation email.

Outputs (.cache/receipts/metrics/): payments, cancels, subs_{level}, daily_{level}, active (same layout as the card run,
so build_report.py works on it).
"""
import importlib
from pathlib import Path
import pandas as pd
import subs_receipts as R

HERE = Path(__file__).parent
C = HERE / ".cache" / "receipts"
OUT = C / "metrics"
FILTERS = ["chatgpt", "claude", "gemini", "grok", "muse", "cursor", "perplexity"]
EU = {"uk": "uk", "de": "de", "fr": "fr", "es": "es", "it": "it"}
START = pd.Timestamp("2024-01-01")


def classify(region: str) -> pd.DataFrame:
    cached = C / f"{region}_classified.parquet"
    if cached.exists() and "--reclassify" not in __import__("sys").argv:
        return pd.read_parquet(cached)
    raw = pd.read_parquet(C / f"{region}_ai_items.parquet")
    out = []
    for f in FILTERS:
        if not (HERE / "filters_receipts" / f"{f}.py").exists():
            print(f"  {region}: no filter for {f} yet", flush=True)
            continue
        c = importlib.import_module(f"filters_receipts.{f}").classify(raw, region)
        print(f"  {region}/{f}: {int(c['keep'].sum()):,} kept of {len(c):,}", flush=True)
        out.append(c)
    x = pd.concat(out, ignore_index=True)
    x["dt"] = pd.to_datetime(x["dt"])
    x["end_date"] = pd.to_datetime(x.get("end_date"))
    x["panel"] = "us" if region == "us" else x["country"].str.lower()
    if "period_months" in x:  # 3-month offers bill quarterly
        x.loc[x["period_months"] == 3, "cadence"] = "Q"
    x = x[x["keep"]].copy()
    for col in x.columns:  # mixed-type object columns from different filters
        if x[col].dtype == object and col not in ("uid",):
            x[col] = x[col].astype("string")
    x["uid"] = x["uid"].astype(str)
    x.to_parquet(cached, index=False)
    return x


def run_panel(panel: str, x: pd.DataFrame, spells, data_end, denom: pd.Series):
    days = pd.date_range(START, data_end)
    x = x.copy()
    x["renews"] = x["renews"].astype(str).str.lower().isin(["true", "1", "1.0"])  # filters return mixed types
    x["cadence"] = x["cadence"].astype(str).where(x["cadence"].astype(str).isin(["M", "Q", "A"]), "M")
    pay = x[x["kind"] == "charge"]
    can = x[x["kind"] == "cancel"]
    res = {"subs": {}, "daily": {}}
    for level in ("plan", "provider"):
        by = ("provider",) if level == "plan" else ()
        s = R.subscriptions(pay, can, level, data_end, spells=spells, by=by).assign(panel=panel)
        # Survival of renewing ChatGPT channels drives the modelled direct (sign-up only) subscribers.
        cg = R.subscriptions(pay[(pay["provider"] == "chatgpt") & pay["renews"]], can[can["provider"] == "chatgpt"],
                             "provider", data_end, spells=spells)
        surv = R.survival(cg, data_end) if len(cg) else None
        d = R.daily(s, level, days, by=by, modelled={"chatgpt": surv} if surv is not None else None)
        raw = R.daily(s[s["provider"] == "chatgpt"], level, days, by=by)
        if len(raw):
            raw["provider"] = "chatgpt_raw"
            if level == "provider":
                raw["provider"] = "chatgpt_raw"
        res["subs"][level] = s
        res["daily"][level] = pd.concat([d, raw], ignore_index=True).assign(panel=panel)
    active = denom.reindex(days).ffill().rename("active_members").to_frame().assign(panel=panel).rename_axis("date").reset_index()
    return res, active


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    subs, daily, active, pays = {"plan": [], "provider": []}, {"plan": [], "provider": []}, [], []
    # US: active mailboxes only (now-inactive mailboxes are not in the extract = removed); 84-day active denominator.
    us = classify("us")
    pays.append(us)
    na = pd.read_parquet(C / "us_normal_active.parquet")
    na = na[na["method"] == "84d_active"].assign(d=lambda t: pd.to_datetime(t["orderdate"])).set_index("d")["unique_mailboxes"].sort_index()
    us_end = min(us["dt"].max(), pd.Timestamp.today().normalize())
    r, a = run_panel("us", us[us["dt"] <= us_end], None, us_end, na)
    # EU: one panel per country; exit = no receipt of any kind for 90 days (activity spells).
    eu = classify("eu")
    pays.append(eu)
    spells = pd.read_parquet(C / "eu_spells.parquet")
    spells["uid"] = spells["uid"].astype(str)
    for col in ("spell_start", "spell_end"):
        spells[col] = pd.to_datetime(spells[col])
    users = pd.read_parquet(C / "eu_users.parquet")
    users["uid"] = users["uid"].astype(str)
    users["country"] = users["country"].str.lower().map(
        {"united kingdom": "uk", "germany": "de", "france": "fr", "spain": "es", "italy": "it"})  # others (India, ...) drop out
    eu_end = eu["dt"].max()
    results = [(r, a)]
    for cc in EU:
        uid_c = users.loc[users["country"] == cc, "uid"]
        sp = spells[spells["uid"].isin(uid_c)]
        days = pd.date_range(START, eu_end)
        denom = pd.Series(R._daily_count(sp["spell_start"], sp["spell_end"] + pd.Timedelta(days=R.EU_QUIET), days), index=days)
        results.append(run_panel(cc, eu[eu["panel"] == cc], sp, eu_end, denom))
        print(cc, "done", flush=True)
    for r, a in results:
        active.append(a)
        for level in ("plan", "provider"):
            subs[level].append(r["subs"][level])
            daily[level].append(r["daily"][level])
    allp = pd.concat(pays, ignore_index=True)
    allp["amount"] = pd.to_numeric(allp["amount"], errors="coerce")
    for col in allp.columns:
        if allp[col].dtype == object:
            allp[col] = allp[col].astype("string")
    allp.to_parquet(OUT / "payments.parquet", index=False)
    pd.concat(active).to_parquet(OUT / "active.parquet", index=False)
    for level in ("plan", "provider"):
        s = pd.concat(subs[level])
        s.to_parquet(OUT / f"subs_{level}.parquet", index=False)
        pd.concat(daily[level]).to_parquet(OUT / f"daily_{level}.parquet", index=False)
        key = ["provider", "plan"] if level == "plan" else ["provider"]
        rem = s.assign(month=s["start"].dt.to_period("M").astype(str)).groupby(["panel", *key, "month"]).agg(
            gross_adds_raw=("start", "size"), removed_exit=("outcome", lambda o: (o == "exit").sum())).reset_index()
        rem.to_parquet(OUT / f"removed_{level}.parquet", index=False)
    print("done", flush=True)


if __name__ == "__main__":
    main()
