# Rose Watch Machine

Intellectual-property monitoring and evidence-management system for Francis Roses.
Rose Watch tracks known rose-reseller websites for potential unauthorized sales of
trademarked rose varieties, and maintains an evidence-based case dashboard and daily
PDF report.

**Full operating instructions live in [`CLAUDE.md`](CLAUDE.md).** That file is the
standing system prompt every Rose Watch run follows, plus a map of where each part
of the spec lives in this repo.

## Layout

```
CLAUDE.md              Rose Watch operating instructions (read this first)
data/
  sources/              Authoritative source spreadsheets, one dated copy per ingestion
  trademarks.json/.csv   Parsed trademark chart (regenerate: scripts/import_sources.py)
  known_sites.json/.csv  Parsed reseller-site roster (regenerate: scripts/import_sources.py)
cases/
  cases.json             Case index, review queue, and website-code registry
  <CASE-NUMBER>/          One folder per case: case.json + screenshots/
dashboard/
  OVERVIEW.md, TRADEMARKS.md, CASES.md, KNOWN_SITES.md,
  NEEDS_REVIEW.md, DATA_SOURCES.md
  (all but DATA_SOURCES.md regenerate: scripts/generate_dashboard.py)
reports/
  Rose Watch Daily Report - YYYY-MM-DD.pdf   One per scheduled run
scripts/
  import_sources.py      Parses data/sources/*.xlsx into data/*.json/.csv
  generate_dashboard.py  Rebuilds dashboard/*.md from data/ and cases/cases.json
```

## Status

Initial setup: 2026-09-10. Trademark chart and known-site roster imported; dashboard
scaffolded. No monitoring run has been completed yet, so `cases/cases.json` is empty
and no daily PDF report has been generated. No recurring schedule has been configured.
