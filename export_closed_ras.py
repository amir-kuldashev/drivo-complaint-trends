#!/usr/bin/env python3
"""Export closed R/As per day and branch from TSD into closed_ras.csv.

Same result as running query 1 of closed_ras.sql in Azure Data Studio and saving
the grid as CSV, without the manual steps:

    ~/.venvs/tsd/bin/python export_closed_ras.py      # then ./refresh_dashboard.py

Needs the pymssql driver (pip install pymssql) and a credentials file at
~/.config/tsd/credentials with TSD_SERVER, TSD_PORT, TSD_DATABASE, TSD_USER and
TSD_PASSWORD lines. The file lives outside the repo so credentials are never
committed. TSD_DATABASE is the TSD customer database (42295), not DrivoDatabase,
which is empty.
"""
import csv
import sys
from pathlib import Path

try:
    import pymssql
except ImportError:
    sys.exit('The pymssql driver is not installed for this Python. Run\n'
             '    python3 -m venv ~/.venvs/tsd && ~/.venvs/tsd/bin/pip install pymssql\n'
             'and then run this script with ~/.venvs/tsd/bin/python.')

HERE = Path(__file__).resolve().parent
OUT = HERE / 'closed_ras.csv'
CREDENTIALS = Path.home() / '.config' / 'tsd' / 'credentials'
SINCE = '2025-01-01'

# Mirrors query 1 of closed_ras.sql: a closed R/A is a Cra001 contract with
# CLOSED_FLAG = 1 and TYPE C or H (not void, damage, transfer or wait status),
# counted on its check-in date under its check-out branch. Branch codes are kept
# as TSD has them (EWRCON separate); refresh_dashboard.py adds EWRCON into EWR.
SQL = """
SELECT CONVERT(varchar(10), CAST(ra.DATE_IN AS date), 23) AS [date],
       UPPER(LTRIM(RTRIM(ra.LOC_OUT)))                    AS [location],
       COUNT(*)                                           AS [count]
FROM dbo.Cra001 AS ra
WHERE ra.CLOSED_FLAG = 1
  AND ra.TYPE IN ('C', 'H')
  AND ra.DATE_IN >= %s
  AND ra.DATE_IN <  DATEADD(day, 1, CAST(GETDATE() AS date))
GROUP BY CAST(ra.DATE_IN AS date), UPPER(LTRIM(RTRIM(ra.LOC_OUT)))
ORDER BY [date], [location]
"""


def read_credentials():
    if not CREDENTIALS.exists():
        sys.exit(f'No credentials file at {CREDENTIALS}. Create it with lines\n'
                 '    TSD_SERVER=...\n    TSD_PORT=1433\n    TSD_DATABASE=42295\n'
                 '    TSD_USER=...\n    TSD_PASSWORD=...\nand chmod 600 it.')
    cfg = {}
    for line in CREDENTIALS.read_text().splitlines():
        if '=' in line and not line.lstrip().startswith('#'):
            k, v = line.split('=', 1)
            cfg[k.strip()] = v.strip()
    missing = [k for k in ('TSD_SERVER', 'TSD_DATABASE', 'TSD_USER', 'TSD_PASSWORD') if not cfg.get(k)]
    if missing:
        sys.exit(f'{CREDENTIALS} is missing {missing}.')
    return cfg


def main():
    cfg = read_credentials()
    conn = pymssql.connect(server=cfg['TSD_SERVER'], port=int(cfg.get('TSD_PORT') or 1433),
                           user=cfg['TSD_USER'], password=cfg['TSD_PASSWORD'],
                           database=cfg['TSD_DATABASE'], tds_version='7.4',
                           encryption='require', login_timeout=30)
    with conn:
        cur = conn.cursor()
        cur.execute(SQL, (SINCE,))
        rows = cur.fetchall()
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
