/* Closed R/As per day and branch, straight from TSD — the source for the
   dashboard's Closed R/As tile and complaint-rate chart.

   SHORTCUT: export_closed_ras.py runs query 1 for you and writes closed_ras.csv.

   HOW TO USE (Azure Data Studio, connected to the TSD server)
     0. In the database dropdown at the top of the editor pick **42295** — that is
        the TSD customer database holding Cra001. DrivoDatabase on the same
        server is empty, and master only lists the databases.
     1. Adjust @Since if you need history further back.
     2. Run this file. Query 1 is the export; queries 2 and 3 are checks.
     3. In the results grid of query 1, click "Save as CSV" (the icon at the
        top right of the grid) and save it as  closed_ras.csv  in this folder,
        next to refresh_dashboard.py.
     4. Run ./refresh_dashboard.py. It reads closed_ras.csv, counts EWRCON under
        EWR, and reports how it compares with the old worker snapshot.

   DEFINITIONS (from "TSD RENTAL Database Definitions", table Cra001)
     - One row of Cra001 is one rental agreement (contract). KNUM is its number.
     - Closed        = CLOSED_FLAG = 1   (0 open, -1 awaiting unit, 2 swap)
     - Real rentals  = TYPE IN ('C','H') (C current, H history). This drops
                       V void, D damage, T non-revenue transfer, W wait status.
     - Closed on     = DATE_IN, the date the renter checked the vehicle in.
     - Branch        = LOC_OUT, the branch where the renter checked the vehicle
                       out. Use LOC_IN instead if you count by return branch.
     - Branch codes are exported as they are in TSD (EWR and EWRCON stay
       separate here); refresh_dashboard.py adds EWRCON into EWR.
*/

DECLARE @Since date = '2025-01-01';

/* 1. EXPORT — save this result as closed_ras.csv */
SELECT
    CONVERT(varchar(10), CAST(ra.DATE_IN AS date), 23) AS [date],      -- yyyy-mm-dd
    UPPER(LTRIM(RTRIM(ra.LOC_OUT)))                    AS [location],
    COUNT(*)                                           AS [count]
FROM dbo.Cra001 AS ra
WHERE ra.CLOSED_FLAG = 1
  AND ra.TYPE IN ('C', 'H')
  AND ra.DATE_IN >= @Since
  AND ra.DATE_IN <  DATEADD(day, 1, CAST(GETDATE() AS date))
GROUP BY CAST(ra.DATE_IN AS date), UPPER(LTRIM(RTRIM(ra.LOC_OUT)))
ORDER BY [date], [location];

/* 2. CHECK — every branch code that appears, so EWRCON is visibly there.
      Anything other than JFK, LGA, EWR, EWRCON, BRK, BRKJS is ignored by the
      dashboard; if a new branch shows up here, add it to LOCS in the script. */
SELECT
    UPPER(LTRIM(RTRIM(ra.LOC_OUT))) AS [location],
    MIN(ra.DATE_IN)                 AS first_closed,
    MAX(ra.DATE_IN)                 AS last_closed,
    COUNT(*)                        AS closed_ras
FROM dbo.Cra001 AS ra
WHERE ra.CLOSED_FLAG = 1 AND ra.TYPE IN ('C', 'H') AND ra.DATE_IN >= @Since
GROUP BY UPPER(LTRIM(RTRIM(ra.LOC_OUT)))
ORDER BY closed_ras DESC;

/* 3. CHECK — Newark by month, out-branch vs in-branch, so you can see how much
      EWRCON adds and confirm which branch column matches your old numbers. */
SELECT
    FORMAT(ra.DATE_IN, 'yyyy-MM')                                            AS [month],
    SUM(CASE WHEN UPPER(LTRIM(RTRIM(ra.LOC_OUT))) = 'EWR'    THEN 1 ELSE 0 END) AS out_EWR,
    SUM(CASE WHEN UPPER(LTRIM(RTRIM(ra.LOC_OUT))) = 'EWRCON' THEN 1 ELSE 0 END) AS out_EWRCON,
    SUM(CASE WHEN UPPER(LTRIM(RTRIM(ra.LOC_IN)))  = 'EWR'    THEN 1 ELSE 0 END) AS in_EWR,
    SUM(CASE WHEN UPPER(LTRIM(RTRIM(ra.LOC_IN)))  = 'EWRCON' THEN 1 ELSE 0 END) AS in_EWRCON
FROM dbo.Cra001 AS ra
WHERE ra.CLOSED_FLAG = 1 AND ra.TYPE IN ('C', 'H') AND ra.DATE_IN >= @Since
GROUP BY FORMAT(ra.DATE_IN, 'yyyy-MM')
ORDER BY [month];
