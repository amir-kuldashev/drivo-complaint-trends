# Drivo Complaint Trends

A self-contained dashboard of customer complaints from the CS DATABASE Google Sheet,
broken down weekly and monthly by complaint type.

## Viewing the dashboard

Open **`index.html`** in any browser — no server or internet connection needed.
It shows the data as of the date in the header ("Data through …").

When the page is served from a web address (e.g. GitHub Pages), it goes further:
on every load it fetches the latest published sheet directly and recomputes all
numbers in the browser — the header then says "live from the sheet". It refreshes
the closed-R/A figures the same way, as a separate request. Opened as a local file
it shows the last saved snapshot instead (Google blocks data requests from local
files). If either live fetch fails, the page falls back to the saved snapshot for
that piece and says so.

## Refreshing the data

Run **`refresh_dashboard.py`** (requires Python 3, no extra packages):

```
./refresh_dashboard.py
```

It downloads the latest published sheet and the closed-R/A snapshot, rebuilds
`index.html`, and opens it. Commit and push the updated `index.html` to share the
refreshed numbers. If the closed-R/A feed is unreachable the refresh
still succeeds — it just builds without the Closed R/As tile and says so.

## What the dashboard shows

- **Filters** — year, month, location, and source (Overall / Drivo Survey / Other
  sources); every tile, chart, and table follows all four.
- **Month total tile** — complaints for the selected month, split by source.
- **Weekly breakdown** — complaints in the day buckets 1–7, 8–14, 15–21, 22–31 of
  the selected month.
- **Top complaint types** — the 8 highest-count types for the selected month, each
  with its share of the month's total; a dropdown expands the remaining 12 so all
  20 types are visible with percentages, on one shared bar scale.
- **Monthly breakdown** — every month of the selected year.
- **Complaint types table** — all 20 types with per-week counts and fixed
  Drivo / Other / Overall columns.
- **Closed R/As tile** — closed rentals for the selected month, with the
  per-location split underneath.
- **Complaint rate by location** — complaints ÷ closed R/As as a percentage, one
  bar per location ranked highest-first, plus a monthly trend table. Both the
  tile and the chart hide themselves when no closed-rental data is available.

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
- Only complaints whose Location is one of JFK, LGA, EWR, BRK, BRKJS (or the
  alias EWRCON, which counts as EWR) are counted.
  Rows with any other Location value are **excluded entirely** — they do not appear
  in any tile, chart, or table, and are not part of "All locations". The refresh
  script prints how many rows it dropped for this reason.

### Closed R/As and the complaint rate

- The rate is **complaint marks ÷ closed R/As**, using the same mark count as
  every other card, so the overall figure reconciles with the month total tile
  (July 2026: 870 ÷ 6,758 = 12.87%). A complaint logged under three types counts
  three times, so this is marks-per-rental rather than the share of rentals that
  drew a complaint, and it could in principle exceed 100%.
- Bars are ranked highest-rate-first, and each is labelled with its own
  complaints / closed R/As counts.
- Closed R/As per month and location come from
  `https://drivo-dashboard-api.mohamed-57f.workers.dev/api/closedrentals`. That
  worker serves a cached snapshot which a **separate** job pushes from TSD —
  nothing in this repo talks to TSD directly.
- Only the five locations the feed reports are shown, under the feed's own codes:
  JFK, LGA, EWR, BRK, BRKJS. The code **EWRCON** is part of Newark: its closed
  R/As (and any complaints tagged with it) are counted under EWR, in both the
  refresh script and the in-browser live refresh.
- The tile is a rental count, so the source filter does not apply to it. On the
  chart the filter narrows the **complaints only** — the denominator is always
  every closed R/A — so filtering to one source gives that channel's rate.
- A month whose closed-R/A total is under half the median month is still being
  filled in by the TSD push. The tile says so, and the chart **withholds the
  rate entirely** rather than publishing a figure inflated several-fold.

## Files

| File | Purpose |
|---|---|
| `index.html` | The dashboard — open it in a browser; also the filename GitHub Pages serves at the root URL |
| `refresh_dashboard.py` | Rebuilds `index.html` from the live sheet |
| `dashboard_template.html` | Page design without data; the script fills it in — edit this to change the dashboard, then rerun the script |
