#!/usr/bin/env python3
"""Export closed R/As per day and branch from TSD into closed_ras.csv.

Same result as running query 1 of closed_ras.sql in Azure Data Studio and saving
the grid as CSV, without the manual steps:

    ~/.venvs/tsd/bin/python export_closed_ras.py      # then ./refresh_dashboard.py

Connection details and the query live in tsd_closed_ras.py.
"""
import csv
import sys
from pathlib import Path

from tsd_closed_ras import DEFAULT_SINCE, fetch_rows

HERE = Path(__file__).resolve().parent
OUT = HERE / 'closed_ras.csv'


def main():
    rows = fetch_rows(DEFAULT_SINCE)
    if not rows:
        sys.exit('TSD returned no closed R/As — not overwriting closed_ras.csv.')
    with OUT.open('w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['date', 'location', 'count'])
        w.writerows(rows)
    by_loc = {}
    for _, loc, n in rows:
        by_loc[loc] = by_loc.get(loc, 0) + n
    print(f'Wrote {OUT.name}: {len(rows):,} day/branch rows, {sum(by_loc.values()):,} closed R/As '
          f'from {rows[0][0]} to {rows[-1][0]}.')
    print('  ' + ', '.join(f'{k} {v:,}' for k, v in sorted(by_loc.items(), key=lambda kv: -kv[1])))


if __name__ == '__main__':
    main()
