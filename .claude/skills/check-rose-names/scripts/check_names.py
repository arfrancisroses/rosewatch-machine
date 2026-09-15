#!/usr/bin/env python3
"""
Check a list of rose/variety names against Rose Watch's Master Trademark
Filing Chart (data/trademarks.json) and report each name's presence and
status.

Usage:
    python3 check_names.py "Beatrice" "Constance" "Pink O'Hara"
    python3 check_names.py --file names.txt      # one name per line
    echo -e "Beatrice\nConstance" | python3 check_names.py -

Output is a markdown table plus a short summary, ready to paste into chat.
Also available as --json for the raw structured data.
"""
import json
import re
import sys
import argparse
import unicodedata
import difflib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
TRADEMARKS_FILE = REPO_ROOT / "data" / "trademarks.json"


def normalize(s):
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    s = re.sub(r"[''`’]", "", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def load_names(args):
    if args.file:
        raw = Path(args.file).read_text(encoding="utf-8").splitlines()
    elif args.names == ["-"]:
        raw = sys.stdin.read().splitlines()
    else:
        raw = args.names
    return [n.strip() for n in raw if n.strip()]


def check(names):
    if not TRADEMARKS_FILE.exists():
        print(f"error: {TRADEMARKS_FILE} not found -- run scripts/import_sources.py first", file=sys.stderr)
        sys.exit(1)
    data = json.loads(TRADEMARKS_FILE.read_text(encoding="utf-8"))
    records = data["records"]

    by_norm = {}
    for r in records:
        if r["trademark"]:
            by_norm.setdefault(normalize(r["trademark"]), []).append(r)

    results = []
    for name in names:
        n = normalize(name)
        exact = by_norm.get(n, [])
        near_misses = []
        if not exact:
            for norm_tm, recs in by_norm.items():
                if norm_tm == n:
                    continue
                # one contains the other as a whole word sequence, but they are not equal
                if re.search(r"(?<!\w)" + re.escape(n) + r"(?!\w)", norm_tm) or \
                   re.search(r"(?<!\w)" + re.escape(norm_tm) + r"(?!\w)", n):
                    near_misses.append(recs[0]["trademark"])

            # Substring containment catches "Garden Julietta Cream" vs "Juliet", but not a
            # transposed/misspelled name like "Withby Abbey" for "Whitby Abbey" -- neither
            # string contains the other, they're just similar. Catch that with a fuzzy
            # similarity ratio instead, restricted to names of comparable length so a short
            # generic word doesn't spuriously match a long unrelated trademark.
            if not near_misses:
                fuzzy = []
                for norm_tm, recs in by_norm.items():
                    if norm_tm == n or abs(len(norm_tm) - len(n)) > max(3, len(n) // 3):
                        continue
                    ratio = difflib.SequenceMatcher(None, n, norm_tm).ratio()
                    if ratio >= 0.82:
                        fuzzy.append((ratio, recs[0]["trademark"]))
                fuzzy.sort(reverse=True)
                near_misses.extend(tm for _, tm in fuzzy[:2])

        results.append({
            "queried_name": name,
            "in_chart": bool(exact),
            "matches": exact,
            "near_misses": sorted(set(near_misses)),
        })
    return results, data


def format_markdown(results, data):
    lines = [
        f"Checked against `{data['source_file']}` (imported {data['imported_date']}, {data['record_count']} records).",
        "",
        "| Name | In Chart? | Status | Trademark Status Category | Breeder | App/Reg No. |",
        "|---|---|---|---|---|---|",
    ]
    for r in results:
        if not r["matches"]:
            near = f" (near-miss, not a real match: {', '.join(r['near_misses'])})" if r["near_misses"] else ""
            lines.append(f"| {r['queried_name']} | No | —{near} | — | — | — |")
            continue
        for m in r["matches"]:
            status = m["status"] or "**Missing/blank in source**"
            needs_review = " ⚠️ Needs Review" if m["needs_review"] else ""
            reg_app = m["reg_no"] or m["app_ser_no"] or "—"
            lines.append(
                f"| {r['queried_name']} | **Yes** | {status}{needs_review} | "
                f"{m['status_category'] or 'Uncategorized'} | {m['owner_breeder'] or '—'} | {reg_app} |"
            )
    return "\n".join(lines)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("names", nargs="*", help="Rose/variety names to check, or '-' to read from stdin")
    p.add_argument("--file", help="Read names from a file, one per line")
    p.add_argument("--json", action="store_true", help="Output raw JSON instead of a markdown table")
    args = p.parse_args()

    names = load_names(args)
    if not names:
        p.error("no names given -- pass them as arguments, --file, or via stdin with '-'")

    results, data = check(names)
    if args.json:
        print(json.dumps(results, indent=2, ensure_ascii=False))
    else:
        print(format_markdown(results, data))


if __name__ == "__main__":
    main()
