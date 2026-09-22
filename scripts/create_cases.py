#!/usr/bin/env python3
"""Turn a day's crawl matches into full case records.

    python3 scripts/create_cases.py [YYYY-MM-DD] [--stamp "2026-09-18 06:06 MST (America/Phoenix)"]

Reads ``cases/runs/crawl-<date>.json`` and creates one case per match that does
not already have a case at that product URL. The existing-URL check is made
against ``cases.json`` when this runs, not against the ``new_matches`` list the
crawler wrote earlier -- that list is a snapshot from crawl time, and trusting
it would create a second case for every match on a re-run.

Cut-flower listings are never turned into cases (user decision, 2026-09-22):
Rose Watch monitors unauthorized sales of rose varieties -- plants that can be
propagated and resold -- and the crawler counts those listings separately.

Every chart status is recorded, per the user's 2026-09-18 decision. The status
travels onto the case, and into the investigator note, so a To Be Filed or
unstatused match can never read as an enforceable finding.

Seller location and hosting are copied from an existing case at the same site
rather than researched again -- that research is per-site, not per-product. A
site with no case yet has no research to copy, and the script stops rather than
writing a case with empty location fields, because blank is not the same as
"not available" and only one of those is honest.
"""
import argparse
import datetime
import html
import json
import re
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
from crawl_sites import fetch, normalize, PHOENIX  # noqa: E402

# Sites whose first case is being created before any case exists to copy from.
# Research recorded by hand when the site joined the roster; keep the wording,
# including its hedges -- "Estimated" is part of the finding.
SITE_RESEARCH_SEED = {
    "redlandranchroses.com": (
        {"country": "United States",
         "state_or_region": "Florida (Estimated)",
         "city": "Redland / Miami-Dade area (Estimated)",
         "source": "No address published on the contact, about or privacy pages -- only "
                   "info@redlandranchroses.com. Estimated from the business name and the site's "
                   "Deep-South / Fortuniana-rootstock focus; unconfirmed.",
         "estimated": True},
        {"hosting_platform": "Shopify, Inc. (the site's own privacy policy states it is 'powered by Shopify')",
         "cdn_or_proxy": None,
         "server_ip": "23.227.38.32 (apex), within Shopify's 23.227.38.0/24 range",
         "ip_geolocation": "Not determined",
         "registrar": "Not determined -- RDAP/whois endpoints (rdap.org, rdap.verisign.com) are "
                      "refused by this environment's network egress policy",
         "hosting_country": "Not determined"}),
}

STATUS_NOT_ENFORCEABLE = ("To Be Filed", "Abandoned", "Not Applicable", "Do Not File", "(no status)")


def text_of(body, limit=420):
    """The listing's own description, tags stripped, as quoted evidence."""
    t = html.unescape(re.sub(r"(?s)<[^>]+>", " ", body or ""))
    t = re.sub(r"\s+", " ", t).strip()
    if not t:
        return None
    return t[:limit] + ("..." if len(t) > limit else "")


def classify(title, mark):
    """Exact / Strong / Possible, with the reasoning that goes on the record.

    A single ordinary word inside a longer title is Possible, never Strong:
    "Secret" or "Catalina" landing in a product name is as likely to be
    coincidence as the variety, and the case should say so on its face.
    """
    tt, mm = normalize(title), normalize(mark)
    if tt == mm:
        return "Exact", f'The product title normalises exactly to the chart name "{mark}".'
    if len(mm.split()) > 1:
        return "Strong", (f'The product title contains the full chart name "{mark}" as a phrase, '
                          f"inside a longer title.")
    return "Possible", (f'The product title contains the single word "{mark}", which is the whole of '
                        f"the chart entry. A one-word match can be coincidence rather than the variety "
                        f"-- it needs a human read of the listing before it means anything.")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("date", nargs="?", help="run date (default: today, America/Phoenix)")
    ap.add_argument("--stamp", help="evidence timestamp to record on the new cases")
    args = ap.parse_args()

    run_date = args.date or datetime.datetime.now(PHOENIX).date().isoformat()
    stamp = args.stamp or datetime.datetime.now(PHOENIX).strftime("%Y-%m-%d %H:%M %Z (America/Phoenix)")

    crawl_path = REPO / "cases" / "runs" / f"crawl-{run_date}.json"
    if not crawl_path.exists():
        sys.exit(f"No crawl output at {crawl_path} -- run scripts/crawl_sites.py first.")
    crawl = json.loads(crawl_path.read_text())
    db = json.loads((REPO / "cases" / "cases.json").read_text())
    chart = {normalize(r["trademark"]): r for r in
             json.loads((REPO / "data" / "trademarks.json").read_text())["records"] if r.get("trademark")}

    # Live check, not the crawler's snapshot: a case created since the crawl ran
    # must not get a second one.
    existing = set()
    site_research = dict(SITE_RESEARCH_SEED)
    for c in db["cases"]:
        detail = json.loads((REPO / "cases" / c["case_number"] / "case.json").read_text())
        existing.add(detail["product_url"].rstrip("/"))
        site_research.setdefault(c["website_domain"], (detail["seller_location"], detail["website_host"]))

    # The crawler already keeps cut-flower listings out of new_matches; the guard
    # is here too so a hand-edited or older crawl file cannot slip one into a case.
    todo = [m for m in crawl["new_matches"]
            if m["url"].rstrip("/") not in existing and not m.get("cut_flower")]
    if not todo:
        print(f"Nothing to create: all {len(crawl['new_matches'])} matches in crawl-{run_date}.json "
              f"already have cases.")
        return 0

    # Pull full product data once per site, only for sites that actually need it.
    needed = {m["site"] for m in todo}
    catalogs = {}
    for label in needed:
        s = crawl["sites"].get(label, {})
        base = s.get("url_used")
        if not base:
            continue
        prods, page = {}, 1
        while page <= 30:
            batch = (json.loads(fetch(f"{base}/products.json?limit=250&page={page}")) or {}).get("products") or []
            if not batch:
                break
            for p in batch:
                prods[p.get("handle", "")] = p
            if len(batch) < 250:
                break
            page += 1
            time.sleep(0.3)
        catalogs[label] = prods
        print(f"  {label}: {len(prods)} products", file=sys.stderr)
        time.sleep(0.5)

    created = []
    for m in todo:
        label = m["site"]
        domain = (crawl["sites"][label].get("url_used") or "").split("//")[-1].rstrip("/")
        if domain not in site_research:
            sys.exit(f"No seller-location or hosting research on file for {domain}. Add it to "
                     f"SITE_RESEARCH_SEED, or create that site's first case by hand. A case with empty "
                     f"location fields would claim less than 'not available' does.")
        reg = db["site_code_registry"].setdefault(domain, {
            "site_code": re.sub(r"[^A-Z0-9]", "", domain.split(".")[0].upper())[:10], "next_sequence": 1})
        seq = reg["next_sequence"]
        reg["next_sequence"] = seq + 1
        case_no = f"{reg['site_code']}-{seq:03d}"

        rec = chart[normalize(m["trademark"])]
        prod = catalogs.get(label, {}).get(m["url"].rstrip("/").split("/")[-1], {})
        variants = prod.get("variants") or [{}]
        price = variants[0].get("price")
        cls, why = classify(m["title"], m["trademark"])
        loc, host = site_research[domain]
        status = m.get("status") or "(no status)"

        case = {
            "case_number": case_no,
            "site_code": reg["site_code"],
            "variety": rec["trademark"],
            "matched_trademark": rec["trademark"],
            "trademark_status": status,
            "trademark_status_as_written": rec.get("status"),
            "trademark_application_or_registration_no":
                f"App. Ser. No. {rec.get('app_ser_no') or 'none on chart'} "
                f"(Reg. No.: {rec.get('reg_no') or 'none on chart'})",
            "breeder": rec.get("owner_breeder"),
            "seller_name": label.split(" (")[0],
            "website_domain": domain,
            "product_url": m["url"],
            "exact_product_title": m["title"],
            "quoted_text": text_of(prod.get("body_html")),
            "price": price,
            "currency": "USD" if price else None,
            "quantity_or_form": (variants[0].get("title")
                                 if variants[0].get("title") not in (None, "Default Title")
                                 else "Live plant listing (no explicit pot size or quantity in the product feed)"),
            "match_classification": cls,
            "match_explanation": why,
            "review_status": "New",
            "first_date_found": stamp,
            "last_verified": stamp,
            "screenshot_captured_at": None,
            "seller_location": loc,
            "website_host": host,
            "evidence_screenshots": [],
            "access_or_research_limitations": [
                "Full-page screenshot could not be captured: the headless browser available in this "
                "session cannot complete a connection through this environment's network egress proxy. "
                "Evidence here is the product feed's own title, description and price as served by the "
                "site on the date shown.",
            ],
            "investigator_notes": (
                f"Found by the daily catalog crawl on {run_date}, which matches product titles against "
                f"every name in the Master Trademark Filing Chart rather than Registered and Pending only "
                f"(user instruction, 2026-09-18). This record's chart entry is "
                f"\"{rec.get('status') or 'blank'}\""
                + (", which carries no enforceable right: it is recorded so the match is tracked, and must "
                   "not be read as a finding of infringement. " if status in STATUS_NOT_ENFORCEABLE
                   else ". ")
                + why),
            "history": [{"date": stamp, "action": "Case created",
                         "details": "Created from that day's crawl; chart status carried through unchanged."}],
        }
        (REPO / "cases" / case_no / "screenshots").mkdir(parents=True, exist_ok=True)
        (REPO / "cases" / case_no / "case.json").write_text(
            json.dumps(case, indent=2, ensure_ascii=False) + "\n")
        db["cases"].append({
            "case_number": case_no, "site_code": reg["site_code"], "variety": case["variety"],
            "matched_trademark": case["matched_trademark"], "trademark_status": status,
            "seller_name": case["seller_name"], "website_domain": domain,
            "seller_location": loc.get("state_or_region") or loc.get("country"),
            "website_host": (host.get("hosting_platform") or "")[:60],
            "first_date_found": stamp, "last_verified": stamp,
            "match_classification": cls, "review_status": "New",
        })
        created.append(case_no)

    (REPO / "cases" / "cases.json").write_text(json.dumps(db, indent=2, ensure_ascii=False) + "\n")
    from collections import Counter
    print(f"\ncreated {len(created)} cases; {len(db['cases'])} on record")
    print("by status:", dict(Counter(c["trademark_status"] for c in db["cases"][-len(created):])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
