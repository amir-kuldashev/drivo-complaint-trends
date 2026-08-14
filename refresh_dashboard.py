#!/usr/bin/env python3
"""Refresh the Drivo complaint dashboard from the published Google Sheet, then open it.

Run this instead of opening index.html directly whenever you want fresh numbers:

    ./refresh_dashboard.py

It downloads the CS DATABASE sheet, rebuilds index.html next to this script, and
opens it in your default browser. If the download fails (offline, sheet moved),
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
# Closed rentals (R/As) pulled from TSD by a separate job and cached on this worker.
# We only read its last-pushed snapshot; nothing here talks to TSD directly.
RENTALS_URL = 'https://drivo-dashboard-api.mohamed-57f.workers.dev/api/closedrentals'
HERE = Path(__file__).resolve().parent
TEMPLATE = HERE / 'dashboard_template.html'
OUT = HERE / 'index.html'  # the filename GitHub Pages serves at the root URL

MONTHS = {m: i + 1 for i, m in enumerate(
    ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'])}

# Locations the closed-rental feed reports, in display order. Complaint records are
# tagged with an index into this list; complaints whose Location is anything else
# are dropped entirely, so every count on the dashboard belongs to one of these.
LOCS = ['JFK', 'LGA', 'EWR', 'BRK', 'BRKJS']
LOC_IDX = {code: i for i, code in enumerate(LOCS)}

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


def fetch_rentals():
    """Closed R/As per (year, month, location) from the cached TSD snapshot.

    Returns ([[year, month, loc_idx, count], ...], pushed_at). On any failure the
    ratio section simply hides itself, so a worker outage never blocks a refresh.
    """
    try:
        payload = json.loads(urllib.request.urlopen(RENTALS_URL, timeout=30).read().decode('utf-8'))
    except Exception as e:
        print(f'Closed-rental feed unavailable ({e}) — building without the ratio section.')
        return [], None

    agg = Counter()
    for row in payload.get('rows') or []:
        loc = str(row.get('location') or '').strip().upper()
        if loc not in LOC_IDX:
            continue
        try:
            year, mon = (int(x) for x in str(row.get('month') or '').split('-')[:2])
        except Exception:
            continue
        agg[(year, mon, LOC_IDX[loc])] += int(row.get('count') or 0)
    return [[*k, v] for k, v in sorted(agg.items())], payload.get('pushedAt')


def main():
    try:
        raw = urllib.request.urlopen(CSV_URL, timeout=60).read().decode('utf-8')
    except Exception as e:
        print(f'Could not download the sheet ({e}).')
        print('Opening the last saved dashboard instead.')
        open_browser()
        sys.exit(1)

    rows = list(csv.DictReader(io.StringIO(raw)))
    missing = [c for c in ['Date of Complaint', 'YEAR ', 'Source', 'Duplicate?', 'Location']
               + [t[1] for t in TYPES] if rows and c not in rows[0]]
    if missing:
        print(f'The sheet layout changed — missing columns: {missing}')
        print('Opening the last saved dashboard instead.')
        open_browser()
        sys.exit(1)

    agg = Counter()
    skipped = 0
    offloc = 0
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
        loc = r['Location'].strip().upper()
        if loc not in LOC_IDX:
            offloc += 1
            continue
        li = LOC_IDX[loc]
        for ti, (_, col, _) in enumerate(TYPES):
            if r[col].strip():
                agg[(year, mon, day, src, li, ti)] += 1

    rentals, pushed_at = fetch_rentals()
    data = {
        'asOf': date.today().isoformat(),
        'types': [{'name': n, 'cat': c} for n, _, c in TYPES],
        'records': [[*k, v] for k, v in sorted(agg.items())],
        'locs': LOCS,
        'rentals': rentals,
        'rentalsPushedAt': pushed_at,
    }
    html = TEMPLATE.read_text()
    assert '__DATA__' in html, 'dashboard_template.html is missing the __DATA__ placeholder'
    built = html.replace('__DATA__', json.dumps(data, separators=(',', ':')), 1)
    OUT.write_text(built)

    note = f', {skipped} dated rows unparseable and skipped' if skipped else ''
    print(f'Dashboard refreshed: {len(rows):,} sheet rows, '
          f'{sum(agg.values()):,} complaint marks after excluding duplicates{note}.')
    if offloc:
        print(f'{offloc:,} rows excluded: Location not one of {LOCS}.')
    if rentals:
        print(f'Closed R/As: {sum(r[3] for r in rentals):,} across {len(LOCS)} locations '
              f'(pushed {pushed_at}).')
    open_browser()


if __name__ == '__main__':
    main()
