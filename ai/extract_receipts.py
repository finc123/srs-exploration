"""Candidate extract for AI-subscription tracking on e-receipt panels.

US: SRS_SLICE.COMMON.ITEMS_LIVE (NIQ / Slice), active mailboxes only (the Muse app convention; a mailbox that is now
    inactive is removed from history). One row per receipt line item.
EU: SHARE_NIQ.SRS.FOX_TRANSACTION_ITEMS (NIQ Fox), UK/DE/FR/ES/IT. One row per item.

Outputs to .cache/receipts/:
  us_ai_items.parquet     line items whose merchant or text matches RECEIPT_KEYWORDS (cancellation senders included)
  us_mailboxes.parquet    active mailboxes with ENTRY_DATE (denominator)
  eu_ai_items.parquet     Fox items matching RECEIPT_KEYWORDS (merchant, seller, product name/description)
  eu_spells.parquet       per-user activity spells (any receipt; gap <= 90 days) for the exit rule and denominator
  eu_users.parquet        FOX_MAILBOXES user, country, created date

Usage: python extract_receipts.py [us] [eu]
"""
import sys, time
from pathlib import Path
import snowflake.connector as sc

OUT = Path(__file__).parent / ".cache" / "receipts"
START, ACT_START, EU_GAP = "2022-01-01", "2022-01-01", 90

RECEIPT_KEYWORDS = [
    "%chatgpt%", "%chat gpt%", "%openai%", "%anthropic%", "%claude%",
    "%google one%", "%google ai%", "%gemini%", "%ai premium%",
    "%grok%", "%xai%", "%x premium%", "%premium+%", "%twitter%", "%x corp%",
    "%muse from meta%", "%power plan%", "%maximum plan%",
    "%cursor%", "%anysphere%", "%perplexity%",
]


def match(col: str) -> str:
    return f"({col}) ILIKE ANY ({', '.join(repr(k) for k in RECEIPT_KEYWORDS)})"


def pull(cur, sql, name):
    t = time.time()
    cur.execute(sql)
    df = cur.fetch_pandas_all()
    df.columns = [c.lower() for c in df.columns]
    df.to_parquet(OUT / f"{name}.parquet", index=False)
    print(f"{name}: {len(df):,} rows, {time.time() - t:.0f}s", flush=True)


def us(cur):
    txt = "merchant_name || ' ' || COALESCE(item_description, '')"
    pull(cur, f"""SELECT mailbox_id AS uid, userid, orderdate AS dt, email_sent_time, merchant_name, merchant_id,
                         item_description AS descr, item_price, item_qty, ordertotal, tax, slice_order_id, item_id,
                         quality, digital_good, category_name, record_status, entry_date
                  FROM SRS_SLICE.COMMON.ITEMS_LIVE
                  WHERE orderdate BETWEEN '{START}' AND CURRENT_DATE AND mailbox_status = 'ACTIVE' AND {match(txt)}""",
         "us_ai_items")
    pull(cur, """SELECT mailbox_id AS uid, MIN(entry_date) AS entry_date FROM SRS_SLICE.COMMON.ITEMS_LIVE
                 WHERE mailbox_status = 'ACTIVE' GROUP BY 1""", "us_mailboxes")


def eu(cur):
    F = "SHARE_NIQ.SRS.FOX_TRANSACTION_ITEMS"
    txt = "COALESCE(merchant_name,'') || ' ' || COALESCE(seller_name,'') || ' ' || COALESCE(product_name,'') || ' ' || COALESCE(product_description,'')"
    pull(cur, f"""SELECT user_id AS uid, country, TO_DATE(order_date) AS dt, email_type, merchant_name, seller_name,
                         product_name, product_description AS descr, item_price, item_quantity, order_total, order_currency,
                         order_id, item_id, industry, order_attributes:aux_data:payment_method::string AS payment_method,
                         order_attributes::string AS order_attributes
                  FROM {F} WHERE order_date >= '{START}' AND {match(txt)}""", "eu_ai_items")
    pull(cur, f"""WITH d AS (SELECT DISTINCT user_id AS uid, TO_DATE(order_date) AS dt FROM {F} WHERE order_date >= '{ACT_START}'),
                  g AS (SELECT uid, dt, IFF(DATEDIFF(day, LAG(dt) OVER (PARTITION BY uid ORDER BY dt), dt) <= {EU_GAP}, 0, 1) AS new_spell FROM d),
                  s AS (SELECT uid, dt, SUM(new_spell) OVER (PARTITION BY uid ORDER BY dt ROWS UNBOUNDED PRECEDING) AS spell FROM g)
                  SELECT uid, spell, MIN(dt) AS spell_start, MAX(dt) AS spell_end, COUNT(*) AS active_days FROM s GROUP BY 1, 2""",
         "eu_spells")
    pull(cur, "SELECT user_id AS uid, customer_country AS country, customer_created_at::DATE AS created FROM SHARE_NIQ.SRS.FOX_MAILBOXES",
         "eu_users")


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    con = sc.connect(connection_name="default", warehouse="ANALYST_XL", network_timeout=7200)
    cur = con.cursor()
    cur.execute("ALTER SESSION SET STATEMENT_TIMEOUT_IN_SECONDS = 7200")
    for p in sys.argv[1:] or ["us", "eu"]:
        us(cur) if p == "us" else eu(cur)
