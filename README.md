# Drivo Complaint Trends

A self-contained dashboard of customer complaints from the CS DATABASE Google Sheet,
broken down weekly and monthly by complaint type.

## Viewing the dashboard

Open **`dashboard.html`** in any browser — no server or internet connection needed.
It shows the data as of the date in the header ("Data through …").

When the page is served from a web address (e.g. GitHub Pages), it goes further:
on every load it fetches the latest published sheet directly and recomputes all
numbers in the browser — the header then says "live from the sheet". Opened as a
local file it shows the last saved snapshot instead (Google blocks data requests
from local files). If the live fetch fails for any reason, the page falls back
to the saved snapshot and says so in the header.

## Refreshing the data

Run **`refresh_dashboard.py`** (requires Python 3, no extra packages):

```
./refresh_dashboard.py
```

It downloads the latest published sheet, rebuilds `dashboard.html`, and opens it.
Commit and push the updated `dashboard.html` to share the refreshed numbers.

## What the dashboard shows

- **Filters** — year, month, and source (Overall / Drivo Survey / Other sources);
  every chart and table follows them.
- **MTD tile** — current month-to-date count with a comparison to the same days of
  the previous month.
- **Weekly breakdown** — complaints in the day buckets 1–7, 8–14, 15–21, 22–31 of
  the selected month.
- **Top complaint types** — the 8 highest-count types for the selected month.
- **Monthly breakdown** — every month of the selected year.
- **Complaint types table** — all 20 types with per-week counts and fixed
  Drivo / Other / Overall columns.

## Counting rules

- Rows flagged `Duplicate? = Yes` in the sheet are excluded everywhere; a blank
  flag counts as not-a-duplicate.
- A record marked with several complaint types counts once under each type;
  records with no complaint type marked (e.g. positive reviews) are not counted.
- Source split is case-insensitive: any source containing "drivo" counts as
  Drivo Survey; everything else is Other.
- Complaint types are grouped into **controllable** (Fleet Failure, Long Shuttle,
  Long Wait, Rude Service, Shuttle Driver, Unexpected Fees, Unhelpful Service,
  Upsell Complaints, Vehicle Cleanliness, Vehicle Condition) and
  **non-controllable** (Call Center, Credit Check, Damage Claims, Deposit Hold,
  Geozone, Insurance Verification, Location Complaint, No Information,
  Other Complaints, Tolls/Violations).
- Sheet column mapping: "Fleet Failure" = the sheet's "Reserved Vehicle
  Unavailable" column; "Shuttle Driver" = "Shuttle Service".

## Files

| File | Purpose |
|---|---|
| `dashboard.html` | The dashboard — open it in a browser |
| `index.html` | Identical copy of `dashboard.html`, the filename GitHub Pages serves at the root URL |
| `refresh_dashboard.py` | Rebuilds `dashboard.html` and `index.html` from the live sheet |
| `dashboard_template.html` | Page design without data; the script fills it in — edit this to change the dashboard, then rerun the script |
