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
WIDTH = 820
QUALITY = 78

def main():
    os.makedirs(OUT, exist_ok=True)
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
        if os.path.exists(dst) and os.path.getmtime(dst) >= os.path.getmtime(src):
            kept += 1
            continue
        with Image.open(src) as im:
            im = im.convert("RGB")
            w, h = im.size
            if w > WIDTH:
                im = im.resize((WIDTH, int(h * WIDTH / w)), Image.LANCZOS)
            im.save(dst, "JPEG", quality=QUALITY, optimize=True)
        made += 1
        print(f"  {cn}: {os.path.getsize(dst)/1024:.0f} KB", file=sys.stderr)
    total = sum(os.path.getsize(os.path.join(OUT, f)) for f in os.listdir(OUT)
                if f.endswith(".jpg"))
    print(f"{made} written, {kept} already current; "
          f"{len([f for f in os.listdir(OUT) if f.endswith('.jpg')])} files, "
          f"{total/1024/1024:.1f} MB total", file=sys.stderr)

if __name__ == "__main__":
    main()
