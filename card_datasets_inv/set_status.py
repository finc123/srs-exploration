"""Writes status.md into the notebook's '## Status' markdown cell. Idempotent."""
import os
import nbformat as nbf

here = os.path.dirname(os.path.abspath(__file__))
NB = os.path.join(here, "card_datasets_inventory.ipynb")
nb = nbf.read(NB, as_version=4)
cell = next(c for c in nb.cells if c.cell_type == "markdown" and c.source.startswith("## Status"))
cell.source = open(os.path.join(here, "status.md"), encoding="utf-8").read().rstrip()
nbf.write(nb, NB)
print("status cell updated")
