#!/usr/bin/env python3
"""Build per-seller evidence packs, plus a Registered-only pack across all sites.

One PDF per site holds every case for that seller as a full evidence card:
screenshot (or a placeholder saying why there is none), the identifying fields,
the listing URL and the quoted text. The daily report's case history is an index
to these; the evidence itself lives here.

Packs are regenerated only when their contents change. The fingerprint covers
what a reader would notice -- which cases are in the pack, their review and
trademark status, when each was last verified, and which screenshot is filed --
so a pack is not reissued on a day nothing about it moved.
"""
import argparse, hashlib, json, os, re, sys
from datetime import datetime
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "reports", "evidence")
STATE = os.path.join(ROOT, "reports", "evidence", ".pack-state.json")
PHX = ZoneInfo("America/Phoenix")

DISCLAIMER = ("A name or product-title match is a research lead, not a legal conclusion. Each case "
              "should be independently reviewed by Francis Roses or legal counsel before any action "
              "is taken.")

def load_cards_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "rw_cards", os.path.join(ROOT, "scripts", "generate_evidence_cards.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def safe_name(text):
    """A filename-safe seller name; separators collapse rather than leaving gaps."""
    cleaned = re.sub(r"[^A-Za-z0-9 ()&.-]", " ", (text or ""))
    return re.sub(r"\s+", " ", cleaned).strip(" -") or "Unknown"

def fingerprint(cases):
    h = hashlib.sha256()
    for c in sorted(cases, key=lambda x: x.get("case_number") or ""):
        shots = c.get("evidence_screenshots") or []
        h.update("|".join([
            str(c.get("case_number")), str(c.get("trademark_status")),
            str(c.get("review_status")), str(c.get("last_verified")),
            str(shots[-1].get("file") if shots else None),
            str(len(c.get("history") or [])),
        ]).encode("utf-8"))
    return h.hexdigest()[:16]

def status_rank(name):
    order = ["Registered", "Pending", "To Be Filed", "Abandoned",
             "Not Applicable", "Do Not File", "(no status)"]
    return order.index(name) if name in order else len(order)

def build_pack(mod, cases, out_path, title, subtitle):
    ordered = sorted(cases, key=lambda c: (status_rank(c.get("trademark_status") or "(no status)"),
                                           c.get("case_number") or ""))
    mod.build(ordered, out_path, title, subtitle)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sites", help="comma-separated site codes; default all")
    ap.add_argument("--force", action="store_true", help="rebuild even if unchanged")
    ap.add_argument("--registered-only", action="store_true")
    a = ap.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)
    state = {}
    if os.path.exists(STATE):
        try:
            state = json.load(open(STATE))
        except ValueError:
            state = {}

    index = json.load(open(os.path.join(ROOT, "cases/cases.json")))["cases"]
    details, by_site = {}, {}
    for row in index:
        cn = row["case_number"]
        path = os.path.join(ROOT, "cases", cn, "case.json")
        if not os.path.exists(path):
            continue
        d = json.load(open(path))
        details[cn] = d
        by_site.setdefault(cn.rsplit("-", 1)[0], []).append(d)

    wanted = {s.strip().upper() for s in (a.sites or "").split(",") if s.strip()} or set(by_site)
    today = datetime.now(PHX).strftime("%Y-%m-%d")
    changed, skipped = [], []

    targets = []
    if not a.registered_only:
        for code in sorted(wanted):
            cases = by_site.get(code) or []
            if not cases:
                continue
            seller = safe_name(cases[0].get("seller_name"))
            targets.append((
                f"site:{code}", cases,
                f"Rose Watch Evidence - {seller} ({code}) - {today}.pdf",
                f"Rose Watch Evidence — {seller}",
                f"Every case on record for {seller} ({cases[0].get('website_domain')}): "
                f"{len(cases)} listing{'s' if len(cases) != 1 else ''}, ordered by trademark status, "
                f"most enforceable first. {DISCLAIMER}"))

    reg = [d for d in details.values() if (d.get("trademark_status") or "") == "Registered"]
    if reg and (a.registered_only or not a.sites):
        sites_n = len({d["case_number"].rsplit("-", 1)[0] for d in reg})
        targets.append((
            "set:REGISTERED", reg,
            f"Rose Watch Evidence - Registered trademarks (all sellers) - {today}.pdf",
            "Rose Watch Evidence — Registered trademarks",
            f"Every case matching a Registered mark on the Francis Roses chart: {len(reg)} listings "
            f"across {sites_n} sellers. These are the only cases carrying an enforceable "
            f"registration. {DISCLAIMER}"))

    if not targets:
        print("nothing to build", file=sys.stderr)
        return 0

    mod = load_cards_module()
    for key, cases, fname, title, subtitle in targets:
        fp = fingerprint(cases)
        prior = state.get(key) or {}
        if prior.get("fingerprint") == fp and not a.force and os.path.exists(
                os.path.join(OUT_DIR, prior.get("file", ""))):
            skipped.append(key)
            continue
        out = os.path.join(OUT_DIR, fname)
        build_pack(mod, cases, out, title, subtitle)
        size = os.path.getsize(out)
        state[key] = {"fingerprint": fp, "file": fname, "cases": len(cases),
                      "built": today, "bytes": size}
        changed.append((key, fname, len(cases), size))
        print(f"  {key:<22} {len(cases):>3} cases  {size/1024/1024:>6.1f} MB  {fname}",
              file=sys.stderr)

    json.dump(state, open(STATE, "w"), indent=2, sort_keys=True)
    open(STATE, "a").write("\n")
    print(f"\n{len(changed)} pack(s) built, {len(skipped)} unchanged", file=sys.stderr)
    return 0

if __name__ == "__main__":
    sys.exit(main())
