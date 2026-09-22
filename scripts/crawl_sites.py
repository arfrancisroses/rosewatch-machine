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
            items.append({"title": p.get("title", ""),
                          "url": f"{base}/products/{p.get('handle','')}",
                          "product_type": p.get("product_type") or "",
                          "tags": p.get("tags") or [],
                          "description": (p.get("body_html") or "")[:3000]})
        if len(prods) < 250:
            break
        page += 1
        time.sleep(0.3)
    return items


def try_woocommerce(base):
    items, page = [], 1
    while page <= 40:
        url = (f"{base}/wp-json/wp/v2/product?per_page=100&page={page}"
               f"&_fields=title,link,content,excerpt")
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
            items.append({"title": (p.get("title") or {}).get("rendered", ""),
                          "url": p.get("link", ""),
                          "product_type": "",
                          "tags": [],
                          "description": ((p.get("content") or {}).get("rendered", "")
                                          or (p.get("excerpt") or {}).get("rendered", ""))[:3000]})
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
    """Every named record in the chart, whatever its status.

    Until 2026-09-18 this returned Registered and Pending only, which meant the
    other 182 of 275 chart records were never compared against a product title at
    all -- the review queue in the spec could not fill because nothing outside the
    active list was ever looked at. Per user instruction 2026-09-18 the crawl now
    matches every name; status travels with each match so a To Be Filed hit is
    never presented as an enforceable finding.
    """
    recs = json.loads((REPO_ROOT / "data" / "trademarks.json").read_text())["records"]
    out = {}
    for r in recs:
        if r.get("trademark"):
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


# ---------------------------------------------------------------------------
# Cut roses (user decision, 2026-09-22)
#
# A listing that is ONLY cut roses -- stems, a bouquet, an arrangement -- is not
# a case. It is moved to the Cut Roses register and shown on its own dashboard
# tab and its own PDF section, so it is visible without sitting among findings.
#
# But a listing that says "cut rose" AND anything plant-like stays an ordinary
# case, because "cut rose" is overwhelmingly used as a VARIETY CLASS -- roses
# bred for the florist trade, sold as plants. Checked against the whole listing,
# not the title: Ergonzi's "Darlington Rose-达林顿｜Netherland Cut Rose" is
# product type "Garden Plants", tagged "Live Plant"; Mola Rose tags 584 products
# "Cut Roses" and 750 "live plant". On the day this rule was written, none of the
# 321 cases on record was cut-roses-only.
#
# So the plant side wins ties and wins on silence: a listing moves only when it
# names a cut-flower product AND nothing anywhere in it suggests a plant. The
# cost of a wrong move is a hidden finding; the cost of a wrong keep is a row in
# a report.
# ---------------------------------------------------------------------------
CUT_ONLY_SIGNALS = (
    "bouquet", "bouquets", "fresh cut", "freshcut", "long stem", "long stemmed",
    "single stem", "stem", "stems", "vase", "centerpiece", "centrepiece",
    "floral arrangement", "arrangement", "arrangements", "preserved",
    "eternal rose", "eternity rose", "forever rose", "infinity rose", "dried",
    "petal", "petals", "boutonniere", "corsage", "dozen", "bunch", "posy",
    "wreath", "garland", "cut rose", "cut roses", "cut flower", "cut flowers",
    "florist", "florists",
)

# Anything here settles a listing as a plant. Growing language counts: High
# Garden's "Florist Hybrid Tea" listings carry no nursery noun but say "easy to
# grow", "Grow tall" and "rose gardeners", and they are plants.
PLANT_SIGNALS = (
    "plant", "plants", "bush", "bushes", "bare root", "bareroot", "bare-root",
    "own root", "ownroot", "grafted", "graft", "non-grafted", "rootstock",
    "seedling", "seedlings", "shrub", "shrubs", "potted", "pot", "gallon",
    "live", "climber", "climbing", "standard", "tree rose", "patio rose",
    "miniature", "starter", "sapling", "cutting", "cuttings", "garden",
    "gardens", "gardener", "gardeners", "grow", "grows", "growing", "growth",
    "grown", "hardy", "hardiness", "zone", "zones", "disease resistance",
    "disease resistant", "disease-resistant", "prune", "pruning", "foliage",
    "rootball", "bloom season", "re-flowering", "reblooming", "repeat blooming",
    "tall", "height", "cm tall", "upright", "floribunda", "hybrid tea",
    "landscape", "container", "planting", "transplant", "soil",
)


def _says(text, tokens, phrases):
    return any(w in tokens for w in phrases if " " not in w) or \
           any(w in text for w in phrases if " " in w)


def listing_text(item):
    """Everything the seller says about the listing, flattened for matching."""
    parts = [item.get("title", ""), item.get("product_type", ""),
             " ".join(item.get("tags") or []), item.get("description", "")]
    return normalize(re.sub(r"(?s)<[^>]+>", " ", " ".join(p for p in parts if p)))


def is_cut_roses_only(item):
    """True only when the whole listing reads as cut flowers and never as a plant."""
    text = listing_text(item)
    tokens = set(text.split())
    if _says(text, tokens, PLANT_SIGNALS):
        return False
    return _says(text, tokens, CUT_ONLY_SIGNALS)


def match_titles(items, active):
    """Whole-word match of a trademark name inside a product title."""
    matches = []
    for item in items:
        title, url = item["title"], item["url"]
        if not is_rose_product(title):
            continue
        toks = normalize(title).split()
        for tm_norm, rec in active.items():
            tw = tm_norm.split()
            if any(toks[i:i + len(tw)] == tw for i in range(len(toks) - len(tw) + 1)):
                matches.append({"title": title, "url": url,
                                "trademark": rec["trademark"],
                                "status": rec.get("status_category") or "(no status)",
                                "status_raw": rec.get("status"),
                                "cut_roses_only": is_cut_roses_only(item)})
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
    print(f"{len(active)} chart names (all statuses), {len(existing)} existing case URLs", file=sys.stderr)

    results, new_matches, cut_roses, total = {}, [], [], 0
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
                if m["url"].rstrip("/") in existing:
                    continue
                (cut_roses if m["cut_roses_only"] else new_matches).append({"site": label, **m})
            results[label] = {k: r[k] for k in ("url_used", "url_attempted", "platform", "count", "error")}
            results[label]["matches"] = matches
            results[label]["cut_roses_only_count"] = sum(1 for m in matches if m["cut_roses_only"])
            note = f"via {r['url_used']}" if r["url_used"] else f"FAILED: {r['error'][:120]}"
            cut = results[label]["cut_roses_only_count"]
            print(f"{label}: {r['count']} products, {len(matches)} matches"
                  + (f", {cut} cut-roses-only" if cut else "") + f", {note}", file=sys.stderr)

    payload = {"crawl_date": today, "total_product_pages_reviewed": total,
               "new_matches": new_matches,
               "cut_roses_only": cut_roses,
               "cut_roses_only_count": len(cut_roses),
               "sites": results}
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    print(f"\n{total} product pages reviewed; {len(new_matches)} match(es) without an existing case",
          file=sys.stderr)
    if cut_roses:
        print(f"{len(cut_roses)} further match(es) are cut-roses-only listings: moved to the Cut Roses "
              f"register, no case created", file=sys.stderr)
    print(f"wrote {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
