"""Monthly summary of the card-panel subscriber metrics -> report/data.json (embedded into report/ai_subs_cards.html)."""
import json
from pathlib import Path
import pandas as pd

HERE = Path(__file__).parent
M = HERE / ".cache" / "metrics"
REPORT = HERE / "report"
EU = ["uk", "de", "fr", "es", "it"]
NAMES = {"omega": "US", "us": "US", "uk": "UK", "de": "Germany", "fr": "France", "es": "Spain", "it": "Italy", "eu": "Europe (5)"}
PROV = ["chatgpt", "claude", "gemini", "grok", "grok_x", "muse", "cursor", "perplexity", "chatgpt_raw"]


def monthly(level: str) -> pd.DataFrame:
    d = pd.read_parquet(M / f"daily_{level}.parquet")
    key = ["provider", "plan"] if level == "plan" else ["provider"]
    d["month"] = d["date"].dt.to_period("M").astype(str)
    g = d.groupby(["panel", *key, "month"])
    m = g.agg(subs=("subs", "mean"), subs_end=("subs", "last"), gross_adds=("gross_adds", "sum"),
              reactivations=("reactivations", "sum"), churn=("churn", "sum")).reset_index()
    eu = m[m["panel"].isin(EU)].groupby([*key, "month"], as_index=False)[["subs", "subs_end", "gross_adds", "reactivations", "churn"]].sum()
    return pd.concat([m, eu.assign(panel="eu")], ignore_index=True)


def main(metrics_dir=None, out_name="ai_subs_cards.html", template="template.html", methods_mod="methods", settle_days=45):
    global M
    M = Path(metrics_dir) if metrics_dir else M
    prov = monthly("provider")
    plan = monthly("plan")
    act = pd.read_parquet(M / "active.parquet")
    act["month"] = act["date"].dt.to_period("M").astype(str)
    act = act.groupby(["panel", "month"], as_index=False)["active_members"].mean()
    act = pd.concat([act, act[act["panel"].isin(EU)].groupby("month", as_index=False)["active_members"].sum().assign(panel="eu")])
    rem = pd.read_parquet(M / "removed_provider.parquet")
    rem = pd.concat([rem, rem[rem["panel"].isin(EU)].groupby(["provider", "month"], as_index=False)[["gross_adds_raw", "removed_exit"]].sum().assign(panel="eu")])

    out = {"panels": {}, "names": NAMES, "providers": PROV}
    present = set(prov["panel"])
    for panel in [p for p in NAMES if p in present or p == "eu"]:
        p = prov[prov["panel"] == panel].merge(act[act["panel"] == panel][["month", "active_members"]], on="month", how="left")
        p = p.merge(rem[rem["panel"] == panel][["provider", "month", "gross_adds_raw", "removed_exit"]], on=["provider", "month"], how="left")
        if p.empty:
            continue
        p["per_1k"] = p["subs"] / p["active_members"] * 1000
        tracked = p["subs"].where(p["provider"] != "chatgpt_raw", 0)  # the raw ChatGPT variant is a comparison, not a provider
        p["share"] = (p["subs"] / tracked.groupby(p["month"]).transform("sum")).where(p["provider"] != "chatgpt_raw")
        p["opening"] = p.groupby("provider")["subs_end"].shift()
        p["churn_rate"] = p["churn"] / p["opening"]
        months = sorted(p["month"].unique())
        series = {pr: p[p["provider"] == pr].set_index("month").reindex(months)[
            ["subs", "gross_adds", "churn", "reactivations", "per_1k", "share", "churn_rate", "gross_adds_raw", "removed_exit"]]
            .round(4).astype(object).where(lambda x: x.notna(), None).to_dict("list") for pr in PROV if pr in set(p["provider"])}
        pl = plan[plan["panel"] == panel]
        plans = (pl[pl["month"].isin(months[-4:])].pivot_table(index=["provider", "plan"], columns="month", values="subs")
                 .round(0).reset_index())
        # Latest month whose lapses are all decidable: its last day is at least settle_days before the data end.
        dp = pd.read_parquet(M / "daily_provider.parquet", columns=["panel", "date", "subs"])
        last_day = dp.loc[dp["panel"].isin(EU if panel == "eu" else [panel]) & dp["subs"].notna(), "date"].max()
        settled = max(m for m in months if (pd.Period(m, "M").end_time.normalize() + pd.Timedelta(days=settle_days)) <= last_day)
        out["panels"][panel] = {"months": months, "series": series, "settled": settled,
                                "plans": json.loads(plans.to_json(orient="split", index=False))}
    REPORT.mkdir(exist_ok=True)
    (REPORT / out_name.replace(".html", ".json")).write_text(json.dumps(out))
    import sys; sys.path.insert(0, str(REPORT))
    import importlib
    methods = importlib.import_module(methods_mod)
    meth = {"html": methods.html(), "panel_notes": methods.PANEL_NOTES}
    page = (REPORT / template).read_text(encoding="utf-8")
    safe = lambda o: json.dumps(o).replace("</", r"<\/")  # keep '</script>' out of the inline JSON
    page = page.replace("__DATA__", safe(out)).replace("__METHODS__", safe(meth))
    (REPORT / out_name).write_text(page, encoding="utf-8")
    print({k: v["months"][-2:] for k, v in out["panels"].items()})


if __name__ == "__main__":
    main()
