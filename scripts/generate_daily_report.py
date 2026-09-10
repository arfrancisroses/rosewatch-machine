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
import sys
import datetime
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo

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


def generate(run_date_str):
    run_date = datetime.date.fromisoformat(run_date_str)
    run = load_json(RUNS_DIR / f"{run_date_str}.json")
    cases_db = load_json(CASES_FILE, {"cases": [], "review_queue": []})
    known_sites = load_json(REPO_ROOT / "data" / "known_sites.json", {"records": []})

    if run is None:
        print(f"No run log found at cases/runs/{run_date_str}.json", file=sys.stderr)
        return 1

    generated_at = datetime.datetime.now(PHOENIX).strftime("%Y-%m-%d %H:%M %Z")
    as_of = run.get("generated_at", generated_at)

    all_cases = cases_db.get("cases", [])
    # Cases first found on this run date (by First Date Found prefix match)
    new_cases = [c for c in all_cases if str(c.get("first_date_found", "")).startswith(run_date_str)]
    new_registered = [c for c in new_cases if c.get("trademark_status") == "Registered"]
    new_pending = [c for c in new_cases if c.get("trademark_status") == "Pending"]

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
    disposition = (
        f"{created} matches were carried through into full, evidence-complete case records this run"
        + (f"; {held} additional matched listings remain held pending a decision on how to process them into cases."
           if held else ".")
    )
    story.append(Paragraph(
        "This is Rose Watch's first monitoring pass under the current system. All 14 known reseller sites "
        "(16 URLs) on the closed crawl roster were attempted. Product catalogs were pulled directly from each "
        "accessible site's own product data feed (Shopify's product API, Squarespace's collection data, or the "
        f"WordPress REST API) and checked against the Master Trademark Filing Chart. {disposition}",
        styles["RWBody"]))
    story.append(Spacer(1, 8))
    story.append(stat_table([
        ("Websites checked", f"{run['total_sites_on_roster']} / 14"),
        ("URLs accessible", f"{run['urls_accessible']} / {run['total_urls_on_roster']}"),
        ("Product pages reviewed", f"{run['total_product_pages_reviewed']:,}"),
        ("Active-trademark matches found", run["active_trademark_matches_found"]),
    ], styles))
    story.append(Spacer(1, 10))
    story.append(stat_table([
        ("New Registered findings (cases)", len(new_registered)),
        ("New Pending findings (cases)", len(new_pending)),
        ("Possible matches held for review", run["matches_held_pending_case_creation"]),
        ("Sites/pages not fully accessible", run["urls_inaccessible"]),
    ], styles))

    # ---- Websites checked ----
    story.append(Paragraph("Websites Checked", styles["RWH2"]))
    site_rows = []
    for s in run["sites"]:
        status = "Accessible" if s["accessible"] else "Not accessible"
        site_rows.append([s["company"], s["url"], s["platform"], f'{s["product_pages_reviewed"]:,}', status])
    story.append(wrapped_table(
        ["Company", "URL", "Platform", "Pages Reviewed", "Status"],
        site_rows,
        [1.3*inch, 2.35*inch, 1.05*inch, 0.85*inch, 0.75*inch],
        styles,
    ))

    story.append(PageBreak())

    # ---- New findings ----
    story.append(Paragraph("New Findings (Case Records)", styles["RWH2"]))
    if new_cases:
        story.append(Paragraph(
            "Each row below is a potential lead for Francis Roses or legal counsel to review &mdash; a matching "
            "product or trademark name, not a legal determination of infringement. Grouped by seller/site; click "
            "“View listing” to go directly to the product page.",
            styles["RWBody"]))
        story.append(Spacer(1, 8))

        by_seller = {}
        for c in new_cases:
            by_seller.setdefault((c.get("seller_name"), c.get("website_domain"), c.get("website_host")), []).append(c)

        for (seller, domain, host), rows in sorted(by_seller.items(), key=lambda kv: kv[0][0] or ""):
            header = Paragraph(
                f"{xml_escape(seller)} &mdash; {xml_escape(domain)} ({len(rows)} finding{'s' if len(rows) != 1 else ''}, host: {xml_escape(host)})",
                ParagraphStyle("siteHead", parent=styles["RWBody"], fontName="Helvetica-Bold", fontSize=10, textColor=ACCENT, spaceBefore=10, spaceAfter=4))
            find_rows = []
            for c in sorted(rows, key=lambda r: r.get("case_number") or ""):
                detail = load_json(REPO_ROOT / "cases" / c["case_number"] / "case.json", {})
                find_rows.append([
                    c.get("case_number"), c.get("variety"), c.get("trademark_status"),
                    c.get("seller_location"), link_cell(detail.get("product_url")),
                ])
            tbl = wrapped_table(
                ["Case #", "Rose Name", "TM Status", "Seller Location", "Product URL"],
                find_rows,
                [1.1*inch, 1.35*inch, 0.7*inch, 2.0*inch, 1.1*inch],
                styles,
                raw_html_cols={4},
            )
            # Keep the site header glued to at least the table's first row so it never
            # ends up orphaned alone at the bottom of a page.
            story.append(KeepTogether([header, tbl]) if len(find_rows) <= 3 else header)
            if len(find_rows) > 3:
                story.append(tbl)
    else:
        story.append(Paragraph("No new case records were created on this date.", styles["RWBody"]))

    if run.get("matches_held_pending_case_creation", 0):
        story.append(Spacer(1, 10))
        story.append(Paragraph(
            f'<b>{run["matches_held_pending_case_creation"]} additional listings</b> matched an active (Registered or '
            f'Pending) trademark name during this run\'s catalog comparison across the remaining sites, but have not '
            f'yet been assigned case numbers or full evidence records &mdash; this is on hold pending the user\'s '
            f'decision on how to process them (full cases for all, a lighter-evidence pass, or a further staged '
            f'rollout). None of these are lost: they remain identified and available to convert into cases.',
            styles["RWNote"]))

    if run.get("review_queue_entries_this_run", 0):
        story.append(Paragraph(
            f'{run["review_queue_entries_this_run"]} additional matches were held in the review queue (matches '
            f'against To Be Filed, Needs Review, Abandoned, Do Not File, Not Applicable, or Not-in-chart trademark '
            f'records) &mdash; never characterized as confirmed infringement.',
            styles["RWNote"]))

    # ---- Access / research limitations ----
    story.append(Paragraph("Access &amp; Research Limitations", styles["RWH2"]))
    limitation_rows = []
    for s in run["sites"]:
        if not s["accessible"]:
            limitation_rows.append([s["company"], s["url"], s["notes"] or "Not accessible."])
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

    # ---- Dashboard confirmation ----
    story.append(Paragraph("Dashboard", styles["RWH2"]))
    dash_note = "The Rose Watch dashboard (Overview, Trademarks, Cases, Known Sites, Needs Review, Data Sources) was updated to reflect this run." if run.get("dashboard_updated") else "The dashboard was NOT updated this run."
    story.append(Paragraph(dash_note, styles["RWBody"]))
    if run.get("dashboard_url"):
        story.append(Paragraph(f'Dashboard: <link href="{run["dashboard_url"]}">{run["dashboard_url"]}</link>', styles["RWBodySmall"]))

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
