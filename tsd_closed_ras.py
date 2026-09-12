"""Shared TSD access for the closed-R/A tools: credentials, connection, and the
one query both export_closed_ras.py and serve_dashboard.py run.

Needs the pymssql driver and ~/.config/tsd/credentials (outside the repo) with
TSD_SERVER, TSD_PORT, TSD_DATABASE, TSD_USER and TSD_PASSWORD lines. TSD_DATABASE
is the TSD customer database (42295) on the Azure SQL server, not DrivoDatabase,
which is empty.
"""
import sys
from pathlib import Path

try:
    import pymssql
except ImportError:
    sys.exit('The pymssql driver is not installed for this Python. Run\n'
             '    python3 -m venv ~/.venvs/tsd && ~/.venvs/tsd/bin/pip install pymssql\n'
             'and then run this script with ~/.venvs/tsd/bin/python.')

CREDENTIALS = Path.home() / '.config' / 'tsd' / 'credentials'
DEFAULT_SINCE = '2025-01-01'

# Mirrors query 1 of closed_ras.sql: a closed R/A is a Cra001 contract with
# CLOSED_FLAG = 1 and TYPE C or H (not void, damage, transfer or wait status),
# counted on its check-in date under its check-out branch. Branch codes are kept
# as TSD has them (EWRCON separate); the dashboard adds EWRCON into EWR.
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


def connect(cfg=None):
    cfg = cfg or read_credentials()
    return pymssql.connect(server=cfg['TSD_SERVER'], port=int(cfg.get('TSD_PORT') or 1433),
                           user=cfg['TSD_USER'], password=cfg['TSD_PASSWORD'],
                           database=cfg['TSD_DATABASE'], tds_version='7.4',
                           encryption='require', login_timeout=30)


def fetch_rows(since=DEFAULT_SINCE, cfg=None):
    """[(date 'yyyy-mm-dd', branch code, count), ...] of closed R/As since `since`."""
    with connect(cfg) as conn:
        cur = conn.cursor()
        cur.execute(SQL, (since,))
        return [(str(d), loc, int(n)) for d, loc, n in cur.fetchall()]
