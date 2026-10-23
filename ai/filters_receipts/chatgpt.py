"""ChatGPT (OpenAI) consumer subscription filter for the e-receipt panels (NIQ US items, NIQ Fox EU).

classify(df, panel) -> one row per candidate ChatGPT item with plan (tier x cadence), channel, kind, keep, reason.
See filters_receipts/chatgpt_report.md. Plan prices / bands reuse filters/chatgpt.py and plans/chatgpt_prices.csv.

Rules
- Plan from the text first ('plus', 'go', 'pro 5x'/'pro 100' -> pro100, 'pro 20x'/'pro 200' -> pro200,
  'pro 25x'/'pro 500' -> pro500, bare 'pro' -> by amount), cadence from the period word (annual/annuel/jahrlich/
  annuale/anual/yearly -> A, else M). Rows with no plan text (bare Apple 'chatgpt', PayPal OpenAI with no product)
  are mapped by amount bands per currency.
- Channels: apple, google_play (incl. PayPal payments to Google for ChatGPT), paypal (payee OpenAI), stripe
  (OpenAI LLC / OpCo / Ireland invoices), direct (sender 'chatgpt' / 'Chat GPT'). Direct ChatGPT sends a sign-up
  receipt only, so renews=False for direct; every other channel renews=True.
- Rejected (keep=False): $0 / trial, implausibly small amounts (< 40% of list, e.g. VAT fragments), Business / Team /
  Enterprise, credits / 'usage reset' / top-ups, Sora, third-party 'powered by ChatGPT' apps, gift-key resellers,
  refunds / adjustments, Apple renewal notices ('se renueva', 'verlangert sich', 'renews'), Fox spam / deleted /
  flag only (EXCLUDE_FLAGS; deleted/trash kept), duplicates (same uid, day, channel, plan, amount).
- Cancels: EU direct email_type='cancel' (unpriced, plan unknown_M); Apple rows whose product carries a cancellation
  date ('cancellation date', 'cancelled', 'date de (la) resiliation', 'data di annullamento', 'annullato il giorno',
  'fecha de cancelacion', 'gekundigt') with end_date parsed; US 'Chat GPT Cancellation' / 'iTunes Cancellation' /
  'Google Play Cancellation' senders. Trial endings are excluded.
"""
import re
import numpy as np
import pandas as pd

PROVIDER = "chatgpt"
T = pd.Timestamp
D0 = T("2000-01-01")
EXCLUDE_FLAGS = ("order_is_spam",)  # deleted / trash are genuine receipts the user later removed: kept

# Amount bands per currency (plan, lo, hi, valid_from). Include ex-VAT amounts (Fox direct item_price is net) and
# 50% promos (Plus retention, Go intro). First match wins.
BANDS = {
    "usd": [("go_M", 3.95, 4.45, T("2025-12-15")), ("go_M", 7.50, 9.00, T("2025-08-01")),
            ("plus_M", 9.95, 11.30, T("2025-01-01")), ("plus_M", 19.00, 24.50, D0),
            ("pro100_M", 99.00, 111.00, T("2026-04-09")), ("pro200_M", 199.00, 245.00, T("2024-12-05")),
            ("pro500_M", 499.00, 555.00, T("2026-09-29"))],
    "eur": [("go_M", 3.90, 4.10, T("2025-12-15")), ("go_M", 6.50, 10.10, T("2025-11-01")),
            ("plus_M", 9.00, 12.50, T("2025-01-01")), ("plus_M", 16.50, 25.90, D0),
            ("pro100_M", 80.00, 106.00, T("2026-04-09")), ("pro200_M", 180.00, 246.00, T("2024-12-05")),
            ("pro500_M", 415.00, 520.00, T("2026-09-29"))],
    "gbp": [("go_M", 3.40, 4.10, T("2025-12-15")), ("go_M", 5.50, 8.10, T("2025-12-15")),
            ("plus_M", 8.30, 10.10, T("2025-01-01")), ("plus_M", 14.00, 20.60, D0),
            ("pro100_M", 74.00, 92.00, T("2026-04-09")), ("pro200_M", 160.00, 201.00, T("2024-12-05")),
            ("pro500_M", 370.00, 505.00, T("2026-09-29"))],
}
LIST = {"go": 8.0, "plus": 20.0, "pro100": 89.0, "pro200": 200.0, "pro500": 445.0}  # lowest list price (any ccy)

ANNUAL_RX = r"\((?:annual|annuel|jahrlich|jährlich|annuale|anual|yearly|1 year|1 an|1 jahr|1 anno|1 ano)\b"
EXCL_RX = {
    "business_team": r"\bbusiness\b|\bteam\b|enterprise|\bedu\b|per seat.*(?:team|business)",
    "credits": r"credits?\b|usage reset|top ?up|flexible usage",
    "sora": r"\bsora\b",
}
RENEW_NOTICE_RX = r"se renueva|verlangert sich|verlängert sich|renews on|renews \d|si rinnova|se renouvelle|renouvellement"
CANCEL_TAIL_RX = (r"cancellation date|cancell?ed\b|date de (?:la )?resiliation|data di annullamento|annullato il giorno"
                  r"|fecha de cancelacion|gekundigt|gekündigt|kundigungsdatum|expires on|will (?:be )?(?:cancel|end)")
MONTHS = {  # month words in en/fr/de/it/es (accents stripped upstream in Fox)
    "jan": 1, "janv": 1, "januar": 1, "gennaio": 1, "enero": 1, "janvier": 1,
    "feb": 2, "fev": 2, "fevrier": 2, "februar": 2, "febbraio": 2, "febrero": 2,
    "mar": 3, "mars": 3, "marz": 3, "märz": 3, "marzo": 3, "march": 3,
    "apr": 4, "avr": 4, "avril": 4, "april": 4, "aprile": 4, "abril": 4,
    "may": 5, "mai": 5, "maggio": 5, "mayo": 5,
    "jun": 6, "juin": 6, "juni": 6, "giugno": 6, "junio": 6, "june": 6,
    "jul": 7, "juil": 7, "juillet": 7, "juli": 7, "luglio": 7, "julio": 7, "july": 7,
    "aug": 8, "aout": 8, "août": 8, "august": 8, "agosto": 8,
    "sep": 9, "sept": 9, "septembre": 9, "september": 9, "settembre": 9, "septiembre": 9,
    "oct": 10, "octobre": 10, "oktober": 10, "ottobre": 10, "octubre": 10, "october": 10,
    "nov": 11, "novembre": 11, "november": 11, "noviembre": 11,
    "dec": 12, "decembre": 12, "dezember": 12, "dicembre": 12, "diciembre": 12, "december": 12,
}
DATE_RX = re.compile(r"(\d{1,2})\.?\s+(?:de\s+)?([a-zäéû]+)\.?\s+(?:de\s+)?(\d{4})|([a-z]+)\.?\s+(\d{1,2}),?\s+(\d{4})")


def _parse_date(s):
    if not isinstance(s, str):
        return pd.NaT
    m = DATE_RX.search(s)
    if not m:
        return pd.NaT
    if m.group(1):
        d, mon, y = m.group(1), m.group(2), m.group(3)
    else:
        mon, d, y = m.group(4), m.group(5), m.group(6)
    mo = MONTHS.get(mon) or MONTHS.get(mon[:4]) or MONTHS.get(mon[:3])
    try:
        return T(int(y), mo, int(d)) if mo else pd.NaT
    except ValueError:
        return pd.NaT


def _text_plan(t: pd.Series, amt: pd.Series, cur: pd.Series, dt: pd.Series) -> pd.Series:
    tier = pd.Series(None, index=t.index, dtype=object)
    tier[t.str.contains(r"\bplus\b")] = "plus"
    tier[t.str.contains(r"\bgo\b")] = "go"
    pro = t.str.contains(r"\bpro\b")
    tier[pro & t.str.contains(r"pro ?(?:5x|100)\b")] = "pro100"
    tier[pro & t.str.contains(r"pro ?(?:20x|200)\b")] = "pro200"
    tier[pro & t.str.contains(r"pro ?(?:25x|500)\b")] = "pro500"
    # bare 'pro': by amount (pro100 band if it fits, pro500 if it fits, else pro200)
    bare = pro & tier.isna()
    band = _band(amt, cur, dt)
    tier[bare] = np.where(band[bare].str.startswith("pro", na=False), band[bare].str.split("_").str[0], "pro200")
    tier[bare & amt.isna() & (dt >= T("2026-04-09"))] = "unknown"   # unpriced bare 'pro' (cancels) after Pro 100 launch
    return tier


def _band(amt: pd.Series, cur: pd.Series, dt: pd.Series) -> pd.Series:
    out = pd.Series(None, index=amt.index, dtype=object)
    for c, bands in BANDS.items():
        m0 = cur.eq(c)
        for plan, lo, hi, vf in bands:
            m = m0 & out.isna() & amt.between(lo, hi) & (dt >= vf)
            out[m] = plan
    return out


def _flags(attr: pd.Series) -> pd.Series:
    a = attr.fillna("")
    bad = pd.Series(False, index=attr.index)
    for k in EXCLUDE_FLAGS:
        bad |= a.str.contains(f'"{k}":"1"', regex=False)
    return bad


def _eu(df: pd.DataFrame) -> pd.DataFrame:
    mer = df.merchant_name.fillna("").str.lower()
    sel = df.seller_name.fillna("").str.lower()
    pn = df.product_name.fillna("").str.lower()
    de = df.descr.fillna("").str.lower()
    et = df.email_type.fillna("").str.lower()
    hit = (mer + "|" + sel + "|" + pn + "|" + de).str.contains(r"chat ?gpt|open ?ai(?!r)|\bsora\b")
    d = df[hit].copy()
    mer, sel, pn, de, et = mer[hit], sel[hit], pn[hit], de[hit], et[hit]
    o = pd.DataFrame(index=d.index)
    o["uid"] = d.uid
    o["dt"] = pd.to_datetime(d.dt)
    o["country"] = d.country
    o["currency"] = d.order_currency.fillna("").str.lower()
    ip, ot = d.item_price, d.order_total
    o["amount"] = np.where((mer == "chatgpt") & (ot > 0) & (ot < ip * 1.3 + 1), ot, ip)  # direct item_price is net
    o["text"] = pn.where(pn != "", de)
    o["channel"] = None
    o["kind"] = "charge"
    o["reason"] = None
    # --- channel / app identification
    apple = mer.eq("apple")
    apple_cg = apple & pn.str.match(r"^chatgpt(?: \|\||$)")
    gp_cg = (mer.eq("google play") | (mer.eq("paypal") & sel.eq("google"))) & pn.str.match(r"^chatgpt (?:plus|go|pro)\b") \
        & (pn.str.contains(r"\(chatgpt") | mer.eq("paypal"))
    gp_cg &= ~pn.str.contains(r"weekly|premium \d|assistant|chatbot")
    pp_oa = mer.str.startswith("paypal") & sel.eq("openai")
    pp_oa |= mer.eq("klarna") & sel.eq("openai")
    stripe_oa = mer.eq("stripe") & (sel.str.contains(r"openai\b") | pn.str.match(r"^openai (?:ireland|opco|, llc|llc)"))
    direct = mer.eq("chatgpt")
    o.loc[apple_cg, "channel"] = "apple"
    o.loc[gp_cg, "channel"] = "google_play"
    o.loc[pp_oa, "channel"] = "paypal"
    o.loc[stripe_oa, "channel"] = "stripe"
    o.loc[direct, "channel"] = "direct"
    o.loc[o.channel.isna(), "channel"] = "other"
    o.loc[o.channel.eq("other"), "reason"] = "third_party_or_unrelated"
    o.loc[o.channel.eq("other") & sel.isin(["g2a", "kinguindigital", "etsy", "eneba"]), "reason"] = "reseller"
    # --- kind
    o.loc[direct & et.eq("cancel"), "kind"] = "cancel"
    tail = pn.str.extract(r"\)\s*(.+)$")[0].fillna("")
    o.loc[apple_cg & tail.str.contains(CANCEL_TAIL_RX), "kind"] = "cancel"
    o.loc[apple_cg & tail.str.contains(RENEW_NOTICE_RX) & o.kind.eq("charge"), "reason"] = "renewal_notice"
    o.loc[et.str.startswith("return") | pn.eq("adjustment"), "reason"] = "refund_adjustment"
    o["end_date"] = pd.NaT
    ac = o.kind.eq("cancel") & apple_cg
    o.loc[ac, "end_date"] = tail[ac].map(_parse_date)
    o.loc[o.kind.eq("cancel"), "amount"] = np.nan
    o["_flag"] = _flags(d.order_attributes)
    return o


def _us(df: pd.DataFrame) -> pd.DataFrame:
    mer = df.merchant_name.fillna("").str.lower()
    de = df.descr.fillna("").str.lower()
    hit = (mer + "|" + de).str.contains(r"chat ?gpt|open ?ai(?!r)|\bsora\b")
    d = df[hit].copy()
    mer, de = mer[hit], de[hit]
    o = pd.DataFrame(index=d.index)
    o["uid"] = d.uid
    o["dt"] = pd.to_datetime(d.dt)
    o["country"] = "us"
    o["currency"] = "usd"
    direct = mer.str.match(r"^(?:chat ?gpt|openai)") & ~mer.str.contains("cancel")
    ot = d.ordertotal
    # direct: ordertotal carries sales tax (single-item email); Apple/Play ordertotal is the whole email -> item_price
    o["amount"] = np.where(direct & (ot > 0) & (ot < d.item_price * 1.3 + 1), ot, d.item_price)
    o["text"] = de
    o["channel"] = "other"
    o["kind"] = "charge"
    o["reason"] = None
    cancel_sender = mer.str.contains("cancel")
    itunes = mer.str.match(r"^(?:itunes|apple)")
    gplay = mer.str.match(r"^google play")
    paypal = mer.str.match(r"^paypal")
    app_cg = de.str.match(r"^chatgpt(?: :| chatgpt| \d+ credits)")
    gp_cg = (de.str.match(r"^chatgpt (?:plus|go|pro)\b") & de.str.contains(r"\(chatgpt\)")) | de.str.contains(
        r"chatgpt subscription from (?:openai|google commerce)|^chatgpt \(chatgpt|purchase from openai")
    o.loc[itunes & app_cg, "channel"] = "apple"
    o.loc[gplay & gp_cg, "channel"] = "google_play"
    o.loc[mer.str.match(r"^(?:chat ?gpt|openai)"), "channel"] = "direct"
    o.loc[paypal & de.str.contains(r"openai|chat ?gpt"), "channel"] = "paypal"
    o.loc[o.channel.eq("other"), "reason"] = "third_party_or_unrelated"
    o.loc[cancel_sender, "kind"] = "cancel"
    ch = o.kind.eq("charge")
    o.loc[ch & o.reason.isna() & direct & de.eq("payment"), "reason"] = "credits"   # API prepaid credit purchases
    o.loc[ch & o.reason.isna() & de.str.contains(r"searchgpt"), "reason"] = "trial_or_zero"
    o.loc[ch & o.reason.isna() & de.str.contains(r"refund"), "reason"] = "refund_adjustment"
    o.loc[ch & o.reason.isna() & de.str.contains(r"your trial will end|free trial"), "reason"] = "trial_or_zero"
    o.loc[ch & o.reason.isna() & itunes & de.str.contains(r"/ ?(?:month|year|week)|^chatgpt chatgpt"),
          "reason"] = "unpriced_confirmation"
    o["end_date"] = pd.NaT
    c = o.kind.eq("cancel")
    full = de.str.extract(r"(?:on|until)\s+([a-z]+\.? \d{1,2},? \d{4})")[0]
    md = de.str.extract(r"end on ([a-z]+) (\d{1,2})\b")
    y = o.dt.dt.year.astype(str)
    md_s = md[0] + " " + md[1] + ", " + y
    o.loc[c, "end_date"] = full.where(full.notna(), md_s)[c].map(_parse_date)
    rolled = c & (o.end_date < o.dt - pd.Timedelta(days=31)) & full.isna()
    o.loc[rolled, "end_date"] = o.loc[rolled, "end_date"] + pd.DateOffset(years=1)
    o.loc[c & de.str.contains(r"trial"), "reason"] = "trial_end"
    o.loc[c & de.str.contains(r"\bfree subscription"), "reason"] = "free_plan"
    o.loc[c & de.str.contains(r"purchase from openai"), "reason"] = "purchase_voided"
    o.loc[c, "amount"] = np.nan
    o["_flag"] = False
    return o


def classify(df: pd.DataFrame, panel: str) -> pd.DataFrame:
    o = _eu(df) if panel == "eu" else _us(df)
    t = o.text.fillna("").str.lower()
    amt = pd.to_numeric(o.amount, errors="coerce")
    ch = o.kind.eq("charge")
    o["provider"] = PROVIDER
    # exclusions by text
    for r, rx in EXCL_RX.items():
        o.loc[o.reason.isna() & t.str.contains(rx), "reason"] = r
    # plan
    tier = _text_plan(t, amt, o.currency, o.dt)
    band = _band(amt, o.currency, o.dt)
    has_text = tier.notna()
    tier = tier.where(has_text, band.str.split("_").str[0])
    o["cadence"] = np.where(t.str.contains(ANNUAL_RX), "A", "M")
    o["tier"] = tier
    # charge validity
    o.loc[ch & o.reason.isna() & (amt.isna() | (amt <= 0) | t.str.contains(r"\btrial\b|probeabo")), "reason"] = "trial_or_zero"
    o.loc[ch & o.reason.isna() & tier.isna(), "reason"] = "amount_unmapped"
    lst = tier.map(LIST) * np.where(o.cadence.eq("A"), 10, 1)
    o.loc[ch & o.reason.isna() & (amt < 0.4 * lst), "reason"] = "amount_implausible"
    # cancels: plan from text where possible (Apple), else unknown_M
    cn = o.kind.eq("cancel")
    o.loc[cn & ~has_text, "tier"] = "unknown"
    o.loc[cn & ~has_text, "cadence"] = "M"
    o["plan"] = o.tier.fillna("unknown") + "_" + o.cadence
    o.loc[o.reason.isna() & o._flag, "reason"] = "fox_spam"
    o["renews"] = ~o.channel.eq("direct")
    o.loc[o.reason.isna(), "reason"] = "ok"
    # de-duplicate repeated line items
    ok = o[o.reason.eq("ok")].assign(_a=amt.round(0).fillna(-1))
    dup = ok.duplicated(["uid", "dt", "channel", "plan", "kind", "_a"])
    o.loc[dup[dup].index, "reason"] = "duplicate"
    o["keep"] = o.reason.eq("ok")
    o["amount"] = amt.where(ch)
    o.loc[~ch, "currency"] = None
    cols = ["uid", "dt", "country", "provider", "tier", "cadence", "plan", "channel", "kind", "amount", "currency",
            "end_date", "renews", "keep", "reason", "text"]
    return o[cols].sort_values(["uid", "dt"]).reset_index(drop=True)
