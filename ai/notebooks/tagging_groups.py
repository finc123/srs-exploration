"""Coarse tagging-issue groups for the email to Consumer Edge (reads tagging_audit.py's cached payments)."""
import re
import pandas as pd
from pathlib import Path

CACHE = Path(__file__).resolve().parent.parent / ".cache" / "card_core"
# provider -> ordered (issue group, regex on the upper-cased descriptor); first match wins
GROUPS = {
    "chatgpt": [("Google Play (GOOGLE *CHATGPT)", r"GOOGLE.{0,3}CHATGPT"),
                ("PayPal-funded (PAYPAL *OPENAI / OPENAIOPCO)", r"PAYPAL|PP\*|OPENAIOPCO"),
                ("Web (OPENAI *CHATGPT SUBSCR)", r"CHATGPT|OPENAI ?\* ?CH")],
    "claude": [("Google Play (GOOGLE *CLAUDE BY ANTH / GOOGLE *ANTHROPIC)", r"GOOGLE"),
               ("Older web descriptor without the dot (CLAUDEAI SUBSCRIPTION)", r"CLAUDEAI"),
               ("Web without the Stripe star (ANTHROPIC CLAUDE)", r"ANTHROPIC CLAUDE")],
    "gemini": [("New SKU code, AI plans (GOOGLE *G1AI101M / G1AI103M)", r"G1AI"),
               ("New SKU code, 2TB incl. AI Plus (GOOGLE *G1SK003M)", r"G1SK"),
               ("Standard GOOGLE ONE text on untagged merchant IDs", r"GOOGLE ?ONE|GOOGLE \*GOOGLE")],
    "grok": [("Current xAI web descriptor (GROK XAI WWW.GROK.COM), since Mar-2026", r"GROK XAI|GROK ?XAI"),
             ("Google Play via PayPal (PP*GOOGLE GROK)", r"GOOGLE")],
    "grok_x": [("Masked X Corp descriptor (CORP. PAID FEATURES ABOUT. .COM)", r"CORP\.? ?PA"),
               ("Google Play (GOOGLE *X CORP / TWITTER)", r"GOOGLE")],
    "perplexity": [("Brandless Stripe descriptor (PRO / MAX WWW.PERPLEX), Jun-Oct 2026", r"^(?:.*\s)?(?:PRO|MAX)\*?(?: TRIAL OVER)? ?WWW\.PERPLEX|^(?:PRO|MAX)$|^PRO,|^PRO SAN"),
                   ("PayPal / Google Play via PayPal (PERPLEXI PAYPAL ...)", r"PAYPAL|PP\*")],
    "muse": [("Direct web (METAPAY META.COM)", r"METAPAY"),
             ("Google Play (GOOGLE *MUSE FROM META)", r"MUSE FROM META")],
}


def group(m: pd.DataFrame) -> pd.Series:
    out = pd.Series("Other", index=m.index)
    up = m.descr.fillna("").str.upper()
    for p, gs in GROUPS.items():
        sel = m.provider.eq(p)
        lab = pd.Series(pd.NA, index=m.index[sel], dtype="object")
        for name, pat in gs:
            hit = lab.isna() & up[sel].str.contains(pat, regex=True)
            lab[hit] = name
        out[sel] = lab.fillna("Other").values
    return out


if __name__ == "__main__":
    pd.set_option("display.width", 250); pd.set_option("display.max_rows", 300); pd.set_option("display.max_colwidth", 70)
    m = pd.read_parquet(CACHE / "audit_payments.parquet")
    m["dt"] = pd.to_datetime(m.dt)
    # X.COM (29913) is X Corp's brand: its Google Play rows are correctly tagged (audit cache predates the fix)
    m.loc[(m.provider == "grok_x") & m.main_brand_id.eq(29913), "status"] = "tagged"
    m["issue_group"] = group(m)
    print("other_brand detail:")
    print(m[m.status == "other_brand"].groupby(["provider", "main_brand", "descr"]).size().sort_values(ascending=False).head(15))
    bad = m[m.status != "tagged"]
    g = (bad.groupby(["provider_name", "issue_group"]).agg(payments=("transid", "size"), members=("uid", "nunique"),
                                                          first=("dt", "min"), last=("dt", "max"))
            .reset_index())
    tot = m.groupby("provider_name").transid.size()
    g["share_of_provider_payments"] = g.payments / g.provider_name.map(tot)
    print(g.sort_values(["provider_name", "payments"], ascending=[True, False]).to_string(index=False))
    q = m.assign(q=m.dt.dt.to_period("Q")).groupby(["provider_name", "q"]).status.apply(lambda s: (s != "tagged").mean()).unstack().round(3)
    print(q.to_string())
    # examples: 3 most recent per group, distinct descriptors, from different members
    ex = (bad.sort_values("dt", ascending=False).drop_duplicates(["issue_group", "descr"]).drop_duplicates(["issue_group", "uid"])
             .groupby(["provider_name", "issue_group"]).head(3))
    print(ex[["provider_name", "issue_group", "transid", "dt", "amount", "descr", "plan", "main_brand", "payment_brand"]].to_string(index=False))
    ex.to_parquet(CACHE / "audit_examples.parquet", index=False)
    # workbook for Consumer Edge: summary, quarterly untagged share, issue groups, up to 10 examples per group
    ex10 = (bad.sort_values("dt", ascending=False).drop_duplicates(["issue_group", "uid"])
               .groupby(["provider_name", "issue_group"]).head(10))
    cols = ["provider_name", "issue_group", "status", "transid", "dt", "amount", "descr", "plan", "channel",
            "main_brand_id", "main_brand", "payment_brand_id", "payment_brand"]
    summ = (m.groupby("provider_name").agg(plan_payments=("transid", "size"),
                                            tagged_to_provider=("status", lambda s: (s == "tagged").sum()),
                                            untagged=("status", lambda s: (s == "untagged").sum()),
                                            other_brand=("status", lambda s: (s == "other_brand").sum())).reset_index())
    summ["share_not_tagged"] = 1 - summ.tagged_to_provider / summ.plan_payments
    with pd.ExcelWriter(CACHE.parent.parent / "docs" / "omega_282_ai_tagging_examples.xlsx") as xw:
        pd.DataFrame({"note": [
            "Omega 282 (prime_enriched_omega_2822), 2022 consistent-shopper panel, transactions 2025-01-01 to 2026-10-22.",
            "Plan payments = consumer subscription payments identified by descriptor and plan price (refunds, API, Team/Business excluded).",
            "tagged = MID_MATCH main_brand_id is the provider's brand (OPENAI 27440, ANTHROPIC 29847, GOOGLE ONE 32111, PERPLEXITY 29069, "
            "X.AI 32064, X.COM 29913, FACEBOOK 11021 / META STORE 27954); untagged = no main brand; other_brand = a different main brand.",
            "Brand ids checked against MID_MATCH_V1_0 on 2026-10-23."]}).to_excel(xw, sheet_name="read_me", index=False)
        summ.to_excel(xw, sheet_name="summary", index=False)
        q.reset_index().to_excel(xw, sheet_name="share_not_tagged_by_qtr", index=False)
        g.sort_values(["provider_name", "payments"], ascending=[True, False]).to_excel(xw, sheet_name="issue_groups", index=False)
        ex10[cols].assign(dt=ex10.dt.dt.date).sort_values(["provider_name", "issue_group", "dt"]).to_excel(
            xw, sheet_name="examples", index=False)
    print(summ.to_string(index=False))
    g.to_parquet(CACHE / "audit_groups.parquet", index=False)
    q.to_parquet(CACHE / "audit_quarterly.parquet")
