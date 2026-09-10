#!/usr/bin/env python3
"""
Rose Watch — dashboard generator.

Regenerates the read-only, data-derived dashboard pages under dashboard/
(OVERVIEW, TRADEMARKS, KNOWN_SITES, NEEDS_REVIEW) from data/trademarks.json,
data/known_sites.json, and cases/cases.json.

CASES.md is derived too, but case data itself (cases/cases.json) is
hand/crawl-maintained and never touched by this script — it only reads it.
Re-run after import_sources.py, and after any crawl run that updates
cases/cases.json.
"""
import json
import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"
DASHBOARD_DIR = REPO_ROOT / "dashboard"
CASES_FILE = REPO_ROOT / "cases" / "cases.json"

PHOENIX = ZoneInfo("America/Phoenix")


def now_phoenix_str():
    return datetime.datetime.now(PHOENIX).strftime("%Y-%m-%d %H:%M %Z")


def load_json(path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def md_escape(s):
    if s is None:
        return ""
    return str(s).replace("|", "\\|").replace("\n", " ")


def write(path, content):
    path.write_text(content, encoding="utf-8")


def generate_trademarks_md(trademarks):
    records = trademarks["records"]
    lines = [
        "# Trademarks",
        "",
        f"Source file: `{trademarks['source_file']}` — imported {trademarks['imported_date']}.",
        f"Total records: {trademarks['record_count']}.",
        "",
        "Fields preserve the original wording from the Master Trademark Filing Chart. "
        "Rows flagged **Needs Review** have missing, unclear, duplicate, or conflicting "
        "source data and must not be silently corrected — see the reason(s) given.",
        "",
    ]

    by_breeder = {}
    for r in records:
        by_breeder.setdefault(r["owner_breeder"] or "(Owner/Breeder not stated — Needs Review)", []).append(r)

    for breeder in sorted(by_breeder.keys()):
        lines.append(f"## {breeder}")
        lines.append("")
        lines.append("| Rose/Variety | Status | Docket No. | App. Ser. No. | Reg. No. | Filing Date | Registration Date | Authorized Seller | Needs Review |")
        lines.append("|---|---|---|---|---|---|---|---|---|")
        for r in sorted(by_breeder[breeder], key=lambda x: (x["trademark"] or "")):
            nr = "Yes — " + "; ".join(r["needs_review_reasons"]) if r["needs_review"] else ""
            lines.append(
                f"| {md_escape(r['trademark']) or '(unnamed)'} | {md_escape(r['status'])} | "
                f"{md_escape(r['docket_no'])} | {md_escape(r['app_ser_no'])} | {md_escape(r['reg_no'])} | "
                f"{md_escape(r['filing_date'])} | {md_escape(r['registration_date'])} | "
                f"{md_escape(r['party_selling'])} | {md_escape(nr)} |"
            )
        lines.append("")
    return "\n".join(lines) + "\n"


def generate_known_sites_md(sites):
    records = sites["records"]
    lines = [
        "# Known Sites",
        "",
        f"Source file: `{sites['source_file']}` — imported {sites['imported_date']}.",
        f"Total known reseller sites: {sites['record_count']}.",
        "",
        "This list is Rose Watch's crawl target roster (SOURCE FILES item 2). The "
        "\"Prior reported varieties\" and \"Prior manual notes\" columns carry over "
        "informal, pre-Rose-Watch research from the source spreadsheet. **They are "
        "background context only** — not verified Rose Watch case evidence (no case "
        "number, product URL, screenshot, quoted text, or evidence date exists for "
        "them). Each site must still be crawled and, if a match is confirmed against "
        "the trademark chart, given a proper case record in `cases/cases.json`.",
        "",
        "| Company | Website(s) | Sales Platform | Shipped From | Prior Reported Varieties (unverified) | Notes |",
        "|---|---|---|---|---|---|",
    ]
    for s in records:
        lines.append(
            f"| {md_escape(s['company'])} | {md_escape('<br>'.join(s['websites']))} | "
            f"{md_escape(', '.join(s['sales_platforms']))} | {md_escape(s['shipped_from'])} | "
            f"{md_escape(', '.join(s['prior_reported_varieties']))} | {md_escape('; '.join(s['prior_manual_notes']))} |"
        )
    lines.append("")
    return "\n".join(lines) + "\n"


def generate_needs_review_md(trademarks, cases):
    tm_nr = [r for r in trademarks["records"] if r["needs_review"]]
    review_queue = cases.get("review_queue", [])
    lines = [
        "# Needs Review",
        "",
        "## Trademark chart records needing review",
        "",
        f"{len(tm_nr)} of {trademarks['record_count']} trademark records have missing, "
        "unclear, duplicate, or conflicting data and were not silently corrected.",
        "",
        "| Rose/Variety | Owner/Breeder | Status (as written) | Source Row | Reason |",
        "|---|---|---|---|---|",
    ]
    for r in tm_nr:
        lines.append(
            f"| {md_escape(r['trademark']) or '(unnamed)'} | {md_escape(r['owner_breeder'])} | "
            f"{md_escape(r['status'])} | {r['source_row']} | {md_escape('; '.join(r['needs_review_reasons']))} |"
        )
    lines.append("")
    lines.append("## Crawl matches held for review (non-Registered/Pending trademarks)")
    lines.append("")
    lines.append(
        "Matches against variety names whose trademark status is To Be Filed, Needs "
        "Review, Abandoned, Do Not File, Not Applicable, or Not in Trademark Chart are "
        "held here rather than published as Cases, and are never characterized as "
        "confirmed infringement."
    )
    lines.append("")
    if not review_queue:
        lines.append("_No crawl-sourced review-queue entries yet — no monitoring run has been completed under this system._")
    else:
        lines.append("| Entry | Rose/Variety | Matched Status | Seller | Website | Product URL | Date Found |")
        lines.append("|---|---|---|---|---|---|---|")
        for e in review_queue:
            lines.append(
                f"| {md_escape(e.get('entry_id'))} | {md_escape(e.get('variety'))} | "
                f"{md_escape(e.get('status'))} | {md_escape(e.get('seller'))} | "
                f"{md_escape(e.get('website'))} | {md_escape(e.get('product_url'))} | "
                f"{md_escape(e.get('first_date_found'))} |"
            )
    lines.append("")
    return "\n".join(lines) + "\n"


def generate_cases_md(cases):
    records = cases.get("cases", [])
    lines = [
        "# Cases",
        "",
        "Active potential-infringement findings that matched a **Registered** or "
        "**Pending** trademark. Every row is a lead for Francis Roses / legal counsel "
        "review, not a legal determination. Full evidence for each case (screenshots, "
        "quoted text, seller location, hosting information, access limitations, notes) "
        "lives in `cases/<CASE-NUMBER>/case.json`.",
        "",
        "Filter by: trademark status, website/seller code, seller location, review status.",
        "",
        "| Case No. | Site Code | Rose/Variety | Matched Trademark | TM Status | Seller | Domain | Seller Location | Website Host | First Found | Last Verified | Match Class. | Review Status |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    if not records:
        lines.append("| _(none yet)_ | | | | | | | | | | | | |")
        lines.append("")
        lines.append("No monitoring run has been completed under this system yet, so no case numbers have been assigned. See `dashboard/DATA_SOURCES.md` for the current data baseline.")
    else:
        for c in records:
            lines.append(
                f"| {md_escape(c.get('case_number'))} | {md_escape(c.get('site_code'))} | "
                f"{md_escape(c.get('variety'))} | {md_escape(c.get('matched_trademark'))} | "
                f"{md_escape(c.get('trademark_status'))} | {md_escape(c.get('seller_name'))} | "
                f"{md_escape(c.get('website_domain'))} | {md_escape(c.get('seller_location'))} | "
                f"{md_escape(c.get('website_host'))} | {md_escape(c.get('first_date_found'))} | "
                f"{md_escape(c.get('last_verified'))} | {md_escape(c.get('match_classification'))} | "
                f"{md_escape(c.get('review_status'))} |"
            )
    lines.append("")
    return "\n".join(lines) + "\n"


def generate_overview_md(trademarks, sites, cases):
    counts = {}
    for r in trademarks["records"]:
        counts[r["status_category"] or "Uncategorized/Needs Review"] = counts.get(r["status_category"] or "Uncategorized/Needs Review", 0) + 1
    lines = [
        "# Rose Watch — Overview",
        "",
        f"Dashboard last regenerated: {now_phoenix_str()}",
        "",
        "## Trademark chart summary",
        "",
        f"- Total trademark records: {trademarks['record_count']} (source: `{trademarks['source_file']}`, imported {trademarks['imported_date']})",
    ]
    for cat, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        lines.append(f"  - {cat}: {n}")
    active = sum(1 for r in trademarks["records"] if r["status_category"] in ("Registered", "Pending"))
    lines.append(f"- Active for crawling (Registered + Pending): **{active}**")
    nr = sum(1 for r in trademarks["records"] if r["needs_review"])
    lines.append(f"- Flagged Needs Review: {nr}")
    lines.append("")
    lines.append("## Known sites")
    lines.append("")
    lines.append(f"- Known reseller sites on roster: {sites['record_count']} (source: `{sites['source_file']}`, imported {sites['imported_date']})")
    lines.append("- Status: not yet crawled under the Rose Watch case-tracking system (see Data Sources for details).")
    lines.append("")
    lines.append("## Cases")
    lines.append("")
    n_cases = len(cases.get("cases", []))
    lines.append(f"- Active cases (matched Registered/Pending trademarks): {n_cases}")
    lines.append(f"- Review-queue entries (matched other statuses): {len(cases.get('review_queue', []))}")
    lines.append(f"- Last monitoring run completed: {cases.get('last_run_completed', '_none yet_')}")
    lines.append("")
    lines.append("## Sections")
    lines.append("")
    lines.append("- [Trademarks](TRADEMARKS.md)")
    lines.append("- [Cases](CASES.md)")
    lines.append("- [Known Sites](KNOWN_SITES.md)")
    lines.append("- [Needs Review](NEEDS_REVIEW.md)")
    lines.append("- [Data Sources](DATA_SOURCES.md)")
    lines.append("")
    return "\n".join(lines) + "\n"


def main():
    trademarks = load_json(DATA_DIR / "trademarks.json", {"records": [], "record_count": 0, "source_file": "(none)", "imported_date": "(none)"})
    sites = load_json(DATA_DIR / "known_sites.json", {"records": [], "record_count": 0, "source_file": "(none)", "imported_date": "(none)"})
    cases = load_json(CASES_FILE, {"cases": [], "review_queue": [], "last_run_completed": None})

    DASHBOARD_DIR.mkdir(exist_ok=True)
    write(DASHBOARD_DIR / "OVERVIEW.md", generate_overview_md(trademarks, sites, cases))
    write(DASHBOARD_DIR / "TRADEMARKS.md", generate_trademarks_md(trademarks))
    write(DASHBOARD_DIR / "KNOWN_SITES.md", generate_known_sites_md(sites))
    write(DASHBOARD_DIR / "NEEDS_REVIEW.md", generate_needs_review_md(trademarks, cases))
    write(DASHBOARD_DIR / "CASES.md", generate_cases_md(cases))
    print("Dashboard regenerated in dashboard/")


if __name__ == "__main__":
    main()
