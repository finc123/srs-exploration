"""Phase 1 Snowflake pulls (read-only; temp tables in SRS_MCP.SANDBOX).

For every mailbox/user with an AI paid receipt (from the classified caches):
  {us,eu}_activity.parquet  uid, month, n_orders (any merchant)          -> is the mailbox sending at all?
  {us,eu}_ref.parquet       uid, dt, ref, channel, price                  -> a different recurring sender per channel
    ref senders: icloud (Apple iCloud+), gplay_storage (Google One storage on Google Play), youtube (YouTube Premium,
    any store), spotify (Spotify direct). Paid rows only (price > 0).
"""
import sys, time
from pathlib import Path
import pandas as pd
import snowflake.connector as sc
from snowflake.connector.pandas_tools import write_pandas

HERE = Path(__file__).parent
C = HERE.parent / ".cache" / "receipts"
OUT = HERE / "data"
START = "2023-01-01"


def q(cur, sql, name):
    t = time.time()
    cur.execute(sql)
    df = cur.fetch_pandas_all()
    df.columns = [c.lower() for c in df.columns]
    df.to_parquet(OUT / f"{name}.parquet", index=False)
    print(f"{name}: {len(df):,} rows {time.time() - t:.0f}s", flush=True)


def upload(con, cur, region):
    x = pd.read_parquet(C / f"{region}_classified.parquet", columns=["uid", "kind"])
    u = pd.DataFrame({"UID": x.loc[x["kind"] == "charge", "uid"].astype(str).unique()})
    cur.execute(f"CREATE OR REPLACE TEMPORARY TABLE P1_UID_{region.upper()} (UID STRING)")
    write_pandas(con, u, f"P1_UID_{region.upper()}", database="SRS_MCP", schema="SANDBOX", quote_identifiers=False)
    print(region, "uids", len(u), flush=True)


def us(con, cur):
    upload(con, cur, "us")
    T = "SRS_SLICE.COMMON.ITEMS_LIVE"
    q(cur, f"""SELECT i.mailbox_id AS uid, DATE_TRUNC('month', orderdate) AS month, COUNT(DISTINCT slice_order_id) AS n_orders
               FROM {T} i JOIN P1_UID_US u ON i.mailbox_id = u.uid
               WHERE orderdate >= '{START}' AND orderdate <= CURRENT_DATE AND mailbox_status = 'ACTIVE' GROUP BY 1, 2""",
      "us_activity")
    q(cur, f"""SELECT i.mailbox_id AS uid, orderdate AS dt, merchant_name, item_description AS descr, item_price AS price
               FROM {T} i JOIN P1_UID_US u ON i.mailbox_id = u.uid
               WHERE orderdate >= '{START}' AND orderdate <= CURRENT_DATE AND mailbox_status = 'ACTIVE' AND item_price > 0
                 AND ((merchant_name = 'iTunes' AND item_description ILIKE 'icloud%icloud+%')
                   OR (merchant_name = 'Google Play' AND item_description ILIKE '%(Google One)%' AND item_description NOT ILIKE '%AI %')
                   OR (item_description ILIKE '%youtube premium%' AND merchant_name IN ('iTunes', 'Google Play', 'Youtube Premium'))
                   OR (merchant_name = 'Spotify' AND item_description ILIKE 'premium%'))""", "us_ref_raw")
    q(cur, f"""SELECT i.mailbox_id AS uid, MIN(entry_date) AS entry_date, MAX(exit_date) AS exit_date, MAX(mailbox_status) AS status
               FROM {T} i JOIN P1_UID_US u ON i.mailbox_id = u.uid WHERE orderdate >= '2026-01-01' GROUP BY 1""", "us_mbx")


def eu(con, cur):
    upload(con, cur, "eu")
    F = "SHARE_NIQ.SRS.FOX_TRANSACTION_ITEMS"
    q(cur, f"""SELECT f.user_id::string AS uid, DATE_TRUNC('month', TO_DATE(order_date)) AS month, COUNT(DISTINCT order_id) AS n_orders
               FROM {F} f JOIN P1_UID_EU u ON f.user_id::string = u.uid
               WHERE order_date >= '{START}' GROUP BY 1, 2""", "eu_activity")
    q(cur, f"""SELECT f.user_id::string AS uid, TO_DATE(order_date) AS dt, merchant_name, email_type, seller_name,
                      product_name AS descr, item_price AS price
               FROM {F} f JOIN P1_UID_EU u ON f.user_id::string = u.uid
               WHERE order_date >= '{START}' AND item_price > 0
                 AND ((merchant_name = 'apple' AND product_name ILIKE 'icloud%')
                   OR (merchant_name = 'google play' AND product_name ILIKE '%(google one)%' AND product_name NOT ILIKE '%ai %')
                   OR (product_name ILIKE '%youtube premium%')
                   OR (merchant_name = 'spotify' AND product_name ILIKE 'premium%'))""", "eu_ref_raw")


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    con = sc.connect(connection_name="default", warehouse="ANALYST_L", network_timeout=7200)
    cur = con.cursor()
    cur.execute("ALTER SESSION SET STATEMENT_TIMEOUT_IN_SECONDS = 7200")
    cur.execute("USE SCHEMA SRS_MCP.SANDBOX")
    for p in sys.argv[1:] or ["us", "eu"]:
        us(con, cur) if p == "us" else eu(con, cur)
