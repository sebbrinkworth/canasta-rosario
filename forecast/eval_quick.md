# Quick eval (7-day window) — 2026-09-01

- files: 7 (rosario-*.json)
- dates: ['2026-08-26', '2026-08-27', '2026-08-28', '2026-08-29', '2026-08-30', '2026-08-31', '2026-09-01']
- yerba Coto per_unit series: [('2026-08-26', 3370.0, 1685.0), ('2026-08-27', 3370.0, 1685.0), ('2026-08-28', 3370.0, 1685.0), ('2026-08-29', 3370.0, 1685.0), ('2026-08-30', 3370.0, 1685.0), ('2026-08-31', 3370.0, 1685.0), ('2026-09-01', 3370.0, 1685.0)]
- 3-day rolling MAE (yerba Coto): 0.00 over 4 points
- hero cheapest series: [('2026-08-26', 29910.99, 'La Anónima'), ('2026-08-27', 25526.12, 'La Anónima'), ('2026-08-28', 25835.91, 'La Anónima'), ('2026-08-29', 26336.26, 'La Anónima'), ('2026-08-30', 29810.96, 'La Anónima'), ('2026-08-31', 29711.31, 'La Anónima'), ('2026-09-01', 27296.39, 'La Anónima')]

## Notes
- CKAN SEPA only retains 7 days per weekday (one resource per weekday, overwritten daily). Verified via package_show: last_modified 2026-08-26..2026-09-01.
- 90-day backfill via public CKAN endpoint is **not possible** — historical dumps are not archived publicly. ETL correctly fetches latest per weekday; backfill older than 7 days would require private archive or daily capture.
- For TimesFM evaluation: 7 days < 32 context needed for 7-day forecast. Recommend: use this 7-day seed + daily cron to build history going forward, or synthesize/obtain archive from soportesepa@comercio.gob.ar.

## Disk & Verification
- data/rosario-*.json count: 7
- du -sh data/: see below
- No *.zip retained in /tmp (cleaned)
- latest.json -> 2026-09-01, web/index.html regenerated
