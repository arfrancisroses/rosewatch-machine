# Changelog

## 2026-09-10 — Initial setup

- Added `CLAUDE.md` with the full Rose Watch operating specification, plus a
  repository map and working conventions translating it into this repo's files.
- Imported the Master Trademark Filing Chart (`data/sources/2026-09-10_MasterTrademarkFilingChart.xlsx`,
  275 records) into `data/trademarks.json` / `.csv`. 86 records flagged Needs Review.
- Imported the known reseller website list (`data/sources/2026-09-10_ListofIPInfringements.xlsx`,
  14 sites) into `data/known_sites.json` / `.csv`. Prior per-variety flags and notes
  carried over as unverified background context, not as case records.
- Scaffolded the dashboard (`dashboard/OVERVIEW.md`, `TRADEMARKS.md`, `CASES.md`,
  `KNOWN_SITES.md`, `NEEDS_REVIEW.md`, `DATA_SOURCES.md`) and an empty case database
  (`cases/cases.json`).
- Added `scripts/import_sources.py` and `scripts/generate_dashboard.py` to keep the
  data and dashboard reproducible from the source spreadsheets.
- No monitoring run, PDF report, or recurring schedule yet — none were requested.
