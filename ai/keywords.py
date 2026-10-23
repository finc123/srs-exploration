"""Broad descriptor keywords for the AI-subscription candidate extract (deliberately over-inclusive;
provider filters are narrowed afterwards from the cached rows)."""

# ILIKE patterns, lowercase. Grouped by provider for the per-provider review.
KEYWORDS = {
    "chatgpt":    ["%chatgpt%", "%chat gpt%", "%openai%", "%open ai%"],
    "claude":     ["%anthropic%", "%claude.ai%", "%claude ai%", "%claude by%", "%claude sub%", "%claude pro%", "%claude max%", "%claudeai%", "%.ai subscri%"],
    "gemini":     ["%google one%", "%google*google one%", "%googleone%", "%gemini%", "%google ai pro%", "%google ai ultra%", "%google storage%", "%google *google storage%", "%g1sk%", "%g1ai%", "google%*g1 %", "%google%ttttt%"],
    "grok":       ["%grok%", "%x.ai%", "%xai %", "% xai%", "%x corp%", "%xcorp%", "%twitter%", "%x premium%", "%corp. paid f%", "%corp paid f%", "%corp. pa 865%", "% x.com%", "x.com%", "%*x.com%"],
    "muse":       ["%metapay%meta.com%", "%meta.com%", "%muse.ai%", "%muse ai%", "%muse from meta%"],
    "cursor":     ["%cursor%", "%anysphere%"],
    "perplexity": ["%perplex%", "pro", "cb pro%", "pro san franc%", "% pro san franc%", "pro, san franc%", "% pro, san franc%",
                   "max san franc%", "ent pro%", "credits san franc%", "computer san franc%"],
}


def where_sql(col: str) -> str:
    pats = sorted({p for ps in KEYWORDS.values() for p in ps})
    return "(" + " OR ".join(f"{col} ILIKE '{p}'" for p in pats) + ")"
