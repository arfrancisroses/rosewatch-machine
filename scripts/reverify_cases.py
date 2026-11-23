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


def _listing_state():
    """generate_evidence_cards.listing_state, or None if it cannot be loaded.

    Reused rather than reimplemented. Deciding "is this listing currently
    recorded as absent" needs the same action-string lists the evidence cards
    use, and two copies of those lists is how they drift apart -- which is
    precisely what produced the pack bugs of 2026-11-16 and 2026-11-19. If the
    import ever fails, returns say so instead of being silently dropped.
    """
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "rw_cards", str(REPO / "scripts" / "generate_evidence_cards.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.listing_state
    except Exception as e:                                    # pragma: no cover
        print(f"  WARNING: could not load listing_state ({type(e).__name__}: {e}); "
              f"returns will NOT be flagged this run.", file=sys.stderr)
        return None


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
    verified, gone, unchecked, returned = [], [], [], []
    state_of = _listing_state()
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
        # A listing that was recorded as REMOVED and is in the feed again has
        # COME BACK, which is a material event -- not the same thing as an
        # ordinary daily confirmation, though this script writes the same line
        # for both. Report it so the explicit "Listing is back" entry is written
        # by hand rather than depending on someone noticing the absent-list got
        # shorter. That is how the two Hillside returns of 2026-11-23 were
        # caught, and it would not have survived a busy run.
        # Checked BEFORE the entry below is appended, or today's own re-verify
        # would mask the prior absence.
        if state_of:
            try:
                if state_of(case)[0] == "REMOVED BY THE SELLER":
                    returned.append((row["case_number"], row["website_domain"],
                                     case["product_url"]))
            except Exception as e:                            # pragma: no cover
                print(f"  WARNING: listing_state failed on {row['case_number']} "
                      f"({type(e).__name__}: {e})", file=sys.stderr)
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
    if returned:
        print(f"RETURNED to the feed after being recorded as removed: {len(returned)} "
              f"-- each needs an explicit \"Listing is back\" history entry; this script "
              f"wrote only its routine re-verify line")
        for cn, dom, url in returned:
            print(f"    {cn}  {dom}  {url}")
    print(f"on a site that served, but NOT in its feed today: {len(gone)}")
    for cn, dom, url in gone:
        print(f"    {cn}  {dom}  {url}")
    print(f"site did not serve, left untouched: {len(unchecked)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
