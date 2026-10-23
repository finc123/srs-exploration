"""Compares the hashed samples from overlap_sample.py. For each ordered pair (A, B): what share of A is also in B?
Because both tables are sampled on the same hash of the id, an id in A's sample is in B's sample whenever it is in B at all,
so containment = |A_sample ∩ B_sample| / |A_sample| estimates |A ∩ B| / |A| for that day.
Match types:
  txn      A.txn_id     in B.txn_id
  partner  A.partner_id in B.partner_id
  x_id     A.txn_id in B.partner_id, or A.partner_id in B.txn_id (ids that change name between vendors)
  member   A.member_id  in B.member_id
  row      among members in both, A's (member, date, rounded |amount|) rows also in B — for vendors whose txn ids differ."""
import os, itertools
import pandas as pd

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results", "overlap")


def load():
    s = {}
    for f in sorted(os.listdir(OUT)):
        if f.endswith(".parquet"):
            df = pd.read_parquet(os.path.join(OUT, f))
            s[f[:-8]] = df[df.kind == "row"].copy()
    return s


def share(a, b):
    a, b = set(a.dropna()), set(b.dropna())
    return (len(a & b) / len(a), len(a)) if a else (float("nan"), 0)


def compare(s):
    out = []
    for A, B in itertools.permutations(s, 2):
        a, b = s[A], s[B]
        r = {"A": A, "B": B}
        r["txn"], r["n_txn"] = share(a[a.s_txn].txn_id, b[b.s_txn].txn_id)
        r["partner"], r["n_partner"] = share(a[a.s_partner].partner_id, b[b.s_partner].partner_id)
        x1 = share(a[a.s_txn].txn_id, b[b.s_partner].partner_id)[0]
        x2 = share(a[a.s_partner].partner_id, b[b.s_txn].txn_id)[0]
        r["x_id"] = max(v for v in (x1, x2, 0) if v == v)
        r["member"], r["n_member"] = share(a[a.s_mem].member_id, b[b.s_mem].member_id)
        am, bm = a[a.s_mem], b[b.s_mem]
        both = set(am.member_id) & set(bm.member_id)
        if both:
            key = lambda d: set(zip(d.member_id, d.txn_date.astype(str), d.amount.astype(float).abs().round(2)))
            r["row"], r["n_row"] = share(pd.Series(list(key(am[am.member_id.isin(both)]))), pd.Series(list(key(bm[bm.member_id.isin(both)]))))
        out.append(r)
    return pd.DataFrame(out)


if __name__ == "__main__":
    s = load()
    tot = pd.read_csv(os.path.join(OUT, "totals.csv")).drop_duplicates("key", keep="last")
    print(tot.to_string(index=False))
    res = compare(s)
    res.to_csv(os.path.join(OUT, "pairs.csv"), index=False)
    pd.set_option("display.width", 250, "display.max_rows", 500)
    for m in ["txn", "partner", "x_id", "member", "row"]:
        print(f"\n== {m}: share of row-table's sample found in column-table ==")
        print(res.pivot(index="A", columns="B", values=m).round(2).to_string())
