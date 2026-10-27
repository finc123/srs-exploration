"""ChatGPT (OpenAI) consumer web-subscription filter for the card panels.

classify(df, panel) -> one row per candidate OpenAI payment with plan (tier x cadence), channel, keep and reason.
See filters/chatgpt_report.md for how the descriptor rules and amount bands were set.

Summary of the rules
- Descriptor classes (on the upper-cased descriptor): ChatGPT web ('CHATGPT', 'OPENAI *CH', PayPal 'OPENAIOPCO'),
  bare 'OPENAI' (mix of API usage and, increasingly from late 2025, ChatGPT subscriptions), Google Play
  ('GOOGLE *CHATGPT': kept with channel='google_play' and its own price bands, user decision 2026-10-19),
  Sora (rejected), 'CHATGPT CREDIT' packs, 'CHATGPT BUSINESS'. Non-OpenAI hits of the
  prefilter ('OPEN AIR' markets etc.), third-party ChatGPT-named apps, account transfers and OpenAI payroll are
  dropped (not candidates).
- Bare 'OPENAI' rows are kept only when the amount maps to a plan AND the uid repeats that plan 25-35 days
  before or after (subscription cadence); otherwise rejected as API/usage.
- No consumer annual plans exist: every kept payment is cadence M.
- Team/Business seats share the CHATGPT descriptor: amounts that are seat multiples (US 2x30, 2x25 ...) are rejected,
  and consumer-collision amounts (Pro 100 = 4x25, Pro 200 = 8x25, upgrade prorations) are rejected when the same uid
  paid a seat-multiple amount within 62 days.
- No reportdate-vs-dt lag filter (removed 2026-10-19: it created holes read as churn; all data used).
- Promos (Plus 50% retention offer, Go 50% intro) map to the base plan; upgrade prorations (Plus->Pro, Go->Plus)
  map to the target plan only when the uid pays that plan within 40 days afterwards. `note` says which.
"""
import numpy as np
import pandas as pd

PROVIDER = "chatgpt"
# Some issuers truncate the descriptor to 15 characters: "GOOGLE *CHATGP MOUNTAIN VIE CA", "PAYPAL *OPENAI *CHATGP"
# (no trailing T; grew from Oct 2025, ~3.8k panel rows a month in Aug 2026). CHATGP must be a whole token.
GPT = r"CHAT ?(?:GPT|GP\b)"
OPENAI_RX = GPT + r"|OPEN ?AI(?!R)"
NOT_MERCHANT_RX = r"XFER|TRANSFER|\bFROM SHARE|\bTO SHARE|\bTO LOAN|PAYROLL|DIRECT DEP|DEPOSIT|\bREPAY"
GOOGLE_RX = r"GOOGLE.{0,4}" + GPT
CREDIT_RX = r"CHATGPT CRED|CHATGPT CR\b|OPENAI\* ?CHATGPT CR"
BUSINESS_RX = r"CHATGPT (?:FOR )?BUSINESS|CHATGPT TEAM"
CHATGPT_RX = GPT + r"|OPENAI ?\* ?CH|OPENAIOPCO|OPENAI - OPENAI|PAYPAL.{0,20}OPENAI"
# ChatGPT-named descriptors without OPENAI are third-party apps (Sider, Superpower ChatGPT, ChatGPT Writer, Gumroad
# GPT guides ...) unless they look like OpenAI's own subscription descriptor.
FIRST_PARTY_RX = r"OPENAI|CHAT ?GPT ?SU|CHATGPT S\b|^\s*CHAT ?GPT( PLUS)?\s*$|PAYMENT TO CHATGPT|PAYPAL.{0,25}CHATGPT|CHATGPT PAYPAL"

T = pd.Timestamp
D0 = T("2000-01-01")
# (plan, lo, hi, valid_from, note). Bands from the panel histograms (see report); first match wins.
BANDS = {
    "US": [
        ("go_M", 7.95, 9.00, T("2025-12-15"), ""),
        ("go_M", 3.95, 4.45, T("2026-01-01"), "promo_go_50pct"),
        ("plus_M", 19.50, 23.05, D0, ""),
        ("plus_M", 9.95, 11.30, T("2025-01-01"), "promo_plus_50pct"),
        ("pro100_M", 99.90, 111.00, T("2026-04-09"), ""),
        ("pro200_M", 199.90, 222.10, T("2024-12-05"), ""),
        ("pro500_M", 499.90, 555.00, T("2026-09-29"), ""),
    ],
    "UK": [
        ("go_M", 6.90, 8.10, T("2025-12-15"), ""),
        ("plus_M", 14.40, 20.60, D0, ""),       # GBP 20; legacy USD 20/24 at FX; ex-VAT GBP 16.67
        ("plus_M", 8.70, 10.10, T("2025-01-01"), "promo_plus_50pct"),
        ("pro100_M", 85.00, 92.00, T("2026-04-09"), ""),
        ("pro200_M", 160.00, 201.00, T("2024-12-05"), ""),   # GBP 200; legacy USD 240 at FX (GBP 167-190)
        ("pro500_M", 440.00, 505.00, T("2026-09-29"), ""),
    ],
    "EU": [
        ("go_M", 7.50, 8.50, T("2025-12-15"), ""),
        ("go_M", 3.90, 4.10, T("2026-01-01"), "promo_go_50pct"),
        ("go_M", 6.50, 6.80, T("2025-12-15"), ""),      # EUR 7.99 ex-VAT (VAT-ID payers: DE 6.72, FR 6.67, ES 6.61)
        ("plus_M", 16.50, 25.90, D0, ""),       # EUR 23; legacy USD 23.80-24.40 at FX (+ FR card FX commission); early USD 20
        ("plus_M", 9.00, 12.50, T("2025-01-01"), "promo_plus_50pct"),
        ("pro100_M", 98.00, 106.00, T("2026-04-09"), ""),
        ("pro200_M", 180.00, 246.00, T("2024-12-05"), ""),
        ("pro500_M", 495.00, 520.00, T("2026-09-29"), ""),
    ],
}
# Google Play in-app billing (keep=True, channel='google_play'): Play price points differ from web (US Plus $19.99
# + tax, Go $7.99/8.00 + tax); in Europe many Play charges are USD-priced and drift with FX (EUR 16.9-18.3 for Plus).
# No Team seats or prorations on Play. Sora-by-OpenAI Play charges (separate app / add-ons) are rejected.
GP_BANDS = {
    "US": [
        ("go_M", 7.99, 8.95, T("2025-12-15"), ""),
        ("plus_M", 19.99, 22.30, D0, ""),
        ("plus_M", 9.99, 11.20, T("2025-01-01"), "promo_plus_50pct"),
        ("pro100_M", 99.98, 111.10, T("2026-04-09"), ""),
        ("pro200_M", 199.98, 222.20, T("2024-12-05"), ""),
        ("pro500_M", 499.98, 555.00, T("2026-09-29"), ""),
    ],
    "UK": [
        ("go_M", 6.90, 8.10, T("2025-12-15"), ""),
        ("plus_M", 14.40, 20.00, D0, ""),       # GBP 18.99 + USD-priced variants
        ("pro100_M", 80.00, 92.00, T("2026-04-09"), ""),
        ("pro200_M", 160.00, 201.00, T("2024-12-05"), ""),
    ],
    "EU": [
        ("go_M", 7.50, 8.60, T("2025-12-15"), ""),
        ("plus_M", 16.50, 23.10, D0, ""),       # EUR 22.99 + USD 19.99 at FX
        ("pro100_M", 85.00, 106.00, T("2026-04-09"), ""),
        ("pro200_M", 170.00, 246.00, T("2024-12-05"), ""),
    ],
}
# Upgrade prorations: (target plan, lo, hi, valid_from). Kept only if the uid pays the target within 40 days after.
PRORATION = {
    "US": [("pro100_M", 75.0, 99.89, T("2026-04-09")), ("pro200_M", 170.0, 199.89, T("2024-12-05")),
           ("plus_M", 11.5, 19.49, T("2026-01-16"))],
    "UK": [("pro100_M", 65.0, 84.99, T("2026-04-09")), ("pro200_M", 120.0, 159.99, T("2024-12-05")),
           ("plus_M", 10.2, 14.39, T("2026-01-16"))],
    "EU": [("pro100_M", 75.0, 97.99, T("2026-04-09")), ("pro200_M", 130.0, 179.99, T("2024-12-05")),
           ("plus_M", 12.6, 16.49, T("2026-01-16"))],
}
# Team/Business seat multiples (lo, hi, valid_from, valid_to). Amounts >= BIG not in a plan band are seats/annual too.
SEATS = {
    "US": [(50.0, 55.6, T("2026-04-02"), None), (60.0, 66.7, D0, None), (75.0, 79.99, T("2026-04-02"), None),
           (90.0, 99.89, D0, T("2026-04-09")), (120.0, 139.0, D0, None), (150.0, 166.7, D0, None)],
    "UK": [(35.5, 36.5, D0, None), (42.5, 43.5, D0, None), (55.0, 66.7, D0, None)],
    "EU": [(56.0, 75.0, D0, None), (43.0, 44.6, T("2026-04-02"), None), (51.0, 53.5, T("2026-04-02"), None)],
}
BIG = 230.0
REGION = {"omega": "US", "uk": "UK", "de": "EU", "fr": "EU", "es": "EU", "it": "EU"}


def _descr_class(u: pd.Series) -> pd.Series:
    d = u.str.upper()
    conds = [~d.str.contains(OPENAI_RX), d.str.contains(NOT_MERCHANT_RX), d.str.contains("SORA"),
             d.str.contains(GOOGLE_RX), ~d.str.contains(FIRST_PARTY_RX), d.str.contains(CREDIT_RX), d.str.contains(BUSINESS_RX),
             d.str.contains(CHATGPT_RX)]
    out = np.select(conds, ["noise", "not_merchant", "sora", "google_play", "third_party", "credits", "business", "chatgpt"],
                    "openai_bare")
    return pd.Series(out, index=u.index)


def _normalise(df: pd.DataFrame, panel: str) -> pd.DataFrame:
    if panel == "omega":
        x = pd.DataFrame({"uid": df["uid"].values, "dt": pd.to_datetime(df["dt"]).values,
                          "amount": df["amount"].astype(float).values, "currency": df["currency"].values,
                          "descr": df["descr"].values})
        x["refund"] = (df["transtype"].values == "credit") | (x["amount"].values <= 0)
        x["amount"] = x["amount"].abs()
        x["usertype"] = "C"
    else:
        so, si = df["spendout"].fillna(0).values, df["spendin"].fillna(0).values
        x = pd.DataFrame({"uid": df["uid"].values, "dt": pd.to_datetime(df["dt"]).values,
                          "amount": np.where(so < 0, -so, si), "currency": df["currency"].values,
                          "descr": df["descr"].values, "usertype": df["usertype"].values})
        x["refund"] = (si > 0) | (so >= 0) | (df["txntype"].values == "CREDIT")
    return x


def _map_bands(x: pd.DataFrame, bands: list, rows: np.ndarray) -> None:
    a, dt = x["amount"].values, x["dt"].values
    for plan, lo, hi, vf, note in bands:
        inb = rows & (a >= lo) & (a <= hi) & (x["plan"].values == "")
        ok = inb & (dt >= np.datetime64(vf))
        x.loc[ok, ["plan", "note"]] = [plan, note]
        x.loc[inb & ~ok, "pre_launch"] = True


def _seat(x: pd.DataFrame, region: str) -> np.ndarray:
    a, dt = x["amount"].values, x["dt"].values
    m = np.zeros(len(x), bool)
    for lo, hi, vf, vt in SEATS[region]:
        w = (a >= lo) & (a <= hi) & (dt >= np.datetime64(vf))
        if vt is not None:
            w &= dt < np.datetime64(vt)
        m |= w
    return m | ((a >= BIG) & (x["plan"].values == ""))


def _near(left: pd.DataFrame, right: pd.DataFrame, days: int, direction: str) -> np.ndarray:
    """For each left row (uid, dt), is there a right row of the same uid within `days` in `direction`?"""
    if left.empty or right.empty:
        return np.zeros(len(left), bool)
    l = left[["uid", "dt"]].reset_index().sort_values("dt")
    r = right[["uid", "dt"]].rename(columns={"dt": "rdt"}).sort_values("rdt")
    m = pd.merge_asof(l, r, left_on="dt", right_on="rdt", by="uid", direction=direction,
                      tolerance=pd.Timedelta(days=days), allow_exact_matches=direction != "forward")
    return m.set_index("index")["rdt"].notna().reindex(left.index).values


def classify(df: pd.DataFrame, panel: str) -> pd.DataFrame:
    region = REGION[panel]
    u = pd.Series(pd.unique(df["descr"].fillna("")))
    cls = dict(zip(u, _descr_class(u)))
    c = df["descr"].fillna("").map(cls)
    keep_rows = ~c.isin(["noise", "not_merchant", "third_party"]).values
    x = _normalise(df.loc[keep_rows], panel).reset_index(drop=True)
    x["dclass"] = c.values[keep_rows]
    x["provider"] = PROVIDER
    x["channel"] = np.where(x["dclass"].isin(["google_play", "sora"]), "google_play", "web")

    # Duplicates: same uid + day + amount among non-refund rows (pending/posted repeats).
    x = x.sort_values(["uid", "dt", "amount"], kind="mergesort").reset_index(drop=True)
    dup = (~x["refund"]) & x.duplicated(["uid", "dt", "amount", "refund"])

    x["plan"], x["note"], x["pre_launch"] = "", "", False
    gp = x["dclass"].values == "google_play"
    _map_bands(x, BANDS[region], ~gp)
    _map_bands(x, GP_BANDS[region], gp)
    subs_cls = x["dclass"].isin(["chatgpt", "openai_bare"]).values
    base = subs_cls & ~x["refund"].values & ~dup.values & (x["usertype"].values == "C")

    # Seat multiples (Team/Business) on the subscription descriptors.
    seat = base & _seat(x, region) & (x["dclass"].values == "chatgpt")

    # Upgrade prorations -> target plan if the uid pays the target within 40 days afterwards.
    pr_note = np.full(len(x), "", object)
    cand = base & (x["plan"].values == "") & ~seat
    for tgt, lo, hi, vf in PRORATION[region]:
        w = cand & (x["amount"].values >= lo) & (x["amount"].values <= hi) & (x["dt"].values >= np.datetime64(vf)) \
            & (pr_note == "")
        if w.any():
            hit = _near(x[w], x[base & (x["plan"].values == tgt)], 40, "forward")
            idx = np.flatnonzero(w)[hit]
            x.loc[idx, "plan"] = tgt
            pr_note[idx] = "upgrade_proration"
    x.loc[pr_note != "", "note"] = pr_note[pr_note != ""]

    # Collisions with seat multiples (Pro 100 = 4x25, Pro 200 = 8x25, prorations): same uid paid seats within 62d.
    coll = base & x["plan"].isin(["pro100_M", "pro200_M", "pro500_M"]).values & (x["dclass"].values == "chatgpt")
    seat_coll = np.zeros(len(x), bool)
    if coll.any() and seat.any():
        seat_coll[np.flatnonzero(coll)] = _near(x[coll], x[seat], 62, "nearest")

    # Bare OPENAI: needs a same-plan repeat 25-35 days before or after (else API usage).
    bare = base & (x["dclass"].values == "openai_bare") & (x["plan"].values != "")
    bare_ok = np.zeros(len(x), bool)
    if bare.any():
        y = x[base & (x["plan"].values != "")][["uid", "plan", "dt"]].copy()
        y = y.sort_values(["uid", "plan", "dt"])
        g = y.groupby(["uid", "plan"])["dt"]
        gp, gn = g.diff().dt.days, (g.shift(-1) - y["dt"]).dt.days
        rep = gp.between(25, 35) | gn.between(25, 35)
        bare_ok = rep.reindex(x.index, fill_value=False).astype(bool).values & bare

    reason = np.select(
        [x["refund"].values,
         x["currency"].values != ("USD" if region == "US" else ("GBP" if region == "UK" else "EUR")),
         x["dclass"].values == "sora",
         x["dclass"].values == "credits",
         x["dclass"].values == "business",
         x["usertype"].values != "C",
         dup.values,
         x["amount"].values < 3,
         seat,
         seat_coll,
         (x["dclass"].values == "openai_bare") & ~bare_ok,
         x["pre_launch"].values & (x["plan"].values == ""),
         x["plan"].values == ""],
        ["refund", "currency", "sora", "credits", "business_descriptor", "business_user",
         "duplicate", "auth_small", "team_business", "team_business_collision", "api_bare_openai",
         "pre_launch", "out_of_band"],
        "ok")
    x["reason"] = reason
    x["keep"] = reason == "ok"
    # Near-duplicates: the same payment posted twice with descriptor variants 1-3 days apart (pending vs posted,
    # common in FR), sometimes with a different FX amount. Same uid + plan within 3 days and amount within 15%.
    k = x[x["keep"]].sort_values(["uid", "channel", "plan", "dt"], kind="mergesort")
    g = k.groupby(["uid", "channel", "plan"], sort=False)
    gap = (k["dt"] - g["dt"].shift()).dt.days
    ratio = k["amount"] / g["amount"].shift()
    near = k.index[(gap <= 3) & ratio.between(0.85, 1.15)]
    x.loc[near, ["reason", "keep"]] = ["duplicate_near", False]
    x.loc[(x["dclass"].values == "openai_bare") & x["keep"].values, "note"] = \
        (x["note"] + ";bare_openai").str.strip(";")
    x["tier"] = np.where(x["plan"] != "", x["plan"].str.replace("_M", "", regex=False), "")
    x["cadence"] = np.where(x["plan"] != "", "M", "")
    cols = ["uid", "dt", "amount", "currency", "descr", "provider", "tier", "cadence", "plan", "channel", "keep",
            "reason", "note", "dclass", "usertype"]
    return x[cols].sort_values(["uid", "dt"], kind="mergesort").reset_index(drop=True)
