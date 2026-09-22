#!/usr/bin/env python3
"""
Rose Watch -- Daily PDF Report generator.

Reads cases/runs/YYYY-MM-DD.json (the day's monitoring-run log) plus
cases/cases.json and data/known_sites.json, and renders
"reports/Rose Watch Daily Report - YYYY-MM-DD.pdf" per CLAUDE.md's
DAILY PDF REPORT section.

Usage: python3 scripts/generate_daily_report.py [YYYY-MM-DD]
       (defaults to today in America/Phoenix)
"""
import json
import re
import sys
import datetime
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo

from reportlab import rl_config

# Binary Flate streams instead of ASCII85-over-Flate: ~9% smaller file, which
# matters because the report is emailed as an inline base64 attachment.
rl_config.useA85 = 0

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, HRFlowable, KeepTogether
)
from reportlab.lib.enums import TA_LEFT

REPO_ROOT = Path(__file__).resolve().parents[1]
CASES_FILE = REPO_ROOT / "cases" / "cases.json"
RUNS_DIR = REPO_ROOT / "cases" / "runs"
REPORTS_DIR = REPO_ROOT / "reports"
PHOENIX = ZoneInfo("America/Phoenix")

INK = colors.HexColor("#1a2420")
ACCENT = colors.HexColor("#7c2b45")
SOFT = colors.HexColor("#4d5a4f")
LINE = colors.HexColor("#c9d1c3")
WARN = colors.HexColor("#a5690f")
OK = colors.HexColor("#2f6844")
BAD = colors.HexColor("#a3352a")
HEADER_BG = colors.HexColor("#eef1ea")


def load_json(path, default=None):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def safe_url(url):
    """Percent-encode non-ASCII characters for display/hyperlink use in the PDF.
    ReportLab's base Helvetica font has no CJK glyphs, so a literal URL containing
    e.g. Chinese characters renders as black boxes; the percent-encoded form is
    still the identical, valid, clickable URL."""
    if not url:
        return url
    return quote(url, safe="/:?&=%.-_~#@!$'()*+,;")


def build_styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle("RWTitle", parent=styles["Title"], fontName="Helvetica-Bold",
                               fontSize=22, textColor=INK, spaceAfter=2))
    styles.add(ParagraphStyle("RWSubtitle", parent=styles["Normal"], fontName="Helvetica",
                               fontSize=11, textColor=SOFT, spaceAfter=14))
    styles.add(ParagraphStyle("RWAsOf", parent=styles["Normal"], fontName="Helvetica-Bold",
                               fontSize=11, textColor=ACCENT, spaceAfter=16,
                               borderPadding=8, backColor=HEADER_BG))
    styles.add(ParagraphStyle("RWH2", parent=styles["Heading2"], fontName="Helvetica-Bold",
                               fontSize=14, textColor=INK, spaceBefore=16, spaceAfter=8))
    styles.add(ParagraphStyle("RWBody", parent=styles["Normal"], fontName="Helvetica",
                               fontSize=9.5, textColor=INK, leading=13.5))
    styles.add(ParagraphStyle("RWBodySmall", parent=styles["Normal"], fontName="Helvetica",
                               fontSize=8.5, textColor=SOFT, leading=12))
    styles.add(ParagraphStyle("RWCell", parent=styles["Normal"], fontName="Helvetica",
                               fontSize=8, textColor=INK, leading=10.5))
    styles.add(ParagraphStyle("RWCellHead", parent=styles["Normal"], fontName="Helvetica-Bold",
                               fontSize=8, textColor=colors.white, leading=10))
    styles.add(ParagraphStyle("RWNote", parent=styles["Normal"], fontName="Helvetica-Oblique",
                               fontSize=9, textColor=SOFT, leading=13, spaceBefore=4))
    return styles


def stat_table(pairs, styles):
    rows = [[Paragraph(f"<b>{v}</b>", ParagraphStyle("v", parent=styles["RWBody"], fontSize=16, textColor=ACCENT)),
             Paragraph(label, styles["RWBodySmall"])] for label, v in pairs]
    t = Table([[rows[i][0] for i in range(len(rows))], [rows[i][1] for i in range(len(rows))]],
               colWidths=[ (6.5*inch)/len(pairs) ] * len(pairs))
    t.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, 0), 6),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 2),
        ("BOTTOMPADDING", (0, 1), (-1, 1), 10),
        ("LINEBELOW", (0, 1), (-1, 1), 0.5, LINE),
    ]))
    return t


def xml_escape(s):
    return (str(s) if s is not None else "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def link_cell(url, text="View listing"):
    if not url:
        return ""
    href = safe_url(url).replace("&", "&amp;")
    return f'<link href="{href}"><u>{xml_escape(text)}</u></link>'


def wrapped_table(header, rows, col_widths, styles, header_bg=INK, raw_html_cols=None):
    """raw_html_cols: set of column indices whose values are pre-built markup (e.g. from
    link_cell) and must NOT be XML-escaped, unlike plain text cells."""
    raw_html_cols = raw_html_cols or set()
    data = [[Paragraph(h, styles["RWCellHead"]) for h in header]]
    for r in rows:
        row_cells = []
        for i, c in enumerate(r):
            text = c if (i in raw_html_cols and c) else xml_escape(c)
            row_cells.append(Paragraph(text, styles["RWCell"]))
        data.append(row_cells)
    t = Table(data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), header_bg),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.4, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, HEADER_BG]),
    ]))
    return t


def build_coverage(crawl, run):
    """Derive the coverage picture from the crawler's own output.

    Whether a site was reached, and how many product pages it served, both come
    from the same record the crawler wrote -- so a site it could not reach cannot
    be reported as checked with a page count beside it. The hand-written run log
    contributes only the prose note for each site, never its status.
    """
    notes = {}
    for s in run.get("sites", []):
        notes[s.get("company", "")] = s.get("notes")

    def note_for(label):
        if label in notes:
            return notes[label]
        company = label.split(" (")[0]
        for name, note in notes.items():
            if name.split(" (")[0] == company:
                return note
        return None

    rows, limitations = [], []
    accessible = 0
    for label, s in crawl.get("sites", {}).items():
        reached = s.get("error") is None
        accessible += 1 if reached else 0
        # Show the host that actually served the catalog; for anything unreachable
        # keep the roster URL so the reader can see which page went unchecked.
        url = s.get("url_used") or s.get("url_attempted") or "--"
        rows.append([label, url, s.get("platform") or "--",
                     f'{s.get("count", 0):,}', "Accessible" if reached else "Not accessible"])
        if not reached:
            limitations.append([label, url, note_for(label) or s.get("error") or "Not accessible."])

    return {
        "rows": rows,
        "limitations": limitations,
        "urls_total": len(rows),
        "urls_accessible": accessible,
        "urls_inaccessible": len(rows) - accessible,
        "pages_reviewed": crawl.get("total_product_pages_reviewed", 0),
        "new_matches": len(crawl.get("new_matches", [])),
    }


def generate(run_date_str):
    run_date = datetime.date.fromisoformat(run_date_str)
    run = load_json(RUNS_DIR / f"{run_date_str}.json")
    cases_db = load_json(CASES_FILE, {"cases": [], "review_queue": []})
    known_sites = load_json(REPO_ROOT / "data" / "known_sites.json", {"records": []})
    crawl = load_json(RUNS_DIR / f"crawl-{run_date_str}.json")

    if run is None:
        print(f"No run log found at cases/runs/{run_date_str}.json", file=sys.stderr)
        return 1
    if crawl is None:
        # Coverage (which sites were reached, and how many pages) is reported from
        # the crawler's own output so a site it could not reach cannot be written up
        # as checked. Without it there is nothing to attest to, so refuse rather than
        # fall back to hand-entered numbers.
        print(f"No crawl output at cases/runs/crawl-{run_date_str}.json -- "
              f"run scripts/crawl_sites.py first.", file=sys.stderr)
        return 1

    coverage = build_coverage(crawl, run)

    generated_at = datetime.datetime.now(PHOENIX).strftime("%Y-%m-%d %H:%M %Z")
    as_of = run.get("generated_at", generated_at)

    all_cases = cases_db.get("cases", [])
    # Cases first found on this run date (by First Date Found prefix match)
    new_cases = [c for c in all_cases if str(c.get("first_date_found", "")).startswith(run_date_str)]
    new_registered = [c for c in new_cases if c.get("trademark_status") == "Registered"]
    new_pending = [c for c in new_cases if c.get("trademark_status") == "Pending"]
    # Per user instruction: the PDF itemizes Registered-trademark matches only -- those are the
    # only marks currently enforceable/actionable. Pending matches still count in the summary
    # stats above and remain fully tracked in the dashboard and case database either way.
    reportable_cases = new_registered

    styles = build_styles()
    out_path = REPORTS_DIR / f"Rose Watch Daily Report - {run_date_str}.pdf"
    REPORTS_DIR.mkdir(exist_ok=True)

    doc = SimpleDocTemplate(
        str(out_path), pagesize=letter,
        leftMargin=0.65 * inch, rightMargin=0.65 * inch,
        topMargin=0.6 * inch, bottomMargin=0.6 * inch,
        title=f"Rose Watch Daily Report - {run_date_str}",
    )

    story = []

    # ---- Header ----
    story.append(Paragraph("Rose Watch Daily Report", styles["RWTitle"]))
    story.append(Paragraph(f"Francis Roses &middot; IP monitoring &amp; evidence-management system", styles["RWSubtitle"]))
    story.append(Paragraph(f"As of: {as_of} &mdash; evidence and findings below reflect the state of each site at the time it was checked.", styles["RWAsOf"]))
    story.append(Paragraph(f"Report generated: {generated_at}", styles["RWBodySmall"]))
    story.append(HRFlowable(width="100%", thickness=0.75, color=LINE, spaceBefore=10, spaceAfter=6))

    # ---- Monitoring run summary ----
    story.append(Paragraph("Monitoring Run Summary", styles["RWH2"]))
    held = run.get("matches_held_pending_case_creation", 0)
    created = run.get("cases_created_this_run", len(new_cases))
    reverified = run.get("cases_reverified_this_run", 0)
    if created:
        disposition = (
            f"{created} match{'es' if created != 1 else ''} were carried through into full, evidence-complete case "
            f"records this run"
            + (f"; {held} additional matched listing{'s' if held != 1 else ''} remain held pending a decision on "
               f"how to process them into cases." if held else ".")
        )
    elif held:
        disposition = (
            f"{held} listing{'s' if held != 1 else ''} matched an active trademark name this run, but "
            f"{'none were' if held != 1 else 'it was not'} carried into a case record &mdash; see the note below "
            f"the findings table for why."
        )
    elif created:
        disposition = (f"{created} match{'es' if created != 1 else ''} were carried into case records this run.")
    else:
        disposition = "No new matches against the trademark chart were found this run."
    if reverified:
        disposition += f" {reverified} previously existing case{'s' if reverified != 1 else ''} were re-verified still present in their site's current catalog."

    if not new_cases:
        story.append(Paragraph(
            "<b>No new potential infringement findings were identified during this monitoring run.</b>",
            ParagraphStyle("noFindings", parent=styles["RWBody"], fontName="Helvetica-Bold", textColor=ACCENT)))
        if held:
            story.append(Paragraph(
                f"({held} listing{'s' if held != 1 else ''} did match an active trademark name and "
                f"{'are' if held != 1 else 'is'} held for review &mdash; the reason no case was opened is stated "
                f"with the findings below. Nothing has been discarded.)",
                styles["RWBodySmall"]))
        story.append(Spacer(1, 6))

    roster_companies = len(known_sites.get("records", []))
    story.append(Paragraph(
        f"All {roster_companies} known reseller companies ({coverage['urls_total']} URLs) on the closed crawl roster "
        f"were attempted, of which {coverage['urls_accessible']} served a catalog. Product catalogs were "
        "pulled directly from each accessible site's own product data feed (Shopify's product API or the WordPress "
        "REST API) and checked against the Master Trademark Filing Chart. "
        f"{disposition} Product titles are matched against <b>every</b> name in the Master Trademark Filing Chart, "
        f"not only the Registered and Pending ones, and findings are listed below grouped by status with the most "
        f"enforceable first. A match against a To Be Filed, Abandoned, Not Applicable, Do Not File or unstatused "
        f"entry is recorded so it is tracked, and carries no enforceable right.",
        styles["RWBody"]))
    story.append(Spacer(1, 8))
    new_other = [c for c in new_cases
                 if c.get("trademark_status") not in ("Registered", "Pending")]
    story.append(stat_table([
        ("Websites checked", f"{roster_companies} / {roster_companies}"),
        ("URLs accessible", f"{coverage['urls_accessible']} / {coverage['urls_total']}"),
        ("Product pages reviewed", f"{coverage['pages_reviewed']:,}"),
        ("Sites/pages not fully accessible", coverage["urls_inaccessible"]),
    ], styles))
    story.append(Spacer(1, 10))
    story.append(stat_table([
        ("New Registered findings (cases)", len(new_registered)),
        ("New Pending findings (cases)", len(new_pending)),
        ("New cases, other chart statuses", len(new_other)),
        ("Possible matches held for review", run["matches_held_pending_case_creation"]),
    ], styles))

    story.append(PageBreak())

    # ---- Websites checked ----
    story.append(Paragraph("Websites Checked", styles["RWH2"]))
    story.append(wrapped_table(
        ["Company", "URL", "Platform", "Pages Reviewed", "Status"],
        coverage["rows"],
        [1.3*inch, 2.35*inch, 1.05*inch, 0.85*inch, 0.75*inch],
        styles,
    ))

    story.append(PageBreak())


    # ---- Dashboard confirmation ----
    story.append(Paragraph("Dashboard", styles["RWH2"]))
    dash_note = "The Rose Watch dashboard (Overview, Trademarks, Cases, Known Sites, Needs Review, Missing Status, Data Sources) was updated to reflect this run." if run.get("dashboard_updated") else "The dashboard was NOT updated this run."
    story.append(Paragraph(dash_note, styles["RWBody"]))
    if run.get("dashboard_url"):
        story.append(Paragraph(f'Dashboard: <link href="{run["dashboard_url"]}">{run["dashboard_url"]}</link>', styles["RWBodySmall"]))

    # ---- New findings, ordered by trademark status ----
    # Registered first, then Pending, then everything else. Until 2026-09-18 this
    # section itemised Registered only; the user widened the crawl to every chart
    # status and asked for all of them listed in that order. Status is a column on
    # every row so a To Be Filed match is never mistaken for an enforceable one.
    STATUS_ORDER = ["Registered", "Pending", "To Be Filed", "Abandoned",
                    "Not Applicable", "Do Not File", "(no status)"]

    def status_rank(name):
        return STATUS_ORDER.index(name) if name in STATUS_ORDER else len(STATUS_ORDER)

    def findings_tables(cases, note_when_empty):
        """One table per trademark status, in enforceability order."""
        if not cases:
            story.append(Paragraph(note_when_empty, styles["RWBody"]))
            return
        groups = {}
        for c in cases:
            groups.setdefault(c.get("trademark_status") or "(no status)", []).append(c)
        for status in sorted(groups, key=status_rank):
            rows = groups[status]
            story.append(Paragraph(
                f"{xml_escape(status)} &mdash; {len(rows)} case{'s' if len(rows) != 1 else ''}",
                ParagraphStyle("statusHead", parent=styles["RWBody"], fontName="Helvetica-Bold",
                               fontSize=11, textColor=ACCENT, spaceBefore=12, spaceAfter=4)))
            table_rows = []
            for c in sorted(rows, key=lambda r: r.get("case_number") or ""):
                detail = load_json(REPO_ROOT / "cases" / c["case_number"] / "case.json", {})
                table_rows.append([
                    c.get("case_number"), c.get("variety"), c.get("seller_name"),
                    c.get("match_classification"), link_cell(detail.get("product_url")),
                ])
            story.append(wrapped_table(
                ["Case #", "Rose Name", "Seller", "Match", "Product URL"],
                table_rows,
                [1.25*inch, 1.45*inch, 1.25*inch, 0.85*inch, 1.4*inch],
                styles,
                raw_html_cols={4},
            ))

    story.append(Paragraph("New Findings", styles["RWH2"]))
    story.append(Paragraph(
        "Every row below is a potential lead for Francis Roses or legal counsel to review &mdash; a matching product "
        "or trademark name, not a legal determination of infringement. Grouped by the trademark's status in the "
        "chart, most enforceable first: <b>Registered</b> and <b>Pending</b> marks carry weight that <b>To Be "
        "Filed</b>, <b>Abandoned</b>, <b>Not Applicable</b>, <b>Do Not File</b> and unstatused entries do not. "
        "Click &ldquo;View listing&rdquo; to open the seller's product page.",
        styles["RWBody"]))
    story.append(Spacer(1, 4))
    findings_tables(new_cases, "No new case records were created on this date.")

    if run.get("matches_held_pending_case_creation", 0):
        story.append(Spacer(1, 10))
        story.append(Paragraph(
            f'<b>{run["matches_held_pending_case_creation"]} additional listings</b> matched a chart name during this '
            f'run but have not been assigned case numbers. '
            + (xml_escape(run["matches_held_note"]) if run.get("matches_held_note") else ""),
            styles["RWNote"]))

    if run.get("review_queue_entries_this_run", 0):
        story.append(Paragraph(
            f'{run["review_queue_entries_this_run"]} additional matches were held in the review queue &mdash; never '
            f'characterized as confirmed infringement.',
            styles["RWNote"]))

    # Cut roses: matched a chart name, but sold as flowers rather than as a plant
    # that can be propagated and resold (user decision, 2026-09-22). Not cases, and
    # not findings -- listed so the count is visible. The section renders only when
    # there is something in it, so an ordinary day's report is unchanged.
    cut_rows = cases_db.get("cut_roses", [])
    if cut_rows:
        story.append(Spacer(1, 12))
        story.append(Paragraph("Cut Roses &mdash; Matched, Not Cases", styles["RWH2"]))
        story.append(Paragraph(
            f"{len(cut_rows)} listing{'s' if len(cut_rows) != 1 else ''} on the roster matched a name in "
            "the trademark chart but is sold as cut flowers &mdash; stems, a bouquet, an arrangement "
            "&mdash; with nothing anywhere in the listing suggesting a plant. Rose Watch monitors "
            "unauthorized sales of rose <i>varieties</i>, meaning plants that can be propagated and "
            "resold, so these are <b>not case records and not findings</b>. They are listed so the "
            "count is visible rather than discarded. A listing that says &ldquo;cut rose&rdquo; "
            "<b>and</b> anything plant-like &mdash; plant, bush, bare root, own root, grafted, shrub, "
            "potted, or growing language &mdash; remains an ordinary case, because &ldquo;cut "
            "rose&rdquo; is overwhelmingly a variety class rather than a product form.",
            styles["RWBody"]))
        story.append(Spacer(1, 4))
        story.append(wrapped_table(
            ["Seller", "Product Title", "Matched Name", "Status", "Product URL"],
            [[r.get("seller_name"), r.get("exact_product_title"), r.get("matched_trademark"),
              r.get("trademark_status") or "(no status)", link_cell(r.get("product_url"))]
             for r in cut_rows],
            [1.15*inch, 1.75*inch, 1.1*inch, 0.85*inch, 1.35*inch],
            styles,
            raw_html_cols={4},
        ))

    # ---- Case history ----
    # Totals first -- the appendix below lists Registered cases only, so the Pending
    # count is otherwise invisible in this report. The full case-by-case list follows;
    # it was briefly dropped on 2026-09-17 to shrink the file for email transcription
    # and restored the same day per user instruction once delivery stopped depending
    # on the file's size.
    all_pending = [c for c in all_cases if c.get("trademark_status") == "Pending"]
    story.append(Spacer(1, 10))
    story.append(Paragraph(
        f"{len(all_cases)} case{'s' if len(all_cases) != 1 else ''} on record to date: "
        f"<b>{len([c for c in all_cases if c.get('trademark_status') == 'Registered'])}</b> against Registered "
        f"trademarks and <b>{len(all_pending)}</b> against Pending. The dashboard carries the complete history, "
        f"including Pending cases, with evidence and review status.",
        styles["RWBody"]))

    # ---- All Past Findings (flows on from the findings above) ----
    story.append(Paragraph("All Cases on Record", styles["RWH2"]))
    story.append(Paragraph(
        "Every case on record to date, not just today's, in the same order: Registered and Pending first, then the "
        "statuses that carry no enforceable right. The dashboard holds the full evidence for each.",
        styles["RWBody"]))
    story.append(Spacer(1, 4))
    findings_tables(all_cases, "No cases exist yet.")

    story.append(PageBreak())

    # ---- Access / research limitations ----
    story.append(Paragraph("Access &amp; Research Limitations", styles["RWH2"]))
    limitation_rows = coverage["limitations"]
    if limitation_rows:
        story.append(wrapped_table(
            ["Company", "URL", "Limitation"],
            limitation_rows,
            [1.3*inch, 2.1*inch, 2.9*inch],
            styles,
            header_bg=BAD,
        ))
    story.append(Spacer(1, 8))
    story.append(Paragraph(f"<b>Screenshot capture:</b> {run['screenshot_limitation']}", styles["RWBodySmall"]))

    story.append(Spacer(1, 14))
    story.append(HRFlowable(width="100%", thickness=0.5, color=LINE, spaceBefore=4, spaceAfter=6))
    story.append(Paragraph(
        "Rose Watch's work is investigative research, not a legal determination. A matching product or trademark "
        "name is a potential lead that must be reviewed by Francis Roses or legal counsel before any action is taken.",
        styles["RWBodySmall"]))

    doc.build(story)
    print(f"Wrote {out_path}")
    return 0


if __name__ == "__main__":
    date_arg = sys.argv[1] if len(sys.argv) > 1 else datetime.datetime.now(PHOENIX).date().isoformat()
    sys.exit(generate(date_arg))
