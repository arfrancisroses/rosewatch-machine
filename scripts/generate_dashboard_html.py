#!/usr/bin/env python3
"""
Rose Watch -- interactive HTML dashboard generator.

Reads data/trademarks.json, data/known_sites.json, and cases/cases.json and
renders a single self-contained dashboard/index.html with the current data
embedded inline (searchable/filterable/sortable in the browser via JS).

This is the human-facing dashboard (view it, or have it published as an
Artifact). dashboard/*.md remains the git-diff-friendly machine record.
Re-run after import_sources.py or any change to cases/cases.json.
"""
import json
import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"
CASES_FILE = REPO_ROOT / "cases" / "cases.json"
OUT_FILE = REPO_ROOT / "dashboard" / "index.html"
PHOENIX = ZoneInfo("America/Phoenix")

STATUS_ORDER = ["Registered", "Pending", "To Be Filed", "Abandoned", "Do Not File", "Not Applicable", None]

# Hand-maintained ingestion log, kept in sync with dashboard/DATA_SOURCES.md.
DATA_SOURCES_LOG = [
    {
        "date": "2026-09-10",
        "kind": "Master Trademark Filing Chart",
        "file": "data/sources/2026-09-10_MasterTrademarkFilingChart.xlsx",
        "records": 275,
        "notes": "Initial Rose Watch setup import. 86 records flagged Needs Review (missing/unclear status, missing owner/breeder, Registered status without a registration number, unrecognized status text, or duplicate trademark name).",
    },
    {
        "date": "2026-09-10",
        "kind": "Known reseller website list",
        "file": "data/sources/2026-09-10_ListofIPInfringements.xlsx",
        "records": 14,
        "notes": "Initial Rose Watch setup import (Sheet1 + Etsy tabs, deduplicated by company). Predates the case-tracking system: per-variety flags are informal prior research, not case records. Imported as the crawl roster only. Per user instruction, this roster is now a closed scope -- no sites are added beyond it without explicit direction.",
    },
]


def load_json(path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def now_phoenix_str():
    return datetime.datetime.now(PHOENIX).strftime("%Y-%m-%d %H:%M %Z")


def build_data():
    tm = load_json(DATA_DIR / "trademarks.json", {"records": [], "record_count": 0, "source_file": None, "imported_date": None})
    sites = load_json(DATA_DIR / "known_sites.json", {"records": [], "record_count": 0, "source_file": None, "imported_date": None})
    cases = load_json(CASES_FILE, {"cases": [], "review_queue": [], "last_run_completed": None, "site_code_registry": {}})

    trademarks = []
    for r in tm["records"]:
        trademarks.append({
            "variety": r.get("trademark"),
            "status": r.get("status"),
            "statusCategory": r.get("status_category"),
            "breeder": r.get("owner_breeder"),
            "docket": r.get("docket_no"),
            "appNo": r.get("app_ser_no"),
            "regNo": r.get("reg_no"),
            "filingDate": r.get("filing_date"),
            "regDate": r.get("registration_date"),
            "authorizedSeller": r.get("party_selling"),
            "needsReview": r.get("needs_review", False),
            "needsReviewReasons": r.get("needs_review_reasons", []),
            "sourceRow": r.get("source_row"),
        })

    known_sites = []
    for s in sites["records"]:
        known_sites.append({
            "company": s.get("company"),
            "websites": s.get("websites", []),
            "salesPlatforms": s.get("sales_platforms", []),
            "shippedFrom": s.get("shipped_from"),
            "priorVarieties": s.get("prior_reported_varieties", []),
            "notes": s.get("prior_manual_notes", []),
        })

    case_rows = cases.get("cases", [])
    review_queue = cases.get("review_queue", [])

    status_counts = {}
    for r in trademarks:
        key = r["statusCategory"] or "Needs Review"
        status_counts[key] = status_counts.get(key, 0) + 1
    active_count = status_counts.get("Registered", 0) + status_counts.get("Pending", 0)
    needs_review_tm = [r for r in trademarks if r["needsReview"]]

    data = {
        "generatedAt": now_phoenix_str(),
        "trademarks": trademarks,
        "knownSites": known_sites,
        "cases": case_rows,
        "reviewQueue": review_queue,
        "needsReviewTrademarks": needs_review_tm,
        "dataSources": DATA_SOURCES_LOG,
        "meta": {
            "trademarkSourceFile": tm.get("source_file"),
            "trademarkImportedDate": tm.get("imported_date"),
            "siteSourceFile": sites.get("source_file"),
            "siteImportedDate": sites.get("imported_date"),
            "trademarkCount": tm.get("record_count", 0),
            "siteCount": sites.get("record_count", 0),
            "statusCounts": status_counts,
            "activeCount": active_count,
            "needsReviewCount": len(needs_review_tm),
            "caseCount": len(case_rows),
            "reviewQueueCount": len(review_queue),
            "lastRunCompleted": cases.get("last_run_completed"),
        },
    }
    return data


TEMPLATE = r"""<!doctype html>
<title>Rose Watch</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,500;9..144,600;9..144,700&family=Public+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap');

:root {
  --paper: #f3f6f1;
  --paper-raised: #ffffff;
  --ink: #1a2420;
  --ink-soft: #4d5a4f;
  --ink-faint: #7c8880;
  --line: #dbe2d6;
  --line-soft: #e8ece3;
  --accent: #7c2b45;
  --accent-ink: #5c1f34;
  --accent-soft: #f4e4e9;
  --ok: #2f6844;
  --ok-soft: #e2eee5;
  --warn: #a5690f;
  --warn-soft: #f6ead2;
  --bad: #a3352a;
  --bad-soft: #f5e0dd;
  --neutral: #656d61;
  --neutral-soft: #eaece6;
  --shadow: 0 1px 2px rgba(26,36,32,0.06), 0 6px 20px -8px rgba(26,36,32,0.12);
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --paper: #121a15;
    --paper-raised: #1a231c;
    --ink: #e7ece3;
    --ink-soft: #aab6a5;
    --ink-faint: #7c8880;
    --line: #2c372d;
    --line-soft: #232d24;
    --accent: #e18aa1;
    --accent-ink: #f4c1cf;
    --accent-soft: #3a1f28;
    --ok: #6cbb8a;
    --ok-soft: #1c2f22;
    --warn: #e2ab55;
    --warn-soft: #362a17;
    --bad: #e5786a;
    --bad-soft: #382220;
    --neutral: #9aa196;
    --neutral-soft: #232922;
    --shadow: 0 1px 2px rgba(0,0,0,0.3), 0 6px 24px -8px rgba(0,0,0,0.5);
  }
}
:root[data-theme="dark"] {
  --paper: #121a15;
  --paper-raised: #1a231c;
  --ink: #e7ece3;
  --ink-soft: #aab6a5;
  --ink-faint: #7c8880;
  --line: #2c372d;
  --line-soft: #232d24;
  --accent: #e18aa1;
  --accent-ink: #f4c1cf;
  --accent-soft: #3a1f28;
  --ok: #6cbb8a;
  --ok-soft: #1c2f22;
  --warn: #e2ab55;
  --warn-soft: #362a17;
  --bad: #e5786a;
  --bad-soft: #382220;
  --neutral: #9aa196;
  --neutral-soft: #232922;
  --shadow: 0 1px 2px rgba(0,0,0,0.3), 0 6px 24px -8px rgba(0,0,0,0.5);
}

* { box-sizing: border-box; }
body {
  background: var(--paper);
  color: var(--ink);
  font-family: 'Public Sans', system-ui, -apple-system, sans-serif;
  margin: 0;
  padding-inline: max(16px, env(safe-area-inset-left));
  -webkit-font-smoothing: antialiased;
}
h1, h2, h3 { font-family: 'Fraunces', Georgia, serif; text-wrap: balance; margin: 0; }
.mono, .tabular { font-family: 'IBM Plex Mono', ui-monospace, monospace; font-variant-numeric: tabular-nums; }
a { color: var(--accent-ink); }

.shell { max-width: 1180px; margin: 0 auto; padding-block: 28px 60px; }

/* Header */
.masthead { display: flex; flex-wrap: wrap; align-items: baseline; justify-content: space-between; gap: 12px 24px; padding-bottom: 18px; border-bottom: 1px solid var(--line); }
.brand { display: flex; align-items: baseline; gap: 12px; flex-wrap: wrap; }
.brand h1 { font-size: 28px; font-weight: 600; letter-spacing: -0.01em; }
.brand .tag { color: var(--ink-soft); font-size: 14px; }
.masthead .meta { font-size: 12.5px; color: var(--ink-faint); text-align: right; }
.masthead .meta strong { color: var(--ink-soft); font-weight: 600; }

/* Tabs */
.tabs { display: flex; gap: 4px; overflow-x: auto; margin-top: 18px; padding-bottom: 2px; scrollbar-width: thin; }
.tab { flex: 0 0 auto; font-family: 'Public Sans', sans-serif; font-size: 14px; font-weight: 600; color: var(--ink-soft); background: transparent; border: none; padding: 9px 14px; border-radius: 8px 8px 0 0; cursor: pointer; white-space: nowrap; border-bottom: 2px solid transparent; }
.tab:hover { color: var(--ink); background: var(--line-soft); }
.tab[aria-selected="true"] { color: var(--accent-ink); border-bottom: 2px solid var(--accent); }
.tab:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; }

.panel { display: none; padding-top: 22px; }
.panel.active { display: block; }

/* Stat tiles */
.stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; margin-bottom: 22px; }
.stat { background: var(--paper-raised); border: 1px solid var(--line); border-radius: 10px; padding: 14px 16px; box-shadow: var(--shadow); }
.stat .n { font-family: 'Fraunces', serif; font-size: 26px; font-weight: 600; line-height: 1.1; }
.stat .l { font-size: 12px; color: var(--ink-soft); margin-top: 4px; }
.stat.accent .n { color: var(--accent-ink); }
.stat.ok .n { color: var(--ok); }
.stat.warn .n { color: var(--warn); }
.stat.bad .n { color: var(--bad); }

/* Section intro text */
.intro { font-size: 14.5px; color: var(--ink-soft); max-width: 68ch; margin-bottom: 18px; line-height: 1.55; }
.intro strong { color: var(--ink); }

/* Controls */
.controls { display: flex; flex-wrap: wrap; gap: 8px 10px; align-items: center; margin-bottom: 14px; }
.controls input[type="search"] {
  font: inherit; font-size: 13.5px; padding: 8px 12px; border-radius: 8px; border: 1px solid var(--line);
  background: var(--paper-raised); color: var(--ink); min-width: 200px; flex: 1 1 200px;
}
.controls select {
  font: inherit; font-size: 13.5px; padding: 8px 10px; border-radius: 8px; border: 1px solid var(--line);
  background: var(--paper-raised); color: var(--ink);
}
.chipset { display: flex; flex-wrap: wrap; gap: 6px; }
.chip {
  font-size: 12.5px; font-weight: 600; padding: 5px 11px; border-radius: 999px; border: 1px solid var(--line);
  background: var(--paper-raised); color: var(--ink-soft); cursor: pointer; white-space: nowrap;
}
.chip[aria-pressed="true"] { background: var(--accent-soft); color: var(--accent-ink); border-color: var(--accent-soft); }
.chip:focus-visible { outline: 2px solid var(--accent); }
.result-count { font-size: 12.5px; color: var(--ink-faint); margin-left: auto; white-space: nowrap; }

/* Table */
.tablewrap { overflow-x: auto; border: 1px solid var(--line); border-radius: 10px; box-shadow: var(--shadow); }
table { border-collapse: collapse; width: 100%; font-size: 13px; background: var(--paper-raised); }
th, td { padding: 9px 12px; text-align: left; border-bottom: 1px solid var(--line-soft); vertical-align: top; }
thead th {
  position: sticky; top: 0; background: var(--paper-raised); font-size: 11.5px; text-transform: uppercase; letter-spacing: 0.04em;
  color: var(--ink-faint); font-weight: 600; cursor: pointer; user-select: none; white-space: nowrap; border-bottom: 1px solid var(--line);
}
thead th:hover { color: var(--ink-soft); }
thead th.sorted::after { content: " " attr(data-arrow); }
tbody tr:hover { background: var(--line-soft); }
tbody tr:last-child td { border-bottom: none; }
td.num { font-family: 'IBM Plex Mono', monospace; font-variant-numeric: tabular-nums; white-space: nowrap; }
.empty-row td { text-align: center; color: var(--ink-faint); padding: 28px; }

/* Pills */
.pill { display: inline-flex; align-items: center; gap: 5px; font-size: 11.5px; font-weight: 600; padding: 3px 9px; border-radius: 999px; white-space: nowrap; }
.pill.ok { background: var(--ok-soft); color: var(--ok); }
.pill.warn { background: var(--warn-soft); color: var(--warn); }
.pill.bad { background: var(--bad-soft); color: var(--bad); }
.pill.neutral { background: var(--neutral-soft); color: var(--neutral); }
.pill.dot::before { content: ""; width: 6px; height: 6px; border-radius: 50%; background: currentColor; }

.small-note { font-size: 12px; color: var(--ink-faint); margin-top: 10px; }
.case-detail { font-size: 12.5px; color: var(--ink-soft); }
.case-detail summary { cursor: pointer; color: var(--accent-ink); font-weight: 600; }
code.k { font-family: 'IBM Plex Mono', monospace; background: var(--neutral-soft); padding: 1px 5px; border-radius: 4px; font-size: 11.5px; }

footer.foot { margin-top: 40px; padding-top: 16px; border-top: 1px solid var(--line); font-size: 12px; color: var(--ink-faint); }

@media (max-width: 560px) {
  .brand h1 { font-size: 23px; }
  .masthead { flex-direction: column; }
  .masthead .meta { text-align: left; }
}
</style>

<div class="shell">
  <header class="masthead">
    <div class="brand">
      <h1>Rose Watch</h1>
      <span class="tag">IP monitoring &amp; evidence dashboard &middot; Francis Roses</span>
    </div>
    <div class="meta">Dashboard generated <strong id="genAt"></strong><br>America/Phoenix</div>
  </header>

  <nav class="tabs" role="tablist" aria-label="Dashboard sections">
    <button class="tab" role="tab" data-panel="overview" aria-selected="true">Overview</button>
    <button class="tab" role="tab" data-panel="trademarks">Trademarks</button>
    <button class="tab" role="tab" data-panel="cases">Cases</button>
    <button class="tab" role="tab" data-panel="sites">Known Sites</button>
    <button class="tab" role="tab" data-panel="review">Needs Review</button>
    <button class="tab" role="tab" data-panel="sources">Data Sources</button>
  </nav>

  <section class="panel active" id="panel-overview"></section>
  <section class="panel" id="panel-trademarks"></section>
  <section class="panel" id="panel-cases"></section>
  <section class="panel" id="panel-sites"></section>
  <section class="panel" id="panel-review"></section>
  <section class="panel" id="panel-sources"></section>

  <footer class="foot">
    Investigative research, not a legal determination. A matching product or trademark name is a potential lead for Francis Roses or legal counsel to review.
  </footer>
</div>

<script id="rw-data" type="application/json">__DASHBOARD_DATA__</script>
<script>
const DATA = JSON.parse(document.getElementById('rw-data').textContent);

function esc(s){ return (s===null||s===undefined) ? '' : String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }

function statusPill(status, category){
  const label = esc(status || 'Needs Review');
  let cls = 'neutral';
  if (category === 'Registered') cls = 'ok';
  else if (category === 'Pending') cls = 'warn';
  else if (!category) cls = 'bad';
  return `<span class="pill dot ${cls}">${label}</span>`;
}
function reviewStatusPill(rs){
  const s = (rs||'New');
  const map = {New:'warn', Reviewing:'warn', Confirmed:'bad', Dismissed:'neutral', Resolved:'ok', Monitoring:'ok'};
  return `<span class="pill ${map[s]||'neutral'}">${esc(s)}</span>`;
}
function matchPill(m){
  const map = {Exact:'bad', Strong:'warn', Possible:'neutral', Uncertain:'neutral'};
  return `<span class="pill ${map[m]||'neutral'}">${esc(m||'—')}</span>`;
}

document.getElementById('genAt').textContent = DATA.generatedAt;

/* ---------- Tabs ---------- */
const tabs = Array.from(document.querySelectorAll('.tab'));
tabs.forEach(tab => tab.addEventListener('click', () => {
  tabs.forEach(t => t.setAttribute('aria-selected', 'false'));
  tab.setAttribute('aria-selected', 'true');
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
  document.getElementById('panel-' + tab.dataset.panel).classList.add('active');
}));

/* ---------- Generic sortable/filterable table ---------- */
function makeTable(container, {columns, rows, getSortValue, rowHtml, emptyMessage}) {
  let sortCol = null, sortDir = 1;
  const wrap = document.createElement('div');
  wrap.className = 'tablewrap';
  const table = document.createElement('table');
  const thead = document.createElement('thead');
  const trh = document.createElement('tr');
  columns.forEach(col => {
    const th = document.createElement('th');
    th.textContent = col.label;
    if (col.sortKey) {
      th.addEventListener('click', () => {
        if (sortCol === col.sortKey) sortDir *= -1; else { sortCol = col.sortKey; sortDir = 1; }
        render();
      });
    }
    th.dataset.key = col.sortKey || '';
    trh.appendChild(th);
  });
  thead.appendChild(trh);
  const tbody = document.createElement('tbody');
  table.appendChild(thead); table.appendChild(tbody);
  wrap.appendChild(table);
  container.appendChild(wrap);

  function render(filtered) {
    const data = filtered || container._lastFiltered || rows;
    container._lastFiltered = data;
    let sorted = data;
    if (sortCol) {
      sorted = data.slice().sort((a,b) => {
        const av = getSortValue(a, sortCol), bv = getSortValue(b, sortCol);
        if (av < bv) return -1 * sortDir;
        if (av > bv) return 1 * sortDir;
        return 0;
      });
    }
    Array.from(trh.children).forEach(th => {
      th.classList.remove('sorted'); th.removeAttribute('data-arrow');
      if (th.dataset.key === sortCol) { th.classList.add('sorted'); th.setAttribute('data-arrow', sortDir === 1 ? '↑' : '↓'); }
    });
    tbody.innerHTML = sorted.length ? sorted.map(rowHtml).join('') : `<tr class="empty-row"><td colspan="${columns.length}">${emptyMessage || 'No matching rows.'}</td></tr>`;
    return sorted.length;
  }
  render(rows);
  return { render, table };
}

/* ---------- Overview ---------- */
(function renderOverview(){
  const el = document.getElementById('panel-overview');
  const m = DATA.meta;
  el.innerHTML = `
    <div class="stats">
      <div class="stat accent"><div class="n tabular">${m.activeCount}</div><div class="l">Active trademarks<br>(Registered + Pending)</div></div>
      <div class="stat"><div class="n tabular">${m.trademarkCount}</div><div class="l">Total trademark records</div></div>
      <div class="stat bad"><div class="n tabular">${m.needsReviewCount}</div><div class="l">Trademark records<br>flagged Needs Review</div></div>
      <div class="stat"><div class="n tabular">${m.siteCount}</div><div class="l">Known reseller sites<br>(closed roster)</div></div>
      <div class="stat ok"><div class="n tabular">${m.caseCount}</div><div class="l">Active cases</div></div>
      <div class="stat warn"><div class="n tabular">${m.reviewQueueCount}</div><div class="l">Review-queue entries</div></div>
    </div>
    <div class="intro">
      <strong>Trademark status breakdown:</strong>
      ${Object.entries(m.statusCounts).map(([k,v]) => `${esc(k)}: <strong>${v}</strong>`).join(' &nbsp;&middot;&nbsp; ')}
    </div>
    <div class="intro">
      Last completed monitoring run: <strong>${esc(m.lastRunCompleted) || 'none yet'}</strong>.
      Rose Watch's work is investigative research, not a legal determination &mdash; every case here is a potential lead for Francis Roses or legal counsel to review, not a confirmed infringement.
    </div>
  `;
})();

/* ---------- Trademarks ---------- */
(function renderTrademarks(){
  const el = document.getElementById('panel-trademarks');
  el.innerHTML = `
    <div class="intro">All records from the Master Trademark Filing Chart, in the original wording. Rows flagged <strong>Needs Review</strong> have missing, unclear, duplicate, or conflicting source data and were not silently corrected.</div>
    <div class="controls">
      <input type="search" id="tm-search" placeholder="Search variety, breeder, docket…">
      <div class="chipset" id="tm-status-chips"></div>
      <span class="result-count" id="tm-count"></span>
    </div>
    <div id="tm-table"></div>
  `;
  const statuses = ['Registered','Pending','To Be Filed','Abandoned','Do Not File','Not Applicable','Needs Review'];
  const chipsEl = document.getElementById('tm-status-chips');
  const active = new Set();
  statuses.forEach(s => {
    const b = document.createElement('button');
    b.className = 'chip'; b.textContent = s; b.setAttribute('aria-pressed','false');
    b.addEventListener('click', () => {
      if (active.has(s)) { active.delete(s); b.setAttribute('aria-pressed','false'); }
      else { active.add(s); b.setAttribute('aria-pressed','true'); }
      applyFilter();
    });
    chipsEl.appendChild(b);
  });

  const tbl = makeTable(document.getElementById('tm-table'), {
    columns: [
      {label:'Variety', sortKey:'variety'},
      {label:'Breeder', sortKey:'breeder'},
      {label:'Status', sortKey:'status'},
      {label:'Docket', sortKey:'docket'},
      {label:'App. Ser. No.', sortKey:'appNo'},
      {label:'Reg. No.', sortKey:'regNo'},
      {label:'Filing Date', sortKey:'filingDate'},
      {label:'Reg. Date', sortKey:'regDate'},
      {label:'Authorized Seller', sortKey:'authorizedSeller'},
    ],
    rows: DATA.trademarks,
    getSortValue: (r,k) => (r[k] ?? '').toString().toLowerCase(),
    emptyMessage: 'No trademarks match this filter.',
    rowHtml: r => `<tr>
      <td>${esc(r.variety) || '<em>(unnamed)</em>'}${r.needsReview ? ' <span class=\"pill bad\" title=\"'+esc((r.needsReviewReasons||[]).join('; '))+'\">Needs Review</span>' : ''}</td>
      <td>${esc(r.breeder)}</td>
      <td>${statusPill(r.status, r.statusCategory)}</td>
      <td class="mono">${esc(r.docket)}</td>
      <td class="mono">${esc(r.appNo)}</td>
      <td class="mono">${esc(r.regNo)}</td>
      <td class="mono">${esc((r.filingDate||'').slice(0,10))}</td>
      <td class="mono">${esc((r.regDate||'').slice(0,10))}</td>
      <td>${esc(r.authorizedSeller)}</td>
    </tr>`
  });

  const searchEl = document.getElementById('tm-search');
  const countEl = document.getElementById('tm-count');
  function applyFilter(){
    const q = searchEl.value.trim().toLowerCase();
    const filtered = DATA.trademarks.filter(r => {
      if (active.size) {
        const cat = r.statusCategory || 'Needs Review';
        if (!active.has(cat) && !(active.has('Needs Review') && r.needsReview)) return false;
      }
      if (!q) return true;
      return [r.variety, r.breeder, r.docket, r.appNo, r.regNo].some(v => (v??'').toString().toLowerCase().includes(q));
    });
    const n = tbl.render(filtered);
    countEl.textContent = `${n} of ${DATA.trademarks.length}`;
  }
  searchEl.addEventListener('input', applyFilter);
  applyFilter();
})();

/* ---------- Cases ---------- */
(function renderCases(){
  const el = document.getElementById('panel-cases');
  el.innerHTML = `
    <div class="intro">Potential-infringement findings matched to a <strong>Registered</strong> or <strong>Pending</strong> trademark. Every row is a lead for review, not a legal conclusion.</div>
    <div class="controls">
      <input type="search" id="case-search" placeholder="Search case #, variety, seller, domain…">
      <select id="case-status"><option value="">All trademark statuses</option></select>
      <select id="case-site"><option value="">All sites</option></select>
      <select id="case-review"><option value="">All review statuses</option></select>
      <span class="result-count" id="case-count"></span>
    </div>
    <div id="case-table"></div>
    <p class="small-note">Full evidence for each case (quoted text, screenshots, hosting lookup, access limitations, investigator notes) lives in <code class="k">cases/&lt;CASE-NUMBER&gt;/case.json</code> in the repository.</p>
  `;
  const statusSel = document.getElementById('case-status');
  const siteSel = document.getElementById('case-site');
  const reviewSel = document.getElementById('case-review');
  [...new Set(DATA.cases.map(c=>c.trademark_status))].sort().forEach(s => statusSel.insertAdjacentHTML('beforeend', `<option>${esc(s)}</option>`));
  [...new Set(DATA.cases.map(c=>c.site_code))].sort().forEach(s => siteSel.insertAdjacentHTML('beforeend', `<option>${esc(s)}</option>`));
  [...new Set(DATA.cases.map(c=>c.review_status))].sort().forEach(s => reviewSel.insertAdjacentHTML('beforeend', `<option>${esc(s)}</option>`));

  const tbl = makeTable(document.getElementById('case-table'), {
    columns: [
      {label:'Case #', sortKey:'case_number'},
      {label:'Site Code', sortKey:'site_code'},
      {label:'Variety', sortKey:'variety'},
      {label:'Matched TM', sortKey:'matched_trademark'},
      {label:'TM Status', sortKey:'trademark_status'},
      {label:'Seller', sortKey:'seller_name'},
      {label:'Domain', sortKey:'website_domain'},
      {label:'Seller Location', sortKey:'seller_location'},
      {label:'Website Host', sortKey:'website_host'},
      {label:'First Found', sortKey:'first_date_found'},
      {label:'Last Verified', sortKey:'last_verified'},
      {label:'Match', sortKey:'match_classification'},
      {label:'Review Status', sortKey:'review_status'},
    ],
    rows: DATA.cases,
    getSortValue: (r,k) => (r[k] ?? '').toString().toLowerCase(),
    emptyMessage: DATA.cases.length ? 'No cases match this filter.' : 'No cases yet — none of today’s crawl results have been processed into full case records.',
    rowHtml: r => `<tr>
      <td class="mono">${esc(r.case_number)}</td>
      <td class="mono">${esc(r.site_code)}</td>
      <td>${esc(r.variety)}</td>
      <td>${esc(r.matched_trademark)}</td>
      <td>${statusPill(r.trademark_status, r.trademark_status)}</td>
      <td>${esc(r.seller_name)}</td>
      <td class="mono">${esc(r.website_domain)}</td>
      <td>${esc(r.seller_location)}</td>
      <td>${esc(r.website_host)}</td>
      <td class="mono">${esc(r.first_date_found)}</td>
      <td class="mono">${esc(r.last_verified)}</td>
      <td>${matchPill(r.match_classification)}</td>
      <td>${reviewStatusPill(r.review_status)}</td>
    </tr>`
  });

  function applyFilter(){
    const q = document.getElementById('case-search').value.trim().toLowerCase();
    const filtered = DATA.cases.filter(r => {
      if (statusSel.value && r.trademark_status !== statusSel.value) return false;
      if (siteSel.value && r.site_code !== siteSel.value) return false;
      if (reviewSel.value && r.review_status !== reviewSel.value) return false;
      if (!q) return true;
      return [r.case_number, r.variety, r.matched_trademark, r.seller_name, r.website_domain].some(v => (v??'').toString().toLowerCase().includes(q));
    });
    const n = tbl.render(filtered);
    document.getElementById('case-count').textContent = `${n} of ${DATA.cases.length}`;
  }
  [statusSel, siteSel, reviewSel].forEach(s => s.addEventListener('change', applyFilter));
  document.getElementById('case-search').addEventListener('input', applyFilter);
  applyFilter();
})();

/* ---------- Known Sites ---------- */
(function renderSites(){
  const el = document.getElementById('panel-sites');
  el.innerHTML = `
    <div class="intro">Rose Watch's crawl target roster &mdash; a <strong>closed scope</strong> per user instruction. No sites are discovered or added automatically; the roster only changes when the source spreadsheet is updated.</div>
    <div class="tablewrap"><table>
      <thead><tr><th>Company</th><th>Website(s)</th><th>Platform</th><th>Shipped From</th><th>Prior Reported Varieties (unverified)</th></tr></thead>
      <tbody>
        ${DATA.knownSites.map(s => `<tr>
          <td>${esc(s.company)}</td>
          <td>${s.websites.map(w=>`<div><a href="${esc(w)}" target="_blank" rel="noopener">${esc(w.replace(/^https?:\/\//,''))}</a></div>`).join('')}</td>
          <td>${esc(s.salesPlatforms.join(', '))}</td>
          <td>${esc(s.shippedFrom)}</td>
          <td>${esc(s.priorVarieties.join(', '))}</td>
        </tr>`).join('')}
      </tbody>
    </table></div>
    <p class="small-note">"Prior reported varieties" carries over informal, pre-Rose-Watch research from the source spreadsheet &mdash; background context only, not verified case evidence.</p>
  `;
})();

/* ---------- Needs Review ---------- */
(function renderReview(){
  const el = document.getElementById('panel-review');
  el.innerHTML = `
    <div class="intro"><strong>Trademark chart records needing review</strong> &mdash; ${DATA.needsReviewTrademarks.length} of ${DATA.meta.trademarkCount} records have missing, unclear, duplicate, or conflicting data.</div>
    <div id="review-tm-table"></div>
    <div class="intro" style="margin-top:28px"><strong>Crawl matches held for review</strong> &mdash; matches against To Be Filed, Abandoned, Do Not File, Not Applicable, or Not-in-chart trademarks. Never characterized as confirmed infringement.</div>
    <div id="review-queue-table"></div>
  `;
  makeTable(document.getElementById('review-tm-table'), {
    columns: [
      {label:'Variety', sortKey:'variety'},
      {label:'Breeder', sortKey:'breeder'},
      {label:'Status (as written)', sortKey:'status'},
      {label:'Source Row', sortKey:'sourceRow'},
      {label:'Reason', sortKey:'reason'},
    ],
    rows: DATA.needsReviewTrademarks,
    getSortValue: (r,k) => k==='sourceRow' ? (r[k]||0) : (r[k] ?? '').toString().toLowerCase(),
    emptyMessage: 'No trademark records currently need review.',
    rowHtml: r => `<tr>
      <td>${esc(r.variety) || '<em>(unnamed)</em>'}</td>
      <td>${esc(r.breeder)}</td>
      <td>${esc(r.status)}</td>
      <td class="mono">${esc(r.sourceRow)}</td>
      <td>${esc((r.needsReviewReasons||[]).join('; '))}</td>
    </tr>`
  });
  makeTable(document.getElementById('review-queue-table'), {
    columns: [
      {label:'Variety', sortKey:'variety'},
      {label:'Matched Status', sortKey:'status'},
      {label:'Seller', sortKey:'seller'},
      {label:'Website', sortKey:'website'},
      {label:'Product URL', sortKey:'product_url'},
      {label:'First Found', sortKey:'first_date_found'},
    ],
    rows: DATA.reviewQueue,
    getSortValue: (r,k) => (r[k] ?? '').toString().toLowerCase(),
    emptyMessage: 'No crawl-sourced review-queue entries yet.',
    rowHtml: r => `<tr>
      <td>${esc(r.variety)}</td>
      <td>${esc(r.status)}</td>
      <td>${esc(r.seller)}</td>
      <td class="mono">${esc(r.website)}</td>
      <td>${r.product_url ? `<a href="${esc(r.product_url)}" target="_blank" rel="noopener">link</a>` : ''}</td>
      <td class="mono">${esc(r.first_date_found)}</td>
    </tr>`
  });
})();

/* ---------- Data Sources ---------- */
(function renderSources(){
  const el = document.getElementById('panel-sources');
  el.innerHTML = `
    <div class="intro">Append-only log of source files ingested into Rose Watch. Each new file gets its own dated row; the data above always reflects the most recent successful import.</div>
    <div class="tablewrap"><table>
      <thead><tr><th>Date</th><th>Source</th><th>File</th><th>Records</th><th>Notes</th></tr></thead>
      <tbody>
        ${DATA.dataSources.map(d => `<tr>
          <td class="mono">${esc(d.date)}</td>
          <td>${esc(d.kind)}</td>
          <td class="mono">${esc(d.file)}</td>
          <td class="mono">${esc(d.records)}</td>
          <td>${esc(d.notes)}</td>
        </tr>`).join('')}
      </tbody>
    </table></div>
  `;
})();
</script>
"""


def main():
    data = build_data()
    html = TEMPLATE.replace("__DASHBOARD_DATA__", json.dumps(data, ensure_ascii=False).replace("</script>", "<\\/script>"))
    OUT_FILE.parent.mkdir(exist_ok=True)
    OUT_FILE.write_text(html, encoding="utf-8")
    print(f"Wrote {OUT_FILE} ({len(html):,} bytes)")


if __name__ == "__main__":
    main()
