#!/usr/bin/env python3
"""Render Rose Watch cases as evidence cards (screenshot + field block) into a PDF.

Layout follows the card format the user supplied on 2026-10-19: a page-top
thumbnail on the left, the case's identifying fields on the right, then the
listing URL and the quoted text that supports the match, then the full capture.

Every field is printed from the case record as stored. Where a field is absent
the card says so rather than leaving a blank that could read as "nothing there".
"""
import argparse, json, os, sys
from PIL import Image
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (BaseDocTemplate, Frame, HRFlowable, Image as RLImage,
                                KeepTogether, PageTemplate, Paragraph, Spacer, Table, TableStyle)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INK   = colors.HexColor("#1a2420")
ACCENT= colors.HexColor("#7c2b45")
SOFT  = colors.HexColor("#4d5a4f")
LINE  = colors.HexColor("#c9d1c3")
LINK  = colors.HexColor("#1f5c86")
LABEL = colors.HexColor("#78857a")

def _register_cjk():
    """Pick a CJK face that is embedded in the PDF.

    UnicodeCIDFont("STSong-Light") is NOT embedded: the glyphs render only where
    the reader already has Adobe's Asian font pack, and are invisible everywhere
    else. Several sellers list in Chinese and those titles are evidence, so the
    font is embedded rather than assumed. Falls back to the CID font only if no
    TrueType face is present on this machine.
    """
    for path, idx in (("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc", 0),
                      ("/usr/share/fonts/truetype/fonts-japanese-gothic.ttf", None)):
        if not os.path.exists(path):
            continue
        try:
            pdfmetrics.registerFont(
                TTFont("RWCJK", path, subfontIndex=idx) if idx is not None
                else TTFont("RWCJK", path))
            return "RWCJK", True
        except Exception:
            continue
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    return "STSong-Light", False


CJK, CJK_EMBEDDED = _register_cjk()

def cjk_safe(text):
    """Wrap CJK runs in the CJK font so they render instead of printing as boxes."""
    if not text:
        return ""
    out, run, is_cjk = [], [], False
    def flush():
        if not run:
            return
        chunk = "".join(run)
        out.append(f'<font name="{CJK}">{chunk}</font>' if is_cjk else chunk)
    for ch in str(text):
        c = ("一" <= ch <= "鿿" or "　" <= ch <= "ヿ"
             or "＀" <= ch <= "￯")
        if c != is_cjk:
            flush(); run = []; is_cjk = c
        run.append(ch)
    flush()
    return "".join(out)

HILITE = "#ffe94d"   # highlighter yellow behind the match classification

def highlight(value):
    """The match rating, bold on a yellow highlight so it reads at a glance."""
    if not value:
        return '<font color="#99a29a">Not recorded</font>'
    return (f'<font backColor="{HILITE}" color="#1a2420"><b>&nbsp;{esc(value)}&nbsp;</b></font>')

def clip(text, limit):
    """Trim to a word boundary and mark the trim, so no quotation ends mid-word."""
    t = (text or "").strip()
    if len(t) <= limit:
        return t
    cut = t[:limit]
    sp = cut.rfind(" ")
    if sp > limit * 0.6:
        cut = cut[:sp]
    return cut.rstrip(" ,;:.") + " \u2026"

def quote_display(text, limit=400):
    """Show the stored excerpt, marking it when it was cut short.

    Quoted text is stored truncated, so an excerpt can end mid-word. Marking it
    with an ellipsis is more faithful than letting it stop dead, and nothing is
    added to or changed in the seller's wording.
    """
    t = clip(text, limit)
    if t and not t.endswith(("\u2026", ".", "!", "?", '"', "\u201d")):
        t += "\u2026"
    return t

def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")) if s else ""

def styles():
    st = getSampleStyleSheet()
    def add(n, **kw):
        st.add(ParagraphStyle(n, parent=st["Normal"], **kw))
    add("CardTitle", fontName="Helvetica-Bold", fontSize=12.5, textColor=ACCENT, leading=15, spaceAfter=2)
    add("CardSub",   fontName="Helvetica", fontSize=8.5, textColor=SOFT, leading=11, spaceAfter=4)
    add("CardFound", fontName="Helvetica-Bold", fontSize=9, textColor=LINK, leading=12, spaceAfter=6)
    add("FieldLabel",fontName="Helvetica", fontSize=6.5, textColor=LABEL, leading=8.5)
    add("FieldValue",fontName="Helvetica", fontSize=8.5, textColor=INK, leading=11)
    add("CardURL",   fontName="Helvetica", fontSize=8, textColor=LINK, leading=10.5, spaceBefore=4)
    add("CardQuote", fontName="Helvetica-Oblique", fontSize=8, textColor=INK, leading=10.5, spaceBefore=2)
    add("CapLabel",  fontName="Helvetica", fontSize=7, textColor=LABEL, leading=9, spaceBefore=3)
    add("Disclaim",  fontName="Helvetica", fontSize=7.5, textColor=SOFT, leading=10)
    add("H1",        fontName="Helvetica-Bold", fontSize=17, textColor=INK, leading=21, spaceAfter=2)
    add("Intro",     fontName="Helvetica", fontSize=9, textColor=SOFT, leading=12.5, spaceAfter=10)
    return st

def thumb(src, box=None, max_w_px=1300):
    """Crop the capture to the listing's product image so the rose is legible.

    Keeps the full page width -- header, product photo and the detail column
    (price, shipping, warranty, customer service) -- and cuts at the end of the
    listing's own section, above the shop's related-products rows. If nothing
    usable was recorded, fall back to a proportional top crop rather than
    guessing. The untouched full capture remains on disk either way.
    """
    cache = os.path.join(ROOT, "reports", "_thumbs")
    os.makedirs(cache, exist_ok=True)
    out = os.path.join(cache, os.path.basename(src).replace(".png", "_crop.png"))
    with Image.open(src) as im:
        W, H = im.size
        bottom = None
        if box:
            try:
                d = float(box.get("dpr") or 1)
                y, bh = float(box["y"]) * d, float(box["h"]) * d
                cut = box.get("detail_bottom")
                if cut is not None:
                    cut = float(cut) * d
                    # only trust a cut that sits below the product image
                    if cut > y + bh * 1.05:
                        bottom = cut
                if bottom is None and bh > 40:
                    bottom = y + bh * 1.9      # product image plus its detail column
            except (KeyError, TypeError, ValueError):
                bottom = None
        if bottom is None:
            bottom = W * 1.35
        region = (0, 0, W, max(200, min(H, int(bottom))))
        im = im.crop(region)
        if im.size[0] > max_w_px:
            im = im.resize((max_w_px, int(im.size[1] * max_w_px / im.size[0])), Image.LANCZOS)
        im.save(out)
    return out

def scaled(path, max_w, max_h):
    with Image.open(path) as im:
        w, h = im.size
    r = min(max_w / w, max_h / h)
    return RLImage(path, width=w * r, height=h * r)

def sliced(path, content_w, page_h, st, label):
    """Render a tall capture at full content width, split across pages so the
    listing stays legible instead of being shrunk to fit one frame."""
    cache = os.path.join(ROOT, "reports", "_slices")
    os.makedirs(cache, exist_ok=True)
    base = os.path.splitext(os.path.basename(path))[0]
    with Image.open(path) as im:
        w, h = im.size
        scale = content_w / w                     # points per pixel at full width
        band_px = max(400, int(page_h / scale))   # pixels that fit one page height
        n = (h + band_px - 1) // band_px
        flows = []
        for i in range(n):
            top, bot = i * band_px, min(h, (i + 1) * band_px)
            out = os.path.join(cache, f"{base}_s{i}.png")
            im.crop((0, top, w, bot)).save(out)
            cap = label if i == 0 else f"{label} (continued, part {i + 1} of {n})"
            flows.append(Paragraph(cap, st["CapLabel"]))
            flows.append(Spacer(1, 3))
            flows.append(RLImage(out, width=content_w, height=(bot - top) * scale))
            if i < n - 1:
                flows.append(Spacer(1, 6))
    return flows

def field(st, label, value):
    """One cell: the small grey label above the value, as in the supplied layout.

    Two stacked paragraphs rather than nested <font> tags -- a <font name=...>
    inside another <font> does not take effect, which silently dropped CJK
    characters from values such as the seller's own product title.
    """
    shown = cjk_safe(esc(value)) if value else '<font color="#99a29a">Not recorded</font>'
    return [Paragraph(esc(label), st["FieldLabel"]),
            Paragraph(shown, st["FieldValue"])]

def card(case, st, content_w):
    cn   = case["case_number"]
    img  = (case.get("evidence_screenshots") or [{}])[-1]
    path = os.path.join(ROOT, img["file"]) if img.get("file") else None
    have = bool(path and os.path.exists(path))

    left_w  = 3.05 * inch
    right_w = content_w - left_w - 0.20 * inch

    if have:
        left = scaled(thumb(path, img.get("product_image_box")), left_w, 3.2 * inch)
    else:
        left = Paragraph(
            "<b>No screenshot on file.</b><br/>" +
            esc((case.get("access_or_research_limitations") or ["Not captured."])[-1][:320]),
            st["CardSub"])

    head = [
        Paragraph(f"{esc(cn)} &mdash; {cjk_safe(esc(case.get('variety')))}", st["CardTitle"]),
        Paragraph(f"Listing identified on {esc(case.get('website_domain'))} &middot; "
                  f"Status: {esc(case.get('review_status'))} &middot; "
                  f"Classification: {highlight(case.get('match_classification'))}", st["CardSub"]),
        Paragraph(f"Date &amp; time listing was found: {esc(case.get('first_date_found'))}",
                  st["CardFound"]),
    ]

    loc = case.get("seller_location") or {}
    loc_s = ", ".join(x for x in [loc.get("city"), loc.get("state_or_region"), loc.get("country")]
                      if x and "not available" not in str(x).lower()) or "Location not available"
    host = case.get("website_host") or {}
    host_s = host.get("hosting_platform") or "Hosting information not available"
    price = case.get("price")
    price_s = f"{price} {case.get('currency') or ''}".strip() if price else (
        case.get("price_note") or "No price shown on listing")

    grid = Table([
        [field(st, "MATCHED TRADEMARK", case.get("matched_trademark")),
         field(st, "TRADEMARK STATUS", case.get("trademark_status"))],
        [field(st, "SELLER / BUSINESS", case.get("seller_name")),
         field(st, "DOMAIN", case.get("website_domain"))],
        [field(st, "PRICE", price_s),
         field(st, "SELLER LOCATION", loc_s)],
        [field(st, "WEBSITE HOST", host_s),
         field(st, "EVIDENCE CAPTURED", case.get("screenshot_captured_at") or "Not captured")],
        [field(st, "SELLER\u2019S PRODUCT TITLE", case.get("exact_product_title")), ""],
    ], colWidths=[right_w * 0.44, right_w * 0.56], hAlign="LEFT")
    grid.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("SPAN", (0, 4), (1, 4)),
    ]))

    right = head + [grid]

    outer = Table([[left, right]], colWidths=[left_w, content_w - left_w], hAlign="LEFT")
    outer.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (0, 0), 0), ("RIGHTPADDING", (0, 0), (0, 0), 12),
        ("LEFTPADDING", (1, 0), (1, 0), 0), ("RIGHTPADDING", (1, 0), (1, 0), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))

    below = [
        Paragraph(f'<link href="{esc(case.get("product_url"))}">'
                  f'{cjk_safe(esc(case.get("product_url")))}</link>', st["CardURL"]),
        Paragraph(f'&ldquo;{cjk_safe(esc(quote_display(case.get("quoted_text"))))}&rdquo;',
                  st["CardQuote"]),
    ]
    if have:
        below.append(Paragraph(
            f"Screenshot: full-page capture {esc(img.get('captured_at'))}, filed at "
            f"{esc(img.get('file'))}. Shown here cropped to the listing&rsquo;s product image; "
            f"the complete capture is held with the case.", st["CapLabel"]))
    return [KeepTogether([outer] + below),
            Spacer(1, 10), HRFlowable(width="100%", color=LINE, thickness=0.6), Spacer(1, 10)]

def build(cases, out_path, title, subtitle):
    st = styles()
    content_w = letter[0] - 1.3 * inch
    doc = BaseDocTemplate(out_path, pagesize=letter, leftMargin=0.65 * inch,
                          rightMargin=0.65 * inch, topMargin=0.6 * inch, bottomMargin=0.72 * inch,
                          title=title)
    frame = Frame(doc.leftMargin, doc.bottomMargin, content_w,
                  letter[1] - 1.32 * inch, id="f")

    def footer(canv, d):
        canv.saveState()
        canv.setStrokeColor(LINE); canv.setLineWidth(0.6)
        canv.line(doc.leftMargin, 0.62 * inch, doc.leftMargin + content_w, 0.62 * inch)
        canv.setFont("Helvetica", 7.5); canv.setFillColor(SOFT)
        canv.drawString(doc.leftMargin, 0.46 * inch,
                        "Rose Watch — Francis Roses Intellectual Property Monitoring")
        canv.drawRightString(doc.leftMargin + content_w, 0.46 * inch, f"Page {d.page}")
        canv.restoreState()

    doc.addPageTemplates([PageTemplate(id="main", frames=[frame], onPage=footer)])
    story = [Paragraph(esc(title), st["H1"]), Paragraph(subtitle, st["Intro"]),
             HRFlowable(width="100%", color=LINE, thickness=0.6), Spacer(1, 12)]
    for c in cases:
        story += card(c, st, content_w)
    story.append(Paragraph(
        "A name or product-title match is a research lead, not a legal conclusion. Each case should be "
        "independently reviewed by Francis Roses or legal counsel before any action is taken.",
        st["Disclaim"]))
    doc.build(story)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cases", nargs="+")
    ap.add_argument("--out", required=True)
    ap.add_argument("--title", default="Rose Watch — Evidence Cards (sample)")
    ap.add_argument("--subtitle", default="")
    a = ap.parse_args()
    recs = []
    for cn in a.cases:
        p = os.path.join(ROOT, "cases", cn, "case.json")
        if not os.path.exists(p):
            print(f"no such case: {cn}", file=sys.stderr); return 2
        recs.append(json.load(open(p)))
    build(recs, a.out, a.title, a.subtitle)
    print(f"wrote {a.out}", file=sys.stderr)

if __name__ == "__main__":
    sys.exit(main() or 0)
