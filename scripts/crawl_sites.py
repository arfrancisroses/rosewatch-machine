#!/usr/bin/env python3
"""
Rose Watch -- daily catalog crawl.

Pulls each known site's own product feed (cheapest source of the full catalog,
per CLAUDE.md's "don't over-scrape" rule), matches product titles against the
active Registered/Pending trademark list, and reports which matches are new
versus already covered by an existing case.

Usage: python3 scripts/crawl_sites.py [--out PATH]
       (defaults to cases/runs/crawl-YYYY-MM-DD.json in America/Phoenix)

Writes JSON: {site: {url_used, platform, count, error, matches[]}} plus a
`new_matches` list of matches with no existing case at that product URL.
"""
import argparse
import datetime
import json
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from zoneinfo import ZoneInfo

REPO_ROOT = Path(__file__).resolve().parents[1]
PHOENIX = ZoneInfo("America/Phoenix")
UA = {"User-Agent": "Mozilla/5.0 (compatible; RoseWatch/1.0; IP monitoring)"}

# Marketplace/social hosts have no open product feed and are blocked by this
# environment's egress policy; record them as not-crawlable rather than clean.
NO_FEED_HOSTS = ("etsy.com", "facebook.com", "instagram.com", "amazon.com", "ebay.com")


def normalize(s):
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    s = re.sub(r"[''`’]", "", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def host_variants(url):
    """The URL as given, plus its www/apex counterpart.

    Several tracked sites answer on only one of the two: the egress proxy has
    repeatedly refused `www` hosts (Hillside Rose Farm, Kate Roses, Jessie's
    Roses on 2026-09-16) while the apex served the same catalog fine, and
    myroseworld.com is the reverse. Trying both keeps a proxy quirk from being
    silently reported as an unreachable site.
    """
    parts = urlsplit(url if "://" in url else "https://" + url)
    host = parts.netloc
    other = host[4:] if host.startswith("www.") else "www." + host
    return [urlunsplit(parts._replace(netloc=h)).rstrip("/") for h in (host, other)]


def fetch(url, timeout=45):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def try_shopify(base):
    items, page = [], 1
    while page <= 30:
        data = json.loads(fetch(f"{base}/products.json?limit=250&page={page}"))
        prods = data.get("products")
        if prods is None:
            raise ValueError("no products key")
        if not prods:
            break
        for p in prods:
            items.append((p.get("title", ""), f"{base}/products/{p.get('handle','')}"))
        if len(prods) < 250:
            break
        page += 1
        time.sleep(0.3)
    return items


def try_woocommerce(base):
    items, page = [], 1
    while page <= 40:
        url = f"{base}/wp-json/wp/v2/product?per_page=100&page={page}&_fields=title,link"
        try:
            data = json.loads(fetch(url))
        except urllib.error.HTTPError as e:
            if e.code == 400 and page > 1:
                break  # past the last page
            raise
        if not isinstance(data, list):
            raise ValueError("not a product list")
        if not data:
            break
        for p in data:
            items.append(((p.get("title") or {}).get("rendered", ""), p.get("link", "")))
        if len(data) < 100:
            break
        page += 1
        time.sleep(0.3)
    return items


FEEDS = [("Shopify", try_shopify), ("WordPress/WooCommerce", try_woocommerce)]


def crawl_site(url):
    """Try every feed type against every host variant. Returns a result dict."""
    errors = []
    for candidate in host_variants(url):
        for platform, reader in FEEDS:
            try:
                items = reader(candidate)
            except Exception as e:
                errors.append(f"{candidate} [{platform}]: {type(e).__name__}: {e}")
                continue
            return {"url_used": candidate, "url_attempted": url, "platform": platform,
                    "count": len(items), "error": None, "items": items}
    return {"url_used": None, "url_attempted": url, "platform": None, "count": 0,
            "error": "; ".join(errors) or "no feed found", "items": []}


def marketplace_name(url):
    """Short, readable platform label for a marketplace/social URL."""
    host = urlsplit(url if "://" in url else "https://" + url).netloc.lower()
    host = host[4:] if host.startswith("www.") else host
    for h in NO_FEED_HOSTS:
        if h in host:
            return h.split(".")[0].capitalize()
    return "Marketplace"


def active_trademarks():
    recs = json.loads((REPO_ROOT / "data" / "trademarks.json").read_text())["records"]
    out = {}
    for r in recs:
        if r.get("status_category") in ("Registered", "Pending") and r.get("trademark"):
            out.setdefault(normalize(r["trademark"]), r)
    return out


# Genus names of plants that are not roses. A trademark name is a word, and a
# word can land on any plant: the chart's "Monsieur" matched a peony and
# "Wildberry" matched a heuchera, both at a general nursery that sells far more
# than roses. Neither is evidence of unauthorized rose sales, so they are not
# matches at all and are dropped before anything downstream sees them. Per user
# instruction 2026-09-17: if the product is not a rose, it is not a finding.
NON_ROSE_GENERA = (
    "paeonia", "peony", "peonies", "heuchera", "hydrangea", "kalmia", "aruncus",
    "gaillardia", "sedum", "cornus", "dogwood", "astilbe", "abelia", "clematis",
    "hosta", "echinacea", "salvia", "lavandula", "lavender", "buxus", "boxwood",
    "acer", "maple", "magnolia", "camellia", "azalea", "rhododendron", "viburnum",
    "spiraea", "spirea", "weigela", "forsythia", "lilac", "syringa", "phlox",
    "iris", "peonia", "helleborus", "hellebore", "geranium", "dianthus", "yucca",
    "juniperus", "juniper", "thuja", "arborvitae", "picea", "spruce", "pinus",
    "mountain laurel", "goat's beard", "goats beard", "blanket flower",
    "stonecrop", "coral bells", "butterfly bush", "buddleia", "crape myrtle",
    "lagerstroemia", "nandina", "pieris", "ilex", "holly",
)


def is_rose_product(title):
    """True unless the title names a plant that is not a rose.

    Conservative on purpose: a title that says rose or Rosa anywhere is kept even
    if it also names another genus, so a genuine rose listing is never dropped by
    a stray word. The cost of a wrong drop is a missed finding; the cost of a
    wrong keep is a line in a report. Only the first is serious.
    """
    t = normalize(title)
    toks = set(t.split())
    if "rose" in toks or "roses" in toks or "rosa" in toks:
        return True
    return not any(g in t for g in NON_ROSE_GENERA)


def match_titles(items, active):
    """Whole-word match of a trademark name inside a product title."""
    matches = []
    for title, url in items:
        if not is_rose_product(title):
            continue
        toks = normalize(title).split()
        for tm_norm, rec in active.items():
            tw = tm_norm.split()
            if any(toks[i:i + len(tw)] == tw for i in range(len(toks) - len(tw) + 1)):
                matches.append({"title": title, "url": url,
                                "trademark": rec["trademark"],
                                "status": rec.get("status_category")})
                break
    return matches


def existing_case_urls():
    cases = json.loads((REPO_ROOT / "cases" / "cases.json").read_text())
    out = {}
    for c in cases["cases"]:
        detail = REPO_ROOT / "cases" / c["case_number"] / "case.json"
        if detail.exists():
            url = json.loads(detail.read_text()).get("product_url", "")
            out[url.rstrip("/")] = c["case_number"]
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", help="where to write the crawl JSON")
    args = ap.parse_args()

    today = datetime.datetime.now(PHOENIX).date().isoformat()
    out_path = Path(args.out) if args.out else REPO_ROOT / "cases" / "runs" / f"crawl-{today}.json"

    active = active_trademarks()
    existing = existing_case_urls()
    sites = json.loads((REPO_ROOT / "data" / "known_sites.json").read_text())["records"]
    print(f"{len(active)} active trademark names, {len(existing)} existing case URLs", file=sys.stderr)

    results, new_matches, total = {}, [], 0
    for site in sites:
        for url in site["websites"]:
            label = site["company"] if len(site["websites"]) == 1 else f"{site['company']} ({urlsplit(url).netloc})"
            if any(h in url for h in NO_FEED_HOSTS):
                results[label] = {"url_used": None, "url_attempted": url,
                                  "platform": marketplace_name(url), "count": 0,
                                  "error": "no open product feed; not crawlable from here",
                                  "matches": []}
                print(f"{label}: skipped (no feed)", file=sys.stderr)
                continue
            r = crawl_site(url)
            matches = match_titles(r["items"], active)
            total += r["count"]
            for m in matches:
                if m["url"].rstrip("/") not in existing:
                    new_matches.append({"site": label, **m})
            results[label] = {k: r[k] for k in ("url_used", "url_attempted", "platform", "count", "error")}
            results[label]["matches"] = matches
            note = f"via {r['url_used']}" if r["url_used"] else f"FAILED: {r['error'][:120]}"
            print(f"{label}: {r['count']} products, {len(matches)} matches, {note}", file=sys.stderr)

    payload = {"crawl_date": today, "total_product_pages_reviewed": total,
               "new_matches": new_matches, "sites": results}
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    print(f"\n{total} product pages reviewed; {len(new_matches)} match(es) without an existing case", file=sys.stderr)
    print(f"wrote {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
