"""Fixes two type bugs that stop the results cells (both found after the first full run). Idempotent.
1. Snowflake returns INFORMATION_SCHEMA row_count / bytes as Decimal, which breaks `bytes / 1e9`:
   cast them to numbers right after the metadata pull.
2. data_from / data_to were python dates mixed with NaN, which breaks the per-database min / max:
   keep them as pandas datetimes."""
import os
import nbformat as nbf

NB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "card_datasets_inventory.ipynb")
REPLACEMENTS = [
    ("objs = pd.concat(tabs, ignore_index=True)\n",
     "objs = pd.concat(tabs, ignore_index=True)\n"
     'objs["row_count"] = pd.to_numeric(objs.row_count, errors="coerce")   # Decimal from Snowflake\n'
     'objs["bytes"] = pd.to_numeric(objs.bytes, errors="coerce")\n'),
    ('inv["data_from"] = pd.to_datetime(inv.data_from).dt.date\n', 'inv["data_from"] = pd.to_datetime(inv.data_from)\n'),
    ('inv["data_to"] = pd.to_datetime(inv.data_to).dt.date\n', 'inv["data_to"] = pd.to_datetime(inv.data_to)\n'),
]

nb = nbf.read(NB, as_version=4)
changed = 0
for cell in nb.cells:
    if cell.cell_type != "code":
        continue
    for old, new in REPLACEMENTS:
        if old in cell.source and new not in cell.source:
            cell.source = cell.source.replace(old, new)
            changed += 1
nbf.write(nb, NB)
print(f"patched {changed} spot(s) in {NB}")
