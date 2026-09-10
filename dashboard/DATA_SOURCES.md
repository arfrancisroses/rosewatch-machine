# Data Sources

Append-only log of source files ingested into Rose Watch. Never overwrite a prior
entry — each new source file gets its own dated row, and `data/trademarks.json` /
`data/known_sites.json` always reflect the most recent successful import.

## Trademark chart

| Date Ingested | Source File | Records | Notes |
|---|---|---|---|
| 2026-09-10 | `data/sources/2026-09-10_MasterTrademarkFilingChart.xlsx` | 275 | Initial Rose Watch setup import. 86 records flagged Needs Review (missing/unclear status, missing owner/breeder, Registered status without a registration number, or duplicate trademark name) — see [Needs Review](NEEDS_REVIEW.md). |

## Known reseller website list

| Date Ingested | Source File | Records | Notes |
|---|---|---|---|
| 2026-09-10 | `data/sources/2026-09-10_ListofIPInfringements.xlsx` | 14 (from `Sheet1` + `Etsy` tabs, deduplicated by company) | Initial Rose Watch setup import. This file predates the Rose Watch case-tracking system: it carries informal per-variety flags and notes from prior manual research, not formal case records (no product URLs, evidence dates, screenshots, or review statuses exist for these). Imported as the known-site crawl roster only — see [Known Sites](KNOWN_SITES.md). The `For Exec Summary` tab was not imported as a separate roster; it is a subset/summary view of `Sheet1` and would only introduce duplicate company rows. |

## Known limitations as of 2026-09-10 setup

- No monitoring run has been completed yet under this system, so `cases/cases.json` starts empty. The per-variety flags in the known-sites import are **not** Rose Watch cases and must not be read as confirmed findings — each known site still needs to be crawled to produce a proper case record.
- The Master Trademark Filing Chart has 82 records with no status value at all and several with unrecognized/typo'd status text (e.g. "Resgistered"). These are held as Needs Review rather than guessed at — see [Needs Review](NEEDS_REVIEW.md) for the full list and reasons.
- Website hosting-lookup and seller-location research have not been run yet (they happen per-case during a monitoring run, not during source import).
