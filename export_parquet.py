import argparse
from telemetry.analytics import to_parquet
p=argparse.ArgumentParser();p.add_argument("src");p.add_argument("dst")
a=p.parse_args();print(f"Scritte {to_parquet(a.src,a.dst)} righe in {a.dst}")
