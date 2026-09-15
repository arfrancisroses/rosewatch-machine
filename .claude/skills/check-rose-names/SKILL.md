---
name: check-rose-names
description: Check a list of rose/variety names against the Rose Watch Master Trademark Filing Chart (data/trademarks.json) and report, for each name, whether it's in the chart and what its trademark status is. Use this whenever the user gives a list of rose names (from a seller's website, a Facebook/Instagram/Etsy page, a catalog, or anywhere else) and asks whether they're trademarked, protected, in the trademark list, or "in my list" -- even if they don't say the word "skill" or name this skill directly. This is a read-only lookup against the existing chart; it does not crawl any website, does not create or modify any Rose Watch case, and does not add anything to the known-sites roster.
---

# Check Rose Names Against the Trademark Chart

A rose reseller's page (Facebook, Etsy, a website, a printed catalog -- anywhere)
often lists variety names with no context on whether they're protected. This
skill answers exactly one question, for a batch of names at once: **is each
name in the Master Trademark Filing Chart, and if so, what's its status?**

This is pure lookup against `data/trademarks.json` -- the same file every other
Rose Watch script reads from. It does not crawl a website, capture evidence, or
create a case. If the names turn out to belong to a seller worth tracking, that's
a separate, deliberate step (adding the seller to `data/known_sites.json` via the
source spreadsheet, per `CLAUDE.md`) -- don't do that automatically just because
a name matched here.

## Why a script instead of eyeballing the JSON

`data/trademarks.json` has 275+ records, and trademark names are messy in ways
that break naive string comparisons: accented characters, apostrophes typed as
`'` vs `’`, extra whitespace, mixed case. `scripts/check_names.py` normalizes
all of that the same way the rest of the Rose Watch pipeline does (see
`scripts/import_sources.py` and `scripts/generate_dashboard_html.py` for the
same normalization pattern elsewhere in this repo), so a name typed slightly
differently than the source spreadsheet still matches correctly.

## How to run it

```bash
python3 .claude/skills/check-rose-names/scripts/check_names.py "Name One" "Name Two" "Name Three"
```

Also accepts a file (one name per line) or stdin:

```bash
python3 .claude/skills/check-rose-names/scripts/check_names.py --file names.txt
echo -e "Name One\nName Two" | python3 .claude/skills/check-rose-names/scripts/check_names.py -
```

It prints a ready-to-paste markdown table. Add `--json` if you need the raw
structured data instead (e.g. to feed into something else programmatically).

**If `data/trademarks.json` is missing or looks stale** (the user mentions a
newer trademark chart was supplied), run `python3 scripts/import_sources.py`
first, per `CLAUDE.md`'s "Ingesting a new/updated source file" convention --
this script always reads whatever is currently in `data/trademarks.json`, it
never fetches or refreshes anything on its own.

## What the columns mean

- **In Chart?** — Yes/No. A "No" is not a legal conclusion, just an honest "this
  name doesn't appear in the current Master Trademark Filing Chart" -- the chart
  itself could be incomplete, or the name could belong to a variety Francis Roses
  hasn't filed on at all.
- **Status** — the trademark status exactly as written in the source spreadsheet
  (Registered, Pending, To Be Filed, etc.). If the source spreadsheet has a blank
  status for that record, this says so explicitly rather than guessing -- per
  `CLAUDE.md`'s "never silently correct uncertain records" rule, a blank status
  is itself a finding worth surfacing, not something to paper over.
- **Near-misses** — when a name isn't an exact match, the script separately checks
  whether it's a whole-word substring of a real trademark name (or vice versa) and
  flags it, clearly labeled as *not* a real match. This catches genuine typos
  ("Withby Abbey" vs "Whitby Abbey") without falsely flagging unrelated names that
  merely share letters (e.g. "Juliet" is correctly NOT flagged against "Garden
  Julietta Cream" -- "Juliet" isn't a whole word inside "Julietta").

## Presenting the results

Paste the script's markdown table directly, then add a short plain-language
summary underneath -- how many names matched, and for each match, what its
status means in practice (e.g. "Registered marks are enforceable now; Pending
marks aren't yet"). Follow the same tone as the rest of Rose Watch: a match is
a potential lead, not an accusation, and an unclear/blank status in the source
chart is flagged for the user's attention rather than assumed one way or the
other.

If every name comes back "No", say so plainly rather than padding the answer --
that's a complete and useful result on its own.
