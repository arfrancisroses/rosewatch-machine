#!/usr/bin/env python3
"""Re-verify existing cases against a day's crawl, per CLAUDE.md step 4.

    python3 scripts/reverify_cases.py [YYYY-MM-DD] [--stamp "..."]

For every case, decide one of three things and never blur them:

* the site served and the listing is in its feed -> Last Verified advances and a
  dated entry is appended to the case history;
* the site served and the listing is NOT in its feed -> Last Verified is left
  alone and the case is reported as no longer listed, because a delisting is a
  finding about the listing, not a verification of it;
* the site did not serve -> the case is untouched and reported as unchecked.
  An unreachable site is never clean.

Lived in a scratch file until 2026-10-12, when the container was recycled and it
vanished mid-run. It is part of the daily workflow, so it belongs in the repo.
"""
import argparse
import datetime
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
from create_cases import site_domain, url_key  # noqa: E402  same normalisation as the cases
from crawl_sites import PHOENIX  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("date", nargs="?", help="run date (default: today, America/Phoenix)")
    ap.add_argument("--stamp", help="verification timestamp to record")
    ap.add_argument("--dry-run", action="store_true", help="report without writing")
    args = ap.parse_args()

    run_date = args.date or datetime.datetime.now(PHOENIX).date().isoformat()
    stamp = args.stamp or datetime.datetime.now(PHOENIX).strftime("%Y-%m-%d %H:%M %Z (America/Phoenix)")

    crawl_path = REPO / "cases" / "runs" / f"crawl-{run_date}.json"
    if not crawl_path.exists():
        sys.exit(f"No crawl output at {crawl_path} -- run scripts/crawl_sites.py first.")
    crawl = json.loads(crawl_path.read_text())

    served, listed = set(), set()
    for site in crawl["sites"].values():
        if not site.get("url_used"):
            continue
        served.add(site_domain(site["url_used"]))
        for m in site.get("matches", []):
            listed.add(url_key(m["url"]))

    db = json.loads((REPO / "cases" / "cases.json").read_text())
    verified, gone, unchecked = [], [], []
    for row in db["cases"]:
        path = REPO / "cases" / row["case_number"] / "case.json"
        case = json.loads(path.read_text())
        # Normalise the stored domain too. The oldest Flower Meadow Dream cases
        # recorded "www.myroseworld.com" while the served set is reduced to the
        # apex, so they reported as "site did not serve" -- claiming we could not
        # check when we could, which is the one thing this script must never do.
        if site_domain(row["website_domain"]) not in served:
            unchecked.append(row["case_number"])
            continue
        if url_key(case["product_url"]) not in listed:
            gone.append((row["case_number"], row["website_domain"], case["product_url"]))
            continue
        # Appending the same date twice would double-count a re-run, so skip it.
        if not any(h.get("date") == stamp and h.get("action", "").startswith("Re-verified")
                   for h in case["history"]):
            case["history"].append({
                "date": stamp,
                "action": "Re-verified present in site catalog feed during scheduled daily run."})
        case["last_verified"] = stamp
        row["last_verified"] = stamp
        if not args.dry_run:
            path.write_text(json.dumps(case, indent=2, ensure_ascii=False) + "\n")
        verified.append(row["case_number"])

    if not args.dry_run:
        (REPO / "cases" / "cases.json").write_text(json.dumps(db, indent=2, ensure_ascii=False) + "\n")

    print(f"re-verified: {len(verified)}")
    print(f"on a site that served, but NOT in its feed today: {len(gone)}")
    for cn, dom, url in gone:
        print(f"    {cn}  {dom}  {url}")
    print(f"site did not serve, left untouched: {len(unchecked)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
