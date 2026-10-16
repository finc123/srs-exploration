"""Lets card_datasets_inventory.ipynb take its warehouse, December-count timeout and retry flag from
environment variables (defaults unchanged). Idempotent: running it twice changes nothing."""
import os
import nbformat as nbf

NB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "card_datasets_inventory.ipynb")
REPLACEMENTS = [
    ('CONN_NAME = os.getenv("SNOWFLAKE_CONNECTION", "default")\n',
     'CONN_NAME = os.getenv("SNOWFLAKE_CONNECTION", "default")\n'
     'WAREHOUSE = os.getenv("CARD_INV_WAREHOUSE")             # e.g. LARGE for the heavy December counts\n'
     'CONN_KW = {"warehouse": WAREHOUSE} if WAREHOUSE else {}\n'),
    ("connect(connection_name=CONN_NAME)", "connect(connection_name=CONN_NAME, **CONN_KW)"),
    ("DEC_TIMEOUT_S = 1800\n", 'DEC_TIMEOUT_S = int(os.getenv("CARD_INV_DEC_TIMEOUT_S", "1800"))\n'),
    ("RETRY_FAILED = False\n", 'RETRY_FAILED = os.getenv("CARD_INV_RETRY_FAILED") == "1"   # retry cached timeouts / errors\n'),
]

nb = nbf.read(NB, as_version=4)
changed = 0
for cell in nb.cells:
    if cell.cell_type != "code":
        continue
    src = cell.source
    for old, new in REPLACEMENTS:
        if old in src and new not in src:
            src = src.replace(old, new)
            changed += 1
    cell.source = src
nbf.write(nb, NB)
print(f"patched {changed} spot(s) in {NB}")
