#!/usr/bin/env python3
"""List cases that have no evidence screenshot on file, and say why.

Read-only. Run as part of each daily pass so a missing screenshot is reported
as a coverage gap rather than quietly absent.
"""
import argparse, collections, json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def reason_for(case):
    """Why there is no screenshot.

    Only notes written by an actual capture attempt count. Every case still
    carries a generic line from before captures worked at all, and reading that
    as a current diagnosis would mislabel sites that capture fine today.
    """
    attempts = [l for l in (case.get("access_or_research_limitations") or [])
                if l.startswith(("Screenshot attempt failed", "Screenshot not captured"))]
    if not attempts:
        return "no capture attempted yet"
    last = attempts[-1]
    if "anti-automation" in last or "innerHTML" in last:
        return "seller blocks automated browsing -- manual capture needed"
    if "egress proxy" in last or "Tunnel connection" in last or "403" in last:
        return "our network policy refuses the seller's pages"
    return "last capture attempt failed"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--status", help="only cases with this trademark status")
    ap.add_argument("--list", action="store_true", help="print every case number")
    a = ap.parse_args()

    index = json.load(open(os.path.join(ROOT, "cases/cases.json")))["cases"]
    missing, have = [], 0
    for row in index:
        if a.status and (row.get("trademark_status") or "") != a.status:
            continue
        cn = row["case_number"]
        case = json.load(open(os.path.join(ROOT, "cases", cn, "case.json")))
        shots = [s for s in (case.get("evidence_screenshots") or [])
                 if os.path.exists(os.path.join(ROOT, s.get("file", "")))]
        if shots:
            have += 1
        else:
            missing.append((cn, case.get("seller_name"), row.get("trademark_status"),
                            reason_for(case), case.get("product_url")))

    total = have + len(missing)
    print(f"{have} of {total} cases have a screenshot; {len(missing)} do not.\n")
    by_site = collections.defaultdict(list)
    for cn, seller, status, why, url in missing:
        by_site[cn.rsplit("-", 1)[0]].append((cn, seller, status, why, url))
    for code in sorted(by_site, key=lambda k: -len(by_site[k])):
        rows = by_site[code]
        reasons = sorted({r[3] for r in rows})
        regs = sum(1 for r in rows if r[2] == "Registered")
        print(f"  {code:<13} {len(rows):>3} without a screenshot"
              f"{f' ({regs} Registered)' if regs else ''} -- {'; '.join(reasons)}")
        if a.list:
            for cn, seller, status, why, url in rows:
                print(f"       {cn:<16} {status or '(no status)':<14} {url}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
