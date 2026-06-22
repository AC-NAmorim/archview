"""
Generates a self-contained HTML dashboard from repo_health.json.

Run:
    python3 -m scripts.generate_dashboard [--input output/demo/repo_health.json]
"""

import json
import sys
import os


def build_html(repos: list[dict]) -> str:
    data_json = json.dumps(repos)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Platform Health Dashboard</title>
<script
  src="https://cdn.jsdelivr.net/npm/chart.js@4.4.3/dist/chart.umd.min.js"
  integrity="sha384-JUh163oCRItcbPme8pYnROHQMC6fNKTBWtRG3I3I0erJkzNgL7uxKlNwcrcFKeqF"
  crossorigin="anonymous"></script>
<style>
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

html, body {{
  height: 100%;
  font-family: system-ui, -apple-system, sans-serif;
  font-size: 13px;
  background: #0f172a;
  color: #cbd5e1;
}}

/* ── Three-row full-page layout ── */
body {{
  display: flex;
  flex-direction: column;
  height: 100vh;
  overflow: hidden;
}}

/* Row 1: header */
#topbar {{
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 0 20px;
  height: 44px;
  background: #0f172a;
  border-bottom: 1px solid #1e293b;
}}
#topbar h1 {{ font-size: 14px; font-weight: 600; color: #f1f5f9; white-space: nowrap; }}
#topbar .ts {{ font-size: 11px; color: #475569; white-space: nowrap; }}
#topbar .spacer {{ flex: 1; }}
#topbar input, #topbar select {{
  background: #1e293b; border: 1px solid #334155; border-radius: 5px;
  color: #cbd5e1; padding: 4px 8px; font-size: 12px; height: 28px;
}}
#topbar input {{ width: 180px; }}
#topbar input:focus, #topbar select:focus {{ outline: none; border-color: #3b82f6; }}

/* Row 2: summary strip — fixed height */
#summary {{
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 8px 20px;
  height: 80px;
  border-bottom: 1px solid #1e293b;
  overflow: hidden;
}}

.kpi {{
  flex: 0 0 auto;
  display: flex;
  flex-direction: column;
  justify-content: center;
  background: #1e293b;
  border-radius: 6px;
  padding: 6px 14px;
  width: 88px;
  height: 58px;
  cursor: pointer;
  transition: outline 0.1s;
}}
.kpi:hover {{ outline: 1px solid #334155; }}
.kpi .val {{ font-size: 20px; font-weight: 700; line-height: 1; }}
.kpi .lbl {{ font-size: 10px; color: #475569; margin-top: 3px; }}

.sep {{ flex: 0 0 1px; align-self: stretch; background: #1e293b; margin: 4px 0; }}

.gov {{
  flex: 0 0 240px;
  display: flex;
  flex-direction: column;
  justify-content: space-around;
  height: 58px;
}}
.gov-row {{
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
}}
.gov-row .lbl {{ color: #475569; width: 76px; flex-shrink: 0; }}
.gov-row .track {{
  flex: 1;
  height: 4px;
  background: #334155;
  border-radius: 2px;
  overflow: hidden;
}}
.gov-row .fill {{ height: 100%; border-radius: 2px; width: 0%; transition: width .4s; }}
.gov-row .pct {{ color: #94a3b8; width: 30px; text-align: right; flex-shrink: 0; }}

.chart-wrap {{
  flex: 0 0 auto;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 4px;
}}
.chart-wrap .lbl {{ font-size: 10px; color: #475569; text-transform: uppercase; letter-spacing: .04em; }}

.badge {{
  flex: 0 0 auto;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: #1e293b;
  border-radius: 6px;
  padding: 6px 14px;
  height: 58px;
}}
.badge .val {{ font-size: 20px; font-weight: 700; color: #fb923c; line-height: 1; }}
.badge .lbl {{ font-size: 10px; color: #475569; margin-top: 3px; }}

/* Row 3: scrollable table */
#table-wrap {{
  flex: 1 1 0;
  overflow-y: auto;
  padding: 0 20px 16px;
}}

table {{
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
  margin-top: 8px;
}}
thead tr {{
  position: sticky;
  top: 0;
  background: #0f172a;
  border-bottom: 1px solid #1e293b;
  z-index: 1;
}}
th {{
  padding: 7px 6px;
  text-align: left;
  font-size: 10px;
  font-weight: 500;
  color: #475569;
  text-transform: uppercase;
  letter-spacing: .05em;
  cursor: pointer;
  user-select: none;
  white-space: nowrap;
}}
th:hover {{ color: #94a3b8; }}
th.right, td.right {{ text-align: right; }}
th.center, td.center {{ text-align: center; }}
td {{ padding: 6px 6px; border-bottom: 1px solid #1e293b; vertical-align: middle; }}
tr:hover td {{ background: #1e293b; }}

a {{ color: #60a5fa; text-decoration: none; font-weight: 500; }}
a:hover {{ text-decoration: underline; }}

.pill {{
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 10px;
  font-weight: 600;
}}
.pill.dormant    {{ background: #450a0a; color: #fca5a5; }}
.pill.ungoverned {{ background: #431407; color: #fb923c; }}
.pill.needs_work {{ background: #422006; color: #fcd34d; }}
.pill.governed   {{ background: #052e16; color: #86efac; }}

.tag {{
  display: inline-block;
  padding: 0 5px;
  border-radius: 3px;
  font-size: 10px;
  line-height: 18px;
  background: #1e293b;
  color: #475569;
  margin: 1px 2px;
}}

#footer {{
  flex: 0 0 auto;
  font-size: 11px;
  color: #334155;
  padding: 4px 20px;
  border-top: 1px solid #1e293b;
}}
</style>
</head>
<body>

<div id="topbar">
  <h1>Platform Health</h1>
  <span class="ts" id="ts"></span>
  <span class="spacer"></span>
  <input id="q" type="text" placeholder="Filter repos…">
  <select id="fl" style="display:none"></select>
  <select id="fs">
    <option value="">All sources</option>
    <option value="github">GitHub</option>
    <option value="gitlab">GitLab</option>
  </select>
  <button id="clear-btn" onclick="clearFilters()" style="display:none;background:#1e293b;border:1px solid #334155;
    border-radius:5px;color:#94a3b8;padding:4px 10px;font-size:12px;cursor:pointer;height:28px;">
    Clear ×
  </button>
</div>

<div id="summary">
  <div class="kpi" onclick="filterTier('dormant')"    data-tier="dormant"><div class="val" style="color:#fca5a5" id="na">—</div><div class="lbl">Dormant</div></div>
  <div class="kpi" onclick="filterTier('ungoverned')" data-tier="ungoverned"><div class="val" style="color:#fb923c" id="nc">—</div><div class="lbl">Ungoverned</div></div>
  <div class="kpi" onclick="filterTier('needs_work')" data-tier="needs_work"><div class="val" style="color:#fcd34d" id="nw">—</div><div class="lbl">Needs Work</div></div>
  <div class="kpi" onclick="filterTier('governed')"   data-tier="governed"><div class="val" style="color:#86efac" id="nh">—</div><div class="lbl">Governed</div></div>

  <div class="sep"></div>

  <div class="gov">
    <div class="gov-row">
      <span class="lbl">CODEOWNERS</span>
      <div class="track"><div class="fill" id="pb-o" style="background:#3b82f6"></div></div>
      <span class="pct" id="pp-o">—</span>
    </div>
    <div class="gov-row">
      <span class="lbl">README</span>
      <div class="track"><div class="fill" id="pb-r" style="background:#8b5cf6"></div></div>
      <span class="pct" id="pp-r">—</span>
    </div>
    <div class="gov-row">
      <span class="lbl">CI Pipeline</span>
      <div class="track"><div class="fill" id="pb-c" style="background:#06b6d4"></div></div>
      <span class="pct" id="pp-c">—</span>
    </div>
  </div>

  <div class="sep"></div>

  <div class="chart-wrap">
    <span class="lbl">Tiers</span>
    <canvas id="donut" width="64" height="64"></canvas>
  </div>

  <div class="chart-wrap" style="flex: 0 0 160px;">
    <span class="lbl">Score spread</span>
    <canvas id="hist" width="160" height="52"></canvas>
  </div>

  <div class="sep"></div>

  <div class="badge" onclick="jumpToCVE()" style="cursor:pointer" title="Jump to CVE panel">
    <div class="val" id="nalerts">—</div>
    <div class="lbl">Open CVEs</div>
  </div>
</div>

<div id="table-wrap">
  <table>
    <thead>
      <tr>
        <th onclick="sort('n')">Repo</th>
        <th onclick="sort('s')">Source</th>
        <th onclick="sort('l')">Lang</th>
        <th onclick="sort('d')">Last Commit</th>
        <th class="center" onclick="sort('t')">Tier</th>
        <th class="right" onclick="sort('v')">Score</th>
        <th>Tags</th>
      </tr>
    </thead>
    <tbody id="tbody"></tbody>
  </table>

  <!-- CVE Panel -->
  <div id="cve-panel" style="margin-top:24px;display:none;">
    <div style="display:flex;align-items:center;gap:12px;margin-bottom:8px;">
      <span style="font-size:12px;font-weight:600;color:#f1f5f9;">Security Alerts</span>
      <span id="cve-count" style="font-size:11px;color:#475569;"></span>
      <div style="flex:1"></div>
      <select id="cve-sev" onchange="renderCVE()"
        style="background:#1e293b;border:1px solid #334155;border-radius:5px;color:#cbd5e1;padding:3px 8px;font-size:11px;">
        <option value="">All severities</option>
        <option value="CRITICAL">Critical</option>
        <option value="HIGH">High</option>
        <option value="MODERATE">Moderate</option>
        <option value="LOW">Low</option>
      </select>
    </div>
    <table style="width:100%;border-collapse:collapse;font-size:12px;">
      <thead>
        <tr style="color:#475569;font-size:10px;text-transform:uppercase;letter-spacing:.05em;border-bottom:1px solid #1e293b;">
          <th style="text-align:left;padding:6px;font-weight:500;cursor:pointer" onclick="sortCVE('repo')">Repo</th>
          <th style="text-align:left;padding:6px;font-weight:500;cursor:pointer" onclick="sortCVE('pkg')">Package</th>
          <th style="text-align:left;padding:6px;font-weight:500;">Ecosystem</th>
          <th style="text-align:center;padding:6px;font-weight:500;cursor:pointer" onclick="sortCVE('sev')">Severity</th>
          <th style="text-align:right;padding:6px;font-weight:500;cursor:pointer" onclick="sortCVE('cvss')">CVSS</th>
          <th style="text-align:left;padding:6px;font-weight:500;">CVE ID</th>
          <th style="text-align:left;padding:6px;font-weight:500;">Summary</th>
        </tr>
      </thead>
      <tbody id="cve-tbody"></tbody>
    </table>
  </div>
</div>

<div id="footer" id="foot"></div>

<script>
const D = {data_json};
let sk = 'v', sd = 1;

// ── Filter state ──────────────────────────────────────────────
const F = {{ q:'', tier:'', lang:'', source:'', tag:'' }};

const TL = {{dormant:'Dormant',ungoverned:'Ungoverned',needs_work:'Needs Work',governed:'Governed'}};
const SC = s => s >= 70 ? '#86efac' : s >= 40 ? '#fcd34d' : '#fb923c';

function ago(iso) {{
  if (!iso) return '—';
  const d = Math.floor((Date.now() - new Date(iso)) / 86400000);
  return d === 0 ? 'today' : d < 30 ? d+'d' : d < 365 ? Math.floor(d/30)+'mo' : Math.floor(d/365)+'yr';
}}

// ── Apply all filters + sort ──────────────────────────────────
function rows() {{
  const key = {{n:'full_name',s:'source',l:'language',d:'last_commit_at',t:'tier',v:'total'}};
  return D
    .filter(r =>
      (!F.q      || r.full_name.toLowerCase().includes(F.q)) &&
      (!F.tier   || r.health?.tier === F.tier) &&
      (!F.lang   || r.language === F.lang) &&
      (!F.source || r.source === F.source) &&
      (!F.tag    || (r.health?.tags||[]).includes(F.tag)))
    .sort((a,b) => {{
      const k = key[sk];
      const av = k==='total'?(a.health?.total??0):k==='tier'?(a.health?.tier??''):(a[k]??'');
      const bv = k==='total'?(b.health?.total??0):k==='tier'?(b.health?.tier??''):(b[k]??'');
      return av<bv ? -sd : av>bv ? sd : 0;
    }});
}}

// ── Sync controls → state, re-render ─────────────────────────
function syncAndRender() {{
  F.q      = document.getElementById('q').value.toLowerCase();
  F.source = document.getElementById('fs').value;
  F.lang   = document.getElementById('fl').value;
  updateClearBtn();
  render();
}}

function filterTier(t) {{
  F.tier = F.tier === t ? '' : t;          // toggle on second click
  highlightKpi();
  updateClearBtn();
  render();
}}

function filterTag(t) {{
  F.tag = F.tag === t ? '' : t;            // toggle
  updateClearBtn();
  render();
}}

function clearFilters() {{
  Object.keys(F).forEach(k => F[k] = '');
  document.getElementById('q').value  = '';
  document.getElementById('fs').value = '';
  document.getElementById('fl').value = '';
  highlightKpi();
  updateClearBtn();
  render();
}}

function highlightKpi() {{
  document.querySelectorAll('.kpi').forEach(el => {{
    const active = F.tier && el.dataset.tier === F.tier;
    el.style.outline = active ? '2px solid #60a5fa' : 'none';
    el.style.cursor  = 'pointer';
  }});
}}

function updateClearBtn() {{
  const active = Object.values(F).some(v => v);
  document.getElementById('clear-btn').style.display = active ? 'block' : 'none';
  // show active tag badge in topbar
  let badge = document.getElementById('tag-badge');
  if (F.tag) {{
    if (!badge) {{
      badge = document.createElement('span');
      badge.id = 'tag-badge';
      badge.style.cssText = 'background:#1e3a5f;color:#60a5fa;border-radius:4px;padding:2px 8px;font-size:11px;cursor:pointer';
      badge.onclick = () => filterTag(F.tag);
      document.getElementById('clear-btn').before(badge);
    }}
    badge.textContent = 'tag: ' + F.tag + ' ×';
  }} else if (badge) {{
    badge.remove();
  }}
}}

// ── Render table ──────────────────────────────────────────────
function render() {{
  const data = rows();
  document.getElementById('footer').textContent = data.length + ' of ' + D.length + ' repos';
  document.getElementById('tbody').innerHTML = data.map(r => {{
    const h = r.health || {{}};
    const sc = typeof h.total === 'number';
    const tags = (h.tags||[]).map(t => {{
      const active = F.tag === t;
      return `<span class="tag" onclick="filterTag('${{t}}')" style="cursor:pointer;${{active?'background:#1e3a5f;color:#60a5fa;':''}} ">${{t}}</span>`;
    }}).join('');
    const wf = r.workflow;
    const deployBadge = wf?.has_deploy
      ? `<span class="tag" title="${{(wf.deploy_workflows||[]).join(', ')||'deploy workflow'}}"
               style="background:#052e16;color:#86efac;border:1px solid #238636;cursor:default">⚡ deployed</span>`
      : '';
    const wfDate = wf?.last_run_at
      ? `<span style="color:#475569;font-size:10px" title="Last CI run: ${{wf.last_run_at.slice(0,10)}} (${{wf.last_run_status||'?'}})">CI ${{ago(wf.last_run_at)}}</span>`
      : '';
    return `<tr>
      <td><a href="${{r.url}}" target="_blank">${{r.full_name}}</a></td>
      <td style="color:#475569">${{r.source}}</td>
      <td style="color:#475569">${{r.language||'—'}}</td>
      <td style="color:#475569">${{ago(r.last_commit_at)}} ${{wfDate}}</td>
      <td class="center"><span class="pill ${{h.tier}}" onclick="filterTier('${{h.tier}}')" style="cursor:pointer">${{TL[h.tier]||'—'}}</span></td>
      <td class="right">${{sc?`<span style="color:${{SC(h.total)}};font-weight:600">${{h.total}}</span>`:'—'}}</td>
      <td>${{deployBadge}} ${{tags}}</td>
    </tr>`;
  }}).join('');
}}

// ── Build language dropdown from real data ────────────────────
function buildLangFilter() {{
  const langs = [...new Set(D.map(r => r.language).filter(Boolean))].sort();
  const el = document.getElementById('fl');
  el.innerHTML = '<option value="">All langs</option>' +
    langs.map(l => `<option value="${{l}}">${{l}}</option>`).join('');
  if (langs.length > 1) el.style.display = '';
}}

// ── Summary strip (static totals, not affected by filters) ────
function summary() {{
  const c = {{dormant:0,ungoverned:0,needs_work:0,governed:0}};
  let o=0,rm=0,ci=0,alerts=0;
  const bk = [0,0,0,0,0];
  D.forEach(r => {{
    c[r.health?.tier]++;
    const own = r.health?.breakdown?.ownership ?? 0;
    if (own>=20) o++;
    if (own>=5)  rm++;
    if (own>=10) ci++;
    if ((r.health?.tags||[]).some(t=>t.includes('cve'))) alerts++;
    bk[Math.min(4,Math.floor((r.health?.total??0)/20))]++;
  }});
  document.getElementById('na').textContent      = c.dormant;
  document.getElementById('nc').textContent      = c.ungoverned;
  document.getElementById('nw').textContent      = c.needs_work;
  document.getElementById('nh').textContent      = c.governed;
  document.getElementById('nalerts').textContent = alerts;

  const n = D.length||1;
  [['pb-o','pp-o',o],['pb-r','pp-r',rm],['pb-c','pp-c',ci]].forEach(([b,p,v]) => {{
    const pct = Math.round(v/n*100);
    document.getElementById(b).style.width = pct+'%';
    document.getElementById(p).textContent = pct+'%';
  }});

  new Chart(document.getElementById('donut'), {{
    type:'doughnut',
    data:{{ datasets:[{{ data:[c.dormant,c.ungoverned,c.needs_work,c.governed],
      backgroundColor:['#7f1d1d','#7c2d12','#78350f','#14532d'],
      borderColor:['#fca5a5','#fb923c','#fcd34d','#86efac'], borderWidth:1.5 }}] }},
    options:{{ cutout:'65%', plugins:{{legend:{{display:false}}}}, animation:false, responsive:false }}
  }});

  new Chart(document.getElementById('hist'), {{
    type:'bar',
    data:{{ labels:['0-19','20-39','40-59','60-79','80+'],
      datasets:[{{ data:bk, backgroundColor:['#7f1d1d','#7c2d12','#78350f','#14532d','#052e16'], borderRadius:2 }}] }},
    options:{{ responsive:false, maintainAspectRatio:false, animation:false,
      plugins:{{legend:{{display:false}}}},
      scales:{{
        x:{{ticks:{{color:'#334155',font:{{size:9}}}},grid:{{display:false}}}},
        y:{{ticks:{{color:'#334155',font:{{size:9}},maxTicksLimit:3}},grid:{{color:'#1e293b'}}}}
      }}
    }}
  }});
}}

function sort(k) {{ sd = sk===k ? -sd : 1; sk=k; render(); }}

// ── CVE panel ─────────────────────────────────────────────────
const SEV_ORDER = {{CRITICAL:0,HIGH:1,MODERATE:2,LOW:3,UNKNOWN:4}};
const SEV_COLOR = {{CRITICAL:'#fca5a5',HIGH:'#fb923c',MODERATE:'#fcd34d',LOW:'#86efac',UNKNOWN:'#94a3b8'}};
const SEV_BG    = {{CRITICAL:'#450a0a',HIGH:'#431407',MODERATE:'#422006',LOW:'#052e16',UNKNOWN:'#1e293b'}};

// Flatten all CVEs from raw data
const ALL_CVES = D.flatMap(r =>
  (r.cve_alerts||[]).map(c => ({{...c, repo: r.full_name, repo_url: r.url}}))
);

let cveSk = 'sev', cveSd = 1;

function cveRows() {{
  const sev = document.getElementById('cve-sev').value;
  return ALL_CVES
    .filter(c => !sev || c.severity === sev)
    .sort((a,b) => {{
      let av, bv;
      if (cveSk==='sev')  {{ av=SEV_ORDER[a.severity]??9; bv=SEV_ORDER[b.severity]??9; }}
      else if (cveSk==='cvss') {{ av=a.cvss_score??-1; bv=b.cvss_score??-1; }}
      else if (cveSk==='repo') {{ av=a.repo; bv=b.repo; }}
      else {{ av=a.package; bv=b.package; }}
      return av<bv ? -cveSd : av>bv ? cveSd : 0;
    }});
}}

function renderCVE() {{
  const data = cveRows();
  document.getElementById('cve-count').textContent =
    data.length + ' alert' + (data.length!==1?'s':'') + ' across ' +
    new Set(data.map(c=>c.repo)).size + ' repos';
  document.getElementById('cve-tbody').innerHTML = data.map(c => `
    <tr style="border-bottom:1px solid #1e293b;">
      <td style="padding:5px 6px;">
        <a href="${{c.repo_url}}/security/dependabot" target="_blank"
           style="color:#60a5fa;text-decoration:none;font-size:11px;">${{c.repo}}</a>
      </td>
      <td style="padding:5px 6px;font-weight:500;">${{c.package}}</td>
      <td style="padding:5px 6px;color:#475569;font-size:11px;">${{c.ecosystem}}</td>
      <td style="padding:5px 6px;text-align:center;">
        <span style="padding:2px 7px;border-radius:3px;font-size:10px;font-weight:700;
          background:${{SEV_BG[c.severity]}};color:${{SEV_COLOR[c.severity]}};">${{c.severity}}</span>
      </td>
      <td style="padding:5px 6px;text-align:right;font-weight:600;color:${{SEV_COLOR[c.severity]}};">
        ${{c.cvss_score != null ? c.cvss_score.toFixed(1) : '—'}}
      </td>
      <td style="padding:5px 6px;font-size:11px;color:#94a3b8;">
        ${{c.cve_id
          ? `<a href="https://nvd.nist.gov/vuln/detail/${{c.cve_id}}" target="_blank"
               style="color:#94a3b8;text-decoration:none;">${{c.cve_id}}</a>`
          : '—'}}
      </td>
      <td style="padding:5px 6px;color:#94a3b8;font-size:11px;max-width:340px;
                 white-space:nowrap;overflow:hidden;text-overflow:ellipsis;"
          title="${{c.summary}}">${{c.summary}}</td>
    </tr>`).join('');
}}

function sortCVE(k) {{ cveSd = cveSk===k ? -cveSd : 1; cveSk=k; renderCVE(); }}

function jumpToCVE() {{
  document.getElementById('cve-panel').scrollIntoView({{behavior:'smooth'}});
}}

function initCVE() {{
  const panel = document.getElementById('cve-panel');
  if (ALL_CVES.length > 0) {{
    panel.style.display = 'block';
    renderCVE();
  }}
}}

document.getElementById('ts').textContent = new Date().toLocaleString(undefined,{{dateStyle:'medium',timeStyle:'short'}});
document.getElementById('q').addEventListener('input', syncAndRender);
document.getElementById('fs').addEventListener('change', syncAndRender);
document.getElementById('fl').addEventListener('change', syncAndRender);

buildLangFilter();
summary();
render();
initCVE();
</script>
</body>
</html>"""


def main():
    input_path = sys.argv[2] if len(sys.argv) > 2 and sys.argv[1] == "--input" else "output/demo/repo_health.json"
    if not os.path.exists(input_path):
        print(f"ERROR: {input_path} not found. Run the demo first:\n  python3 -m scripts.demo")
        sys.exit(1)

    with open(input_path) as f:
        repos = json.load(f)

    out_dir = os.path.dirname(input_path)
    out_path = os.path.join(out_dir, "dashboard.html")
    with open(out_path, "w") as f:
        f.write(build_html(repos))

    print(f"Dashboard → {out_path}")
    return out_path


if __name__ == "__main__":
    main()
