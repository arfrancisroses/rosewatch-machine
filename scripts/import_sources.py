#!/usr/bin/env python3
"""
Rose Watch — source import script.

Parses the authoritative source spreadsheets in data/sources/ into the
structured JSON/CSV files Rose Watch reads from (data/trademarks.*,
data/known_sites.*). Re-run this whenever a new Master Trademark Filing
Chart or reseller site list is supplied, after copying the new file into
data/sources/ with a YYYY-MM-DD-prefixed filename.

This script never invents data. Missing/unclear/conflicting fields are
preserved as-is (or left null) and flagged in a "needs_review" field with
a reason, per Rose Watch's "never silently correct uncertain records" rule.
"""
import csv
import json
import sys
import datetime
from pathlib import Path

import openpyxl

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCES_DIR = REPO_ROOT / "data" / "sources"
DATA_DIR = REPO_ROOT / "data"

TRADEMARK_HEADERS = [
    "row_index", "docket_no", "link", "trademark", "status", "reg_no",
    "app_ser_no", "first_use_date", "goods", "eu_reg_no", "filing_date",
    "registration_date", "next_action", "owner_breeder", "party_selling",
]


def _cell(v):
    """Normalize a cell value to a JSON/CSV-friendly form, preserving
    original wording. Dates are rendered ISO 8601; everything else is
    returned as-is (str/int/float/None)."""
    if isinstance(v, (datetime.datetime, datetime.date)):
        return v.isoformat()
    if isinstance(v, str):
        v = v.replace("\xa0", " ").strip()
        return v if v != "" else None
    return v


STATUS_PREFIXES = [
    ("Registered", "Registered"),
    ("Pending", "Pending"),
    ("To Be Filed", "To Be Filed"),
    ("Abandoned", "Abandoned"),
    ("DO NOT FILE", "Do Not File"),
    ("N/A", "Not Applicable"),
]


def classify_status(raw_status):
    """Return (status_category, unrecognized) without altering the stored
    original wording. Anything not matching a known Rose Watch status
    prefix is left uncategorized and flagged for review rather than
    silently corrected."""
    if not raw_status or raw_status == "?":
        return None, True
    for prefix, category in STATUS_PREFIXES:
        if raw_status.strip().upper().startswith(prefix.upper()):
            return category, False
    return None, True


def find_latest_source(prefix_glob):
    matches = sorted(SOURCES_DIR.glob(prefix_glob))
    if not matches:
        raise FileNotFoundError(f"No source file matching {prefix_glob} in {SOURCES_DIR}")
    return matches[-1]


def parse_trademark_chart(path):
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb["Sheet1"]
    records = []
    seen_names = {}
    for r in range(3, ws.max_row + 1):
        row = [_cell(ws.cell(row=r, column=c).value) for c in range(1, 16)]
        trademark = row[3]
        # Skip fully blank rows and breeder-section-header rows (only col B populated)
        if trademark is None and row[1] is None:
            continue
        if trademark is None and all(v is None for v in row if v not in (row[0], row[1])):
            continue
        rec = dict(zip(TRADEMARK_HEADERS, row))
        rec["source_row"] = r

        status_category, status_unrecognized = classify_status(rec["status"])
        rec["status_category"] = status_category

        reasons = []
        if not rec["trademark"]:
            reasons.append("Missing trademark/variety name")
        if status_unrecognized:
            if not rec["status"]:
                reasons.append("Missing status")
            else:
                reasons.append(f"Unrecognized status value: {rec['status']!r}")
        if not rec["owner_breeder"]:
            reasons.append("Missing owner/breeder")
        if rec["status"] == "Registered" and (not rec["reg_no"] or str(rec["reg_no"]).upper() == "NYA"):
            reasons.append("Status is Registered but registration number is missing/NYA")
        if rec["status"] == "Pending" and (not rec["app_ser_no"]):
            reasons.append("Status is Pending but application serial number is missing")

        key = (rec["trademark"] or "").strip().lower()
        if key:
            if key in seen_names:
                reasons.append(f"Duplicate trademark name also on source row {seen_names[key]}")
            else:
                seen_names[key] = r

        for date_field, label in (("filing_date", "Filing Date"), ("registration_date", "Registration Date"), ("first_use_date", "First Use Date")):
            val = rec.get(date_field)
            if val is not None and not isinstance(val, str):
                reasons.append(
                    f"{label} cell contains a raw number ({val!r}) instead of a formatted date in the source "
                    "spreadsheet -- likely an unformatted Excel date serial. Not converted automatically; needs "
                    "source verification."
                )
                rec[date_field] = str(val)

        rec["needs_review"] = bool(reasons)
        rec["needs_review_reasons"] = reasons
        records.append(rec)
    return records


KNOWN_SITE_HEADERS_SHEET1 = None  # discovered dynamically


def parse_known_sites(path):
    wb = openpyxl.load_workbook(path, data_only=True)
    sites = {}

    for sheet_name in ("Sheet1", "Etsy"):
        ws = wb[sheet_name]
        headers = [_cell(ws.cell(row=1, column=c).value) for c in range(1, ws.max_column + 1)]
        # Columns after the fixed lead columns are per-variety flag columns.
        fixed = {"Company", "Website", "Sales platform", "Shipped from", "Notes"}
        variety_cols = [
            (i, h) for i, h in enumerate(headers)
            if h and h not in fixed
        ]
        for r in range(2, ws.max_row + 1):
            row = [_cell(ws.cell(row=r, column=c).value) for c in range(1, ws.max_column + 1)]
            company = row[0]
            if not company:
                continue
            website_raw = row[1] if len(row) > 1 else None
            websites = []
            if website_raw:
                websites = [w.strip() for w in website_raw.split("\n") if w.strip()]

            flagged_varieties = []
            for idx, variety_name in variety_cols:
                if idx >= len(row):
                    continue
                val = row[idx]
                if val and str(val).strip().lower() not in ("-", "n/a", "na"):
                    flagged_varieties.append(variety_name.strip())

            notes = row[headers.index("Notes")] if "Notes" in headers and headers.index("Notes") < len(row) else None

            key = company.strip().lower()
            entry = sites.setdefault(key, {
                "company": company.strip(),
                "websites": [],
                "sales_platforms": set(),
                "shipped_from": None,
                "prior_manual_notes": [],
                "prior_reported_varieties": set(),
                "source_sheets": [],
            })
            for w in websites:
                if w not in entry["websites"]:
                    entry["websites"].append(w)
            sp = row[2] if len(row) > 2 else None
            if sp:
                for p in str(sp).split("\n"):
                    p = p.strip()
                    if p:
                        entry["sales_platforms"].add(p)
            shipped_from = row[3] if len(row) > 3 else None
            if shipped_from and not entry["shipped_from"]:
                entry["shipped_from"] = shipped_from
            if notes and notes not in entry["prior_manual_notes"]:
                entry["prior_manual_notes"].append(notes)
            entry["prior_reported_varieties"].update(flagged_varieties)
            if sheet_name not in entry["source_sheets"]:
                entry["source_sheets"].append(sheet_name)

    out = []
    for entry in sites.values():
        entry["sales_platforms"] = sorted(entry["sales_platforms"])
        entry["prior_reported_varieties"] = sorted(entry["prior_reported_varieties"])
        out.append(entry)
    out.sort(key=lambda e: e["company"].lower())
    return out


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_csv(path, records, headers):
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
        w.writeheader()
        for rec in records:
            row = dict(rec)
            for k, v in row.items():
                if isinstance(v, (list, set)):
                    row[k] = "; ".join(sorted(v)) if isinstance(v, set) else "; ".join(v)
            w.writerow(row)


def main():
    tm_source = find_latest_source("*MasterTrademarkFilingChart.xlsx")
    sites_source = find_latest_source("*ListofIPInfringements*.xlsx")

    print(f"Trademark chart source: {tm_source.name}")
    print(f"Known sites source:     {sites_source.name}")

    trademarks = parse_trademark_chart(tm_source)
    write_json(DATA_DIR / "trademarks.json", {
        "source_file": tm_source.name,
        "imported_date": datetime.date.today().isoformat(),
        "record_count": len(trademarks),
        "records": trademarks,
    })
    write_csv(DATA_DIR / "trademarks.csv", trademarks, TRADEMARK_HEADERS + ["status_category", "needs_review", "needs_review_reasons", "source_row"])
    print(f"Wrote {len(trademarks)} trademark records -> data/trademarks.json / .csv")

    sites = parse_known_sites(sites_source)
    write_json(DATA_DIR / "known_sites.json", {
        "source_file": sites_source.name,
        "imported_date": datetime.date.today().isoformat(),
        "record_count": len(sites),
        "records": sites,
    })
    site_headers = ["company", "websites", "sales_platforms", "shipped_from", "prior_reported_varieties", "prior_manual_notes", "source_sheets"]
    write_csv(DATA_DIR / "known_sites.csv", sites, site_headers)
    print(f"Wrote {len(sites)} known-site records -> data/known_sites.json / .csv")


if __name__ == "__main__":
    sys.exit(main())
