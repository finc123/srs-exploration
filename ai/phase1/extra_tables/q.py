"""Helper: python q.py "SQL" [maxrows]  or python q.py -f file.sql"""
import sys, snowflake.connector as sc, pandas as pd
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 50); pd.set_option("display.max_colwidth", 120)
def run(sql, wh="ANALYST_L"):
    con = sc.connect(connection_name="default", warehouse=wh, network_timeout=3600)
    cur = con.cursor(); cur.execute("ALTER SESSION SET STATEMENT_TIMEOUT_IN_SECONDS = 3600")
    out = None
    for s in [x for x in sql.split(";\n") if x.strip()]:
        cur.execute(s)
        try: out = cur.fetch_pandas_all()
        except Exception:
            try: out = pd.DataFrame(cur.fetchall(), columns=[d[0] for d in cur.description])
            except Exception: out = None
    return out
if __name__ == "__main__":
    a = sys.argv[1:]
    wh = "ANALYST_L"
    if a and a[0].startswith("--wh="): wh = a.pop(0)[5:]
    sql = open(a[1]).read() if a[0] == "-f" else a[0]
    n = int(a[2] if a[0]=="-f" and len(a)>2 else (a[1] if a[0]!="-f" and len(a)>1 else 200))
    df = run(sql, wh)
    if df is not None: print(df.head(n).to_string())
