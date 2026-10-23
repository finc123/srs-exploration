"""Combine per-run metric folders (.cache/metrics_omega, .cache/metrics_eu) into .cache/metrics."""
from pathlib import Path
import pandas as pd

C = Path(__file__).parent / ".cache"
OUT = C / "metrics"
OUT.mkdir(exist_ok=True)
for f in (C / "metrics_omega").glob("*.parquet"):
    pd.concat([pd.read_parquet(d / f.name) for d in (C / "metrics_omega", C / "metrics_eu")]).to_parquet(OUT / f.name, index=False)
    print(f.name)
