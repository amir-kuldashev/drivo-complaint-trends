#!/usr/bin/env python3
"""Refresh the Drivo complaint dashboard from the published Google Sheet, then open it.

Run this instead of opening dashboard.html directly whenever you want fresh numbers:

    ./refresh_dashboard.py

It downloads the CS DATABASE sheet, rebuilds dashboard.html next to this script,
and opens it in your default browser. If the download fails (offline, sheet moved),
it opens the last saved dashboard instead.
"""
import csv
import io
import json
import sys
import urllib.request
import webbrowser
from collections import Counter
from datetime import date
from pathlib import Path

CSV_URL = ('https://docs.google.com/spreadsheets/d/e/'
           '2PACX-1vSnM14ZYjcNke8a-6MrTA_kbDzE4DgwaAjVECGbP_OQj-y6DEBkz5AlYKk7bl_x4WiY4pGJWh7feS7w'
           '/pub?output=csv')
HERE = Path(__file__).resolve().parent
TEMPLATE = HERE / 'dashboard_template.html'
OUT = HERE / 'dashboard.html'
INDEX = HERE / 'index.html'  # same page; the name GitHub Pages serves at the root URL

MONTHS = {m: i + 1 for i, m in enumerate(
    ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'])}

# (display name, sheet column, category) — C = controllable, N = non-controllable.
# Order must stay in sync with what the dashboard template expects.
TYPES = [
    ('Fleet Failure',          'Reserved Vehicle Unavailable', 'C'),
    ('Long Shuttle',           'Long shuttle',                 'C'),
    ('Long Wait',              'Long wait',                    'C'),
    ('Rude Service',           'Rude service',                 'C'),
    ('Shuttle Driver',         'Shuttle Service',              'C'),
    ('Unexpected Fees',        'Unexpected Fees',              'C'),
    ('Unhelpful Service',      'Unhelpful Service',            'C'),
    ('Upsell Complaints',      'Upsell complaints',            'C'),
    ('Vehicle Cleanliness',    'Vehicle Cleanlines',           'C'),
    ('Vehicle Condition',      'Vehicle Conditions',           'C'),
    ('Call Center',            'Call Center Complaints',       'N'),
    ('Credit Check',           'Credit Check',                 'N'),
    ('Damage Claims',          'Damage Claims',                'N'),
    ('Deposit Hold',           'Deposit Hold',                 'N'),
    ('Geozone',                'Geozone',                      'N'),
    ('Insurance Verification', 'Insurance Verification',       'N'),
    ('Location Complaint',     'Location Complaint',           'N'),
    ('No Information',         'No Information',               'N'),
    ('Other Complaints',       'Other Complaints',             'N'),
    ('Tolls/Violations',       'Tolls and Violations',         'N'),
]


def open_browser():
    if OUT.exists():
        webbrowser.open(OUT.as_uri())


def main():
    try:
        raw = urllib.request.urlopen(CSV_URL, timeout=60).read().decode('utf-8')
    except Exception as e:
        print(f'Could not download the sheet ({e}).')
        print('Opening the last saved dashboard instead.')
        open_browser()
        sys.exit(1)

    rows = list(csv.DictReader(io.StringIO(raw)))
    missing = [c for c in ['Date of Complaint', 'YEAR ', 'Source', 'Duplicate?']
               + [t[1] for t in TYPES] if rows and c not in rows[0]]
    if missing:
        print(f'The sheet layout changed — missing columns: {missing}')
        print('Opening the last saved dashboard instead.')
        open_browser()
        sys.exit(1)

    agg = Counter()
    skipped = 0
    for r in rows:
        if r['Duplicate?'].strip().lower() == 'yes':
            continue
        dt = r['Date of Complaint'].strip()
        if not dt:
            continue  # empty filler rows at the bottom of the sheet
        try:
            day_s, mon_s = dt.split('-')
            day = int(day_s)
            mon = MONTHS[mon_s[:3].title()]
            year = int(r['YEAR '].strip())
        except Exception:
            skipped += 1
            continue
        src = 0 if 'drivo' in r['Source'].lower() else 1
        for ti, (_, col, _) in enumerate(TYPES):
            if r[col].strip():
                agg[(year, mon, day, src, ti)] += 1

    data = {
        'asOf': date.today().isoformat(),
        'types': [{'name': n, 'cat': c} for n, _, c in TYPES],
        'records': [[*k, v] for k, v in sorted(agg.items())],
    }
    html = TEMPLATE.read_text()
    assert '__DATA__' in html, 'dashboard_template.html is missing the __DATA__ placeholder'
    built = html.replace('__DATA__', json.dumps(data, separators=(',', ':')), 1)
    OUT.write_text(built)
    INDEX.write_text(built)

    note = f', {skipped} dated rows unparseable and skipped' if skipped else ''
    print(f'Dashboard refreshed: {len(rows):,} sheet rows, '
          f'{sum(agg.values()):,} complaint marks after excluding duplicates{note}.')
    open_browser()


if __name__ == '__main__':
    main()
