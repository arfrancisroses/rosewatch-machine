#!/usr/bin/env python3
"""Make web-sized copies of case screenshots for the dashboard artifact.

The full-resolution PNG stays in the case folder as the evidence of record.
This writes a smaller JPEG per case into dashboard/shots/ for the artifact to
serve, because the originals are far too large to publish (hundreds of MB).
"""
import json, os, sys
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "dashboard", "shots")
THUMBS = os.path.join(OUT, "t")
WIDTH = 760
QUALITY = 74
# The Cases table shows a 60x44 thumbnail per row. Pointing those at the full
# display copy would make opening that tab download every screenshot at once,
# so a tiny separate file is written for the table.
THUMB_WIDTH = 190
THUMB_QUALITY = 70

def main():
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(THUMBS, exist_ok=True)
    index = json.load(open(os.path.join(ROOT, "cases/cases.json")))["cases"]
    made = kept = 0
    for row in index:
        cn = row["case_number"]
        case = json.load(open(os.path.join(ROOT, "cases", cn, "case.json")))
        shots = [s for s in (case.get("evidence_screenshots") or [])
                 if s.get("file") and os.path.exists(os.path.join(ROOT, s["file"]))]
        if not shots:
            continue
        src = os.path.join(ROOT, shots[-1]["file"])
        dst = os.path.join(OUT, f"{cn}.jpg")
        tdst = os.path.join(THUMBS, f"{cn}.jpg")
        if (os.path.exists(dst) and os.path.exists(tdst)
                and os.path.getmtime(dst) >= os.path.getmtime(src)):
            kept += 1
            continue
        with Image.open(src) as im:
            im = im.convert("RGB")
            w, h = im.size
            full = im.resize((WIDTH, int(h * WIDTH / w)), Image.LANCZOS) if w > WIDTH else im
            full.save(dst, "JPEG", quality=QUALITY, optimize=True)
            # square-ish crop of the top of the page for the table
            tw = THUMB_WIDTH
            th = int(tw * 44 / 60)
            crop_h = min(h, int(w * 44 / 60))
            im.crop((0, 0, w, crop_h)).resize((tw, th), Image.LANCZOS).save(
                tdst, "JPEG", quality=THUMB_QUALITY, optimize=True)
        made += 1
        print(f"  {cn}: {os.path.getsize(dst)/1024:.0f} KB", file=sys.stderr)
    big = [f for f in os.listdir(OUT) if f.endswith(".jpg")]
    small = [f for f in os.listdir(THUMBS) if f.endswith(".jpg")]
    tb = sum(os.path.getsize(os.path.join(OUT, f)) for f in big)
    ts = sum(os.path.getsize(os.path.join(THUMBS, f)) for f in small)
    print(f"{made} written, {kept} already current; "
          f"{len(big)} display copies ({tb/1024/1024:.1f} MB) + "
          f"{len(small)} table thumbnails ({ts/1024/1024:.1f} MB)", file=sys.stderr)

if __name__ == "__main__":
    main()
