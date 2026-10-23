"""Recommended lapse windows: p99 continuing gap per region x provider x channel, all users vs the reliable subset
(live_any). Small cells (< 2000 gaps) fall back to the channel pooled across providers. Output: out/recommended_windows.csv"""
import pandas as pd
from common import *

w = pd.read_csv(OUTD / "t2b_windows.csv")
get = windows()
a = w[(w["subset"] == "all") & (w["prov"] != "ALL") & (w["channel"] != "ALL")].set_index(["region", "prov", "channel"])
r = w[(w["subset"] == "live_any") & (w["prov"] != "ALL") & (w["channel"] != "ALL")].set_index(["region", "prov", "channel"])
out = pd.DataFrame({"gaps_all": a["n_gaps"], "capture_all": a["capture"], "p99_all": a["p99"],
                    "R_share_of_gaps": r["share_of_gaps"], "capture_R": r["capture"], "p99_R": r["p99"],
                    "false_lapse_45_R": r["false_lapse_45"]}).reset_index()
out["W_recommended"] = [get(*k) for k in zip(out["region"], out["prov"], out["channel"])]
out["W_source"] = ["own" if (g >= 2000) else "pooled (provider, else channel)" for g in r["n_gaps"].reindex(
    pd.MultiIndex.from_frame(out[["region", "prov", "channel"]])).fillna(0)]
out.round(3).to_csv(OUTD / "recommended_windows.csv", index=False)
pd.set_option("display.width", 250)
print(out.round(3).to_string(index=False))
