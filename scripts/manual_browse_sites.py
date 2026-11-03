#!/usr/bin/env python3
"""Roster entries Rose Watch cannot crawl, with their URLs, for the user to browse by hand.

Per user instruction 2026-11-03: the Facebook pages on the roster are to be
surfaced with every scan so the user can look at them themselves. They cannot be
crawled -- Facebook needs an account and blocks automated access, and this
environment cannot reach facebook.com at all -- so they are reported as coverage
gaps on every run and nothing about them is ever verified. Handing over the links
is the only honest way these get looked at.

Etsy storefronts are the same problem for the same reasons and are listed in
their own group, so the daily summary can carry them without implying the user
asked for them.

    python3 scripts/manual_browse_sites.py            # grouped, for the summary
    python3 scripts/manual_browse_sites.py --json     # machine-readable

This reads the roster only. It makes no network request and does not care
whether a crawl has run.
"""
import argparse
import json
import os
import sys
import urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Host -> (group label, why it cannot be crawled). Matched on the URL's host,
# so a seller's own site is never caught by this even if they also sell here.
PLATFORMS = {
    "facebook.com": ("Facebook", "Facebook pages have no product feed and the site is unreachable from this "
                                 "environment; browsing one needs a signed-in person."),
    "instagram.com": ("Instagram", "No product feed, and the site is unreachable from this environment."),
    "etsy.com": ("Etsy", "Etsy storefronts have no open product feed and the site is unreachable from this "
                         "environment."),
}
# Facebook is what the user asked for, so it leads.
GROUP_ORDER = ["Facebook", "Instagram", "Etsy"]


def host_of(url):
    host = urllib.parse.urlsplit(url.strip()).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def collect():
    path = os.path.join(ROOT, "data", "known_sites.json")
    recs = json.load(open(path, encoding="utf-8"))
    recs = recs["records"] if isinstance(recs, dict) and "records" in recs else recs
    groups = {}
    for r in recs:
        for url in r.get("websites") or []:
            hit = PLATFORMS.get(host_of(url))
            if not hit:
                continue
            label, why = hit
            groups.setdefault(label, {"why": why, "sites": []})["sites"].append(
                {"company": r.get("company"), "url": url.strip()})
    return groups


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    groups = collect()
    if a.json:
        print(json.dumps(groups, indent=1, ensure_ascii=False))
        return 0
    if not groups:
        print("No roster entry needs browsing by hand.")
        return 0
    for label in GROUP_ORDER:
        g = groups.get(label)
        if not g:
            continue
        print(f"{label} -- {len(g['sites'])} to browse by hand. {g['why']}")
        for s in g["sites"]:
            print(f"    {s['company']}")
            print(f"        {s['url']}")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
