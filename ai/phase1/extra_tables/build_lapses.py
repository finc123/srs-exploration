"""Rebuild the t6 confirmed-lapse table (US) and cancel events; save locally for presence tests."""
import sys, os; P = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, P)
os.chdir(P)
from t6_cancel_scaling import build
L, cn, allpay, data_end, c = build()
L.to_parquet("extra_tables/L_us.parquet"); cn.to_parquet("extra_tables/cn_us.parquet")
c[["uid","prov","channel","dt","plan","amount"]].to_parquet("extra_tables/charges_us.parquet")
print(len(L), len(cn), data_end)
