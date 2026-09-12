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
from datetime import date, datetime, timezone
from pathlib import Path

CSV_URL = ('https://docs.google.com/spreadsheets/d/e/'
           '2PACX-1vSnM14ZYjcNke8a-6MrTA_kbDzE4DgwaAjVECGbP_OQj-y6DEBkz5AlYKk7bl_x4WiY4pGJWh7feS7w'
           '/pub?output=csv')
# Closed rentals (R/As). Preferred source: closed_ras.csv, exported from TSD with
# closed_ras.sql in Azure Data Studio (columns date, location, count; branch codes
# as TSD has them, so EWRCON is present). Fallback, and filler for months the
# export does not cover: a snapshot a separate job pushes from TSD to this worker.
# That job drops EWRCON, which is why the export is preferred.
RENTALS_URL = 'https://drivo-dashboard-api.mohamed-57f.workers.dev/api/closedrentals'
HERE = Path(__file__).resolve().parent
TEMPLATE = HERE / 'dashboard_template.html'
EXPORT = HERE / 'closed_ras.csv'
OUT = HERE / 'index.html'  # the filename GitHub Pages serves at the root URL

MONTHS = {m: i + 1 for i, m in enumerate(
    ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'])}

# Locations the closed-rental feed reports, in display order. Complaint records are
# tagged with an index into this list; complaints whose Location is anything else
# are dropped entirely, so every count on the dashboard belongs to one of these.
LOCS = ['JFK', 'LGA', 'EWR', 'BRK', 'BRKJS']
LOC_IDX = {code: i for i, code in enumerate(LOCS)}
# Codes that are the same branch under another name. TSD (and the sheet) now use
# EWRCON for part of Newark; its closed R/As and complaints all count under EWR.
LOC_ALIASES = {'EWRCON': 'EWR'}


def loc_index(code):
    """Index into LOCS for a raw location string, or None if it is not one of ours."""
    code = str(code or '').strip().upper()
    return LOC_IDX.get(LOC_ALIASES.get(code, code))

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


def read_export():
    """Closed R/As per (year, month, loc_idx) from closed_ras.csv, or None if absent.

    The file is the "Save as CSV" of query 1 in closed_ras.sql: one row per day and
    branch with columns date, location, count. Also returns the per-month count of
    EWRCON rows folded into EWR and the codes that were dropped, for the summary.
    """
    if not EXPORT.exists():
        return None
    with EXPORT.open(encoding='utf-8-sig', newline='') as f:
        rows = list(csv.DictReader(f))
    if not rows:
        sys.exit(f'{EXPORT.name} is empty — re-run query 1 of closed_ras.sql and save it again.')
    cols = {c.strip().lower(): c for c in rows[0]}
    missing = [c for c in ('date', 'location', 'count') if c not in cols]
    if missing:
        sys.exit(f'{EXPORT.name} is missing columns {missing}; it needs date, location, count '
                 f'(save the result of query 1 in closed_ras.sql). Found: {list(rows[0])}')
    agg, ewrcon, dropped, bad = Counter(), Counter(), Counter(), 0
    for r in rows:
        code = str(r[cols['location']] or '').strip().upper()
        li = loc_index(code)
        try:
            # Query 1 emits yyyy-mm-dd; a raw datetime export still starts that way.
            dt = str(r[cols['date']]).strip()[:10]
            year, mon = int(dt[:4]), int(dt[5:7])
            n = int(float(r[cols['count']] or 0))
        except Exception:
            bad += 1
            continue
        if li is None:
            dropped[code] += n
            continue
        agg[(year, mon, li)] += n
        if code in LOC_ALIASES:
            ewrcon[(year, mon)] += n
    if bad:
        print(f'{bad:,} rows in {EXPORT.name} had an unreadable date or count and were skipped.')
    return agg, ewrcon, dropped


def fetch_worker():
    """Closed R/As per (year, month, loc_idx) from the worker's cached TSD snapshot.

    Returns (Counter, pushed_at); an empty Counter on any failure so a worker outage
    never blocks a refresh (the ratio section just hides itself if nothing else is
    available).
    """
    try:
        # The worker sits behind Cloudflare, which answers 403 to Python's default
        # User-Agent; any browser-like one is accepted.
        req = urllib.request.Request(RENTALS_URL, headers={'User-Agent': 'Mozilla/5.0 drivo-complaint-trends/refresh'})
        payload = json.loads(urllib.request.urlopen(req, timeout=30).read().decode('utf-8'))
    except Exception as e:
        print(f'Closed-rental worker unavailable ({e}).')
        return Counter(), None

    agg = Counter()
    for row in payload.get('rows') or []:
        li = loc_index(row.get('location'))
        if li is None:
            continue
        try:
            year, mon = (int(x) for x in str(row.get('month') or '').split('-')[:2])
        except Exception:
            continue
        agg[(year, mon, li)] += int(row.get('count') or 0)
    return agg, payload.get('pushedAt')


def month_totals(agg):
    out = Counter()
    for (year, mon, _), n in agg.items():
        out[(year, mon)] += n
    return out


def fetch_rentals():
    """Closed R/As for the dashboard: the TSD export where it has data, the worker
    snapshot for any other month.

    Returns ([[year, month, loc_idx, count], ...], pushed_at, export_months, exported_at).
    export_months lists the [year, month] pairs taken from the export so the page's
    in-browser worker refresh leaves them alone.
    """
    exported = read_export()
    worker, pushed_at = fetch_worker()
    if exported is None:
        print(f'No {EXPORT.name} next to the script — closed R/As come from the worker snapshot only, '
              f'which has no EWRCON rows. Run closed_ras.sql in Azure Data Studio and save query 1 as '
              f'{EXPORT.name} to fix that.')
        return [[*k, v] for k, v in sorted(worker.items())], pushed_at, [], None

    agg, ewrcon, dropped = exported
    export_months = {k[:2] for k in agg}
    merged = Counter(agg)
    for k, v in worker.items():
        if k[:2] not in export_months:
            merged[k] += v

    # Reconcile with the old snapshot month by month so the change is visible.
    ex_tot, wk_tot = month_totals(agg), month_totals(worker)
    print(f'Closed R/As from {EXPORT.name} ({sum(agg.values()):,} across {len(export_months)} months; '
          f'EWRCON counted under EWR: {sum(ewrcon.values()):,}).')
    if dropped:
        print('  Ignored branch codes in the export: '
              + ', '.join(f'{c or "(blank)"} {n:,}' for c, n in dropped.most_common()))
    print(f'  {"month":8} {"export":>8} {"worker":>8} {"diff":>7} {"EWRCON":>7}')
    for ym in sorted(export_months):
        e, w = ex_tot[ym], wk_tot.get(ym)
        w_s, diff = (f'{w:,}', f'{e - w:+,}') if w is not None else ('n/a', 'n/a')
        print(f'  {ym[0]}-{ym[1]:02d}  {e:8,} {w_s:>8} {diff:>7} {ewrcon[ym]:7,}')
    filler = sorted(set(wk_tot) - export_months)
    if filler:
        print('  Months filled from the worker snapshot (not in the export): '
              + ', '.join(f'{y}-{m:02d}' for y, m in filler))
    # Timezone-aware so a browser anywhere shows the save time in its own zone
    # (the GitHub Actions build runs in UTC).
    exported_at = datetime.fromtimestamp(EXPORT.stat().st_mtime, tz=timezone.utc).isoformat(timespec='minutes')
    return ([[*k, v] for k, v in sorted(merged.items())], pushed_at,
            sorted(list(ym) for ym in export_months), exported_at)


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
        # Every logged complaint counts, whatever the Confirmed column says (rule
        # dropped 2026-09-13: an investigation outcome does not remove the complaint).
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
        li = loc_index(r['Location'])
        if li is None:
            offloc += 1
            continue
        for ti, (_, col, _) in enumerate(TYPES):
            if r[col].strip():
                agg[(year, mon, day, src, li, ti)] += 1

    rentals, pushed_at, export_months, exported_at = fetch_rentals()
    data = {
        'asOf': date.today().isoformat(),
        'types': [{'name': n, 'cat': c} for n, _, c in TYPES],
        'records': [[*k, v] for k, v in sorted(agg.items())],
        'locs': LOCS,
        'rentals': rentals,
        'rentalsPushedAt': pushed_at,
        'rentalsExportMonths': export_months,
        'rentalsExportedAt': exported_at,
    }
    html = TEMPLATE.read_text()
    assert '__DATA__' in html, 'dashboard_template.html is missing the __DATA__ placeholder'
    built = html.replace('__DATA__', json.dumps(data, separators=(',', ':')), 1)
    OUT.write_text(built)

    note = f', {skipped} dated rows unparseable and skipped' if skipped else ''
    print(f'Dashboard refreshed: {len(rows):,} sheet rows, '
          f'{sum(agg.values()):,} complaint marks after excluding duplicates{note}.')
    if offloc:
        print(f'{offloc:,} rows excluded: Location not one of {LOCS} (or an alias: {LOC_ALIASES}).')
    if rentals:
        print(f'Closed R/As on the dashboard: {sum(r[3] for r in rentals):,} across {len(LOCS)} locations'
              + (f' (worker snapshot pushed {pushed_at}).' if pushed_at else '.'))
    else:
        print('No closed R/A data from either source — building without the ratio section.')
    open_browser()


if __name__ == '__main__':
    main()
