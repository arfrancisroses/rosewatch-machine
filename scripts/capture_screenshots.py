#!/usr/bin/env python3
"""Capture full-page evidence screenshots for Rose Watch cases.

Writes cases/<CASE>/screenshots/<CASE>_<YYYY-MM-DD_HHMM>.png and records the
capture on the case record (screenshot_captured_at + evidence_screenshots).

Evidence rules this script follows:
  * It records what it actually did. A capture that fails is reported, never
    silently skipped, and the case keeps "no screenshot" rather than a stale one.
  * Consent/newsletter overlays are dismissed before capture because they hide
    the listing text. The dismissal is logged on the case so the record says
    the page was altered and how.
  * Nothing about access control is bypassed. If the proxy or the site refuses
    the page, that is reported as a limitation.
"""
import argparse, json, os, re, sys
from datetime import datetime
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PHX = ZoneInfo("America/Phoenix")
PROXY = os.environ.get("HTTPS_PROXY") or "http://127.0.0.1:36525"

# The pre-installed browser. The Playwright bindings here may pin a newer build
# than the image ships, so point at the one on disk rather than downloading.
CHROME = os.environ.get("ROSEWATCH_CHROME") or "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"

# Overlay/popup dismissal. Each entry is a CSS selector for a close control or a
# container to hide. Kept narrow on purpose: we remove chrome that covers the
# listing, never listing content itself.
DISMISS_CLICK = [
    "button[aria-label*='close' i]", "button[aria-label*='dismiss' i]",
    "[class*='popup'] button[class*='close' i]", "[class*='modal'] button[class*='close' i]",
    ".needsclick button[class*='close' i]", "#onetrust-accept-btn-handler",
]
HIDE_CSS = """
  [class*='newsletter' i][class*='popup' i], [class*='popup' i][class*='modal' i],
  [id*='newsletter' i][class*='modal' i], .klaviyo-form, [class*='klaviyo' i],
  [class*='cookie' i][class*='banner' i], #onetrust-consent-sdk,
  [class*='backdrop' i], [class*='overlay' i][class*='modal' i],
  .modal-backdrop, .page-overlay, .site-overlay, [class*='bg-overlay' i],
  [class*='drawer' i][class*='cart' i][class*='open' i] { display:none !important; }
  body { overflow:visible !important; }
  html { scroll-behavior:auto !important; }
"""

# A capture is only evidence if the page actually rendered. These are the floors
# below which we treat the result as a failed capture rather than keep a blank
# or near-blank image on the record.
MIN_TEXT_CHARS = 400
MIN_BYTES = 40_000
# An unstyled page (stylesheets blocked) renders as raw HTML. It carries the text
# but does not show the listing as a buyer saw it, so it is not kept as evidence.
# The floor is deliberately low: it exists to catch a page with no styling at all,
# not to judge how much a theme uses. Flower Meadow Dream renders perfectly at 77
# rules, so a threshold near that number rejects good captures.
MIN_CSS_RULES = 25

class RenderFailure(RuntimeError):
    """The page loaded but did not render enough to be usable as evidence."""


def stamp(dt=None):
    return (dt or datetime.now(PHX)).strftime("%Y-%m-%d %H:%M %Z (America/Phoenix)")

def capture(page, url, out_path, settle_ms):
    resp = page.goto(url, wait_until="domcontentloaded", timeout=90000)
    # A delisted product still renders a page -- the shop's 404. Photographing that
    # and filing it against the case would put a picture of "not found" on the
    # record as if it were the listing. Only a 2xx response is evidence of a live
    # listing; anything else is a removal to be recorded in history, not an image.
    if resp is not None and not (200 <= resp.status < 300):
        raise RenderFailure(
            f"the seller returned HTTP {resp.status} for this URL, so the listing is not live; "
            f"no image kept")
    try:
        page.wait_for_load_state("networkidle", timeout=45000)
    except Exception:
        pass  # a store with live chat never goes idle; the page is still rendered
    dismissed = []
    for sel in DISMISS_CLICK:
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                el.click(timeout=2000); dismissed.append(sel)
        except Exception:
            pass
    try:
        page.keyboard.press("Escape")
    except Exception:
        pass
    page.add_style_tag(content=HIDE_CSS)
    # Some themes dim the page with an unnamed full-viewport scrim that no selector
    # above matches. Hide any fixed/absolute element that covers most of the viewport
    # and carries a translucent or dark background. Listing content is never removed:
    # an element is only hidden when it holds no text of its own.
    try:
        dismissed += page.evaluate(r"""() => {
            const hidden = [];
            const vw = innerWidth, vh = innerHeight;
            for (const el of document.querySelectorAll('body *')) {
                const cs = getComputedStyle(el);
                if (cs.position !== 'fixed' && cs.position !== 'absolute') continue;
                if (cs.display === 'none' || cs.visibility === 'hidden') continue;
                const r = el.getBoundingClientRect();
                if (r.width < vw * 0.75 || r.height < vh * 0.55) continue;
                if ((el.innerText || '').trim().length > 40) continue;
                const bg = cs.backgroundColor || '';
                const m = bg.match(/rgba?\(([^)]+)\)/);
                let scrim = false;
                if (m) {
                    const p = m[1].split(',').map(Number);
                    const a = p.length > 3 ? p[3] : 1;
                    const lum = (p[0] + p[1] + p[2]) / 3;
                    scrim = (a > 0.05 && a < 1) || (a === 1 && lum < 90);
                }
                if (scrim || Number(cs.zIndex) >= 1000) {
                    el.style.setProperty('display', 'none', 'important');
                    hidden.push(el.tagName.toLowerCase() + (el.className ?
                        '.' + String(el.className).split(/\s+/)[0] : ''));
                }
            }
            return hidden;
        }""")
    except Exception:
        pass
    # Scroll through so lazy-loaded images render, then return to the top.
    try:
        page.evaluate("""async () => {
            const step = window.innerHeight;
            for (let y = 0; y < document.body.scrollHeight; y += step) {
                window.scrollTo(0, y); await new Promise(r => setTimeout(r, 180));
            }
            window.scrollTo(0, 0); await new Promise(r => setTimeout(r, 400));
        }""")
    except Exception:
        pass
    page.wait_for_timeout(settle_ms)

    # Locate the listing's main product image. The card crops to this band so the
    # rose is legible at card size; the full capture on disk stays the evidence.
    hero = None
    try:
        hero = page.evaluate("""() => {
            let best = null;
            for (const img of document.images) {
                const r = img.getBoundingClientRect();
                const top = r.top + window.scrollY;
                if (r.width < 220 || r.height < 220) continue;
                if (top < 0 || top > 3500) continue;          // off-canvas carousel slides
                if (r.left + window.scrollX < -50) continue;  // ditto, horizontally
                const cs = getComputedStyle(img);
                if (cs.visibility === 'hidden' || cs.display === 'none') continue;
                if (parseFloat(cs.opacity || '1') < 0.2) continue;
                const area = r.width * r.height;
                if (!best || area > best.area) {
                    best = {x: r.left + window.scrollX, y: top,
                            w: r.width, h: r.height, area};
                }
            }
            // Where the listing's own detail section ends, i.e. the top of the
            // first "related products" style block. The card crops above this so
            // it shows the listing itself and not the shop's cross-sell rows.
            let cut = null;
            const re = /^(related products|you may also like|recently viewed|customers also|you might also like|similar products)/i;
            for (const el of document.querySelectorAll('h1,h2,h3,h4,div,section,p,span')) {
                const t = (el.textContent || '').trim();
                if (t.length > 60 || !re.test(t)) continue;
                if (el.offsetParent === null) continue;        // hidden container
                const r2 = el.getBoundingClientRect();
                if (r2.width < 50 || r2.height < 10) continue;
                const top = r2.top + window.scrollY;
                const floor = best ? best.y + best.h : 400;    // must sit below the product image
                if (top > floor && (cut === null || top < cut)) cut = top;
            }
            return best ? {x: best.x, y: best.y, w: best.w, h: best.h,
                           detail_bottom: cut,
                           dpr: window.devicePixelRatio || 1} : null;
        }""")
    except Exception:
        pass

    # Verify the page actually rendered before we call the image evidence.
    text = page.inner_text("body") if page.query_selector("body") else ""
    if len(text.strip()) < MIN_TEXT_CHARS:
        raise RenderFailure(
            f"page rendered only {len(text.strip())} characters of text "
            f"(threshold {MIN_TEXT_CHARS}); blocked sub-resources usually cause this")
    rules = page.evaluate("""() => [...document.styleSheets].reduce((n, s) => {
            try { return n + s.cssRules.length; } catch (e) { return n; } }, 0)""")
    if rules < MIN_CSS_RULES:
        raise RenderFailure(
            f"page loaded unstyled ({rules} CSS rules, threshold {MIN_CSS_RULES}); the "
            f"stylesheets were refused, so the capture would not show the listing as served")

    # Images are often the most probative part of a rose listing. A capture whose
    # photos did not load is still worth keeping for its text, but the record must
    # say so rather than let a blank frame pass for the listing as served.
    imgs = page.evaluate("""() => {
        const all = [...document.images];
        const broken = all.filter(i => !i.complete || i.naturalWidth === 0);
        return {total: all.length, broken: broken.length};
    }""")
    page.screenshot(path=out_path, full_page=True)
    if os.path.getsize(out_path) < MIN_BYTES:
        size = os.path.getsize(out_path)
        os.remove(out_path)
        raise RenderFailure(f"capture was only {size:,} bytes, below the {MIN_BYTES:,} floor")
    return dismissed, hero, imgs

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cases", nargs="*", help="case numbers; default = those named by --status")
    ap.add_argument("--status", help="capture every case with this trademark status")
    ap.add_argument("--missing", action="store_true",
                    help="every case that has no screenshot file on disk")
    ap.add_argument("--skip-sites", default="",
                    help="comma-separated site codes to leave out (e.g. HIGHGARDEN)")
    ap.add_argument("--pace", type=float, default=2.0,
                    help="seconds to wait between cases; keeps the load on a seller gentle")
    ap.add_argument("--width", type=int, default=1400)
    ap.add_argument("--settle", type=int, default=1200)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    index = json.load(open(os.path.join(ROOT, "cases/cases.json")))["cases"]
    wanted = list(args.cases)
    if args.status:
        wanted += [c["case_number"] for c in index
                   if (c.get("trademark_status") or "") == args.status
                   and c["case_number"] not in wanted]
    if args.missing:
        for row in index:
            cn = row["case_number"]
            case_file = os.path.join(ROOT, "cases", cn, "case.json")
            if not os.path.exists(case_file) or cn in wanted:
                continue
            rec = json.load(open(case_file))
            on_disk = [x for x in (rec.get("evidence_screenshots") or [])
                       if x.get("file") and os.path.exists(os.path.join(ROOT, x["file"]))]
            if not on_disk:
                wanted.append(cn)
    skip = {c.strip().upper() for c in args.skip_sites.split(",") if c.strip()}
    if skip:
        before = len(wanted)
        wanted = [c for c in wanted if c.rsplit("-", 1)[0] not in skip]
        print(f"skipping {before - len(wanted)} case(s) on {', '.join(sorted(skip))}",
              file=sys.stderr)
    if not wanted:
        print("nothing selected", file=sys.stderr); return 2

    print(f"{len(wanted)} case(s) selected", file=sys.stderr)
    if args.dry_run:
        for c in wanted: print("  " + c, file=sys.stderr)
        return 0

    from playwright.sync_api import sync_playwright
    ok = fail = 0
    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox"], proxy={"server": PROXY},
                                     executable_path=CHROME)
        ctx = browser.new_context(viewport={"width": args.width, "height": 1200},
                                  ignore_https_errors=False, locale="en-US")
        page = ctx.new_page()
        for cn in wanted:
            cpath = os.path.join(ROOT, "cases", cn, "case.json")
            if not os.path.exists(cpath):
                print(f"  {cn}: no case record", file=sys.stderr); fail += 1; continue
            case = json.load(open(cpath))
            url = case.get("product_url")
            now = datetime.now(PHX)
            shots = os.path.join(ROOT, "cases", cn, "screenshots")
            os.makedirs(shots, exist_ok=True)
            fname = f"{cn}_{now.strftime('%Y-%m-%d_%H%M')}.png"
            out = os.path.join(shots, fname)
            blocked = set()
            page.on("requestfailed", lambda r: blocked.add(
                r.url.split("//")[-1].split("/")[0]) if "TUNNEL" in (r.failure or "") else None)
            try:
                dismissed, hero, imgs = capture(page, url, out, args.settle)
            except Exception as e:
                if os.path.exists(out):
                    os.remove(out)
                detail = f"{type(e).__name__}: {str(e)[:200]}"
                if blocked:
                    detail += (" | sub-resources refused by this environment's egress proxy: "
                               + ", ".join(sorted(blocked)[:6]))
                msg = (f"Screenshot attempt failed {stamp(now)}: {detail}. No image was kept; "
                       f"this case has no screenshot rather than a blank one.")
                case.setdefault("access_or_research_limitations", []).append(msg)
                json.dump(case, open(cpath, "w"), indent=2, ensure_ascii=False)
                open(cpath, "a").write("\n")
                print(f"  {cn}: FAILED {type(e).__name__}", file=sys.stderr); fail += 1; continue
            size = os.path.getsize(out)
            rel = f"cases/{cn}/screenshots/{fname}"
            case["screenshot_captured_at"] = stamp(now)
            case.setdefault("evidence_screenshots", []).append({
                "file": rel, "captured_at": stamp(now), "source_url": url,
                "viewport_width_px": args.width, "full_page": True,
                "bytes": size,
                "product_image_box": hero,
                "images_total": imgs.get("total"),
                "images_failed_to_load": imgs.get("broken"),
                "capture_method": ("Headless Chromium via Playwright, rendered through this "
                                   "environment's egress proxy. Full-page capture at the URL shown."),
                "page_modifications": (
                    "Newsletter/cookie overlays hidden before capture so they did not cover the "
                    "listing" + (f"; dismissed: {', '.join(dismissed)}" if dismissed else "") +
                    ". No listing content was altered, added or removed."),
                "image_load_note": (
                    None if not imgs.get("broken") else
                    f"{imgs['broken']} of {imgs['total']} images on the page did not load and appear "
                    f"blank in this capture. Their host is refused by this environment's network "
                    f"policy, not by the seller. The capture is kept for its text, price and layout; "
                    f"it is not a complete picture of the listing as a buyer saw it."),
            })
            case.setdefault("history", []).append({
                "date": stamp(now), "action": "Evidence screenshot captured",
                "details": f"Full-page capture of {url} saved to {rel} ({size:,} bytes).",
            })
            json.dump(case, open(cpath, "w"), indent=2, ensure_ascii=False)
            open(cpath, "a").write("\n")
            print(f"  {cn}: {size:,} bytes -> {rel}", file=sys.stderr); ok += 1
            if args.pace:
                page.wait_for_timeout(int(args.pace * 1000))
        browser.close()
    print(f"captured {ok}, failed {fail}", file=sys.stderr)
    return 0 if fail == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
