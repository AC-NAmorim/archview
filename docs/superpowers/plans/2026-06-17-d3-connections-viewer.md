# D3 Connections Viewer Extension — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend `write_viewer()` in `scripts/pilot.py` to add a "Connections" tab alongside the existing domain map. The tab renders a D3 v7 force-directed graph of architectural relationships extracted from `architecture-graph.json`, supporting domain-level overview and per-domain service-level drill-down.

**Architecture:** All new code is added inside the single Python f-string (`html`) within `write_viewer()`. No new files are created — the viewer remains fully self-contained as `architecture-overview/index.html`. The graph data is already embedded as the `G` JS constant; new D3 code reads the same object.

**Tech Stack:** Python 3 f-string with `{{`/`}}` brace-escaping for literal JS; D3 v7 (CDN via jsDelivr with SRI hash); SVG-based force simulation; vanilla JS for tab switching, state management, and SVG tooltip.

---

## Pre-implementation step: fetch D3 SRI hash

- [ ] Run the following command and capture the hash string for use in Task 1:
  ```bash
  curl -s https://cdn.jsdelivr.net/npm/d3@7/dist/d3.min.js | openssl dgst -sha384 -binary | openssl base64 -A
  ```
  The output will look like `abc123...==`. Use it as the `integrity` attribute value prefixed with `sha384-`.

---

## Task 1 — Add CSS, toggle buttons, and HTML shell

**Files:**
- Modify: `scripts/pilot.py` — `write_viewer()` function (CSS block, topbar HTML, body HTML)

### 1a. CSS additions

Insert immediately before `</style>` in the html f-string:

```css
/* ── View toggle (Map / Connections) ─────────────────────────── */
.view-toggle {{
  display:flex; align-items:center; gap:2px;
  background:var(--bg-base); border:1px solid var(--bd-default);
  border-radius:6px; padding:2px; flex-shrink:0;
}}
.vt-btn {{
  font-size:11px; font-weight:600; padding:3px 10px; border-radius:4px;
  cursor:pointer; border:none; background:transparent;
  color:var(--tx-second); transition:background var(--t-fast), color var(--t-fast);
}}
.vt-btn.active {{
  background:var(--bg-elevated); color:var(--tx-primary);
}}

/* ── Connections view container ──────────────────────────────── */
#connections-view {{
  display:none; flex:1 1 0; flex-direction:column; overflow:hidden; min-height:0;
}}
#connections-view.visible {{
  display:flex;
}}
#conn-toolbar {{
  flex:0 0 auto; padding:8px 16px; border-bottom:1px solid var(--bd-subtle);
  display:flex; align-items:center; gap:10px; background:var(--bg-surface);
  font-size:11px; color:var(--tx-second);
}}
#conn-back {{
  display:none; cursor:pointer; padding:3px 8px; border-radius:5px;
  border:1px solid var(--bd-default); background:var(--bg-elevated);
  color:var(--tx-primary); font-size:11px;
}}
#conn-back:hover {{ background:var(--bd-subtle) }}
#conn-back.visible {{ display:inline-block }}
#conn-legend {{ display:flex; gap:12px; align-items:center; margin-left:auto; }}
.cl-item {{ display:flex; align-items:center; gap:5px; font-size:10px; color:var(--tx-muted); }}
.cl-line {{ width:24px; height:2px; flex-shrink:0; }}
.cl-line.depends {{ background:#58a6ff; }}
.cl-line.calls   {{ background:#d97706; }}
#conn-svg-wrap {{ flex:1 1 0; overflow:hidden; position:relative; }}
#conn-svg {{ width:100%; height:100%; display:block; }}
#conn-tooltip {{
  position:absolute; pointer-events:none;
  background:var(--bg-elevated); border:1px solid var(--bd-default);
  border-radius:6px; padding:6px 10px; font-size:11px; color:var(--tx-primary);
  max-width:260px; white-space:pre-wrap; display:none; z-index:10;
  box-shadow:0 4px 12px #00000040;
}}
#conn-empty {{
  position:absolute; inset:0; display:flex; align-items:center;
  justify-content:center; flex-direction:column; gap:8px;
  color:var(--tx-muted); font-size:13px; text-align:center; padding:40px;
  pointer-events:none;
}}
```

### 1b. Topbar toggle buttons

After `<span class="logo">TVaaS Platform</span>` add:

```html
  <div class="view-toggle">
    <button class="vt-btn active" id="btn-map"         onclick="switchView('map')">Map</button>
    <button class="vt-btn"        id="btn-connections" onclick="switchView('connections')">Connections</button>
  </div>
```

### 1c. Connections view HTML block

Add immediately after `</div><!-- /body -->` and before `<script>`:

```html
<!-- Connections view -->
<div id="connections-view">
  <div id="conn-toolbar">
    <button id="conn-back" onclick="connBack()">← Domain overview</button>
    <span id="conn-title">Domain dependency map</span>
    <div id="conn-legend">
      <div class="cl-item">
        <div class="cl-line depends" style="border-top:2px dashed #58a6ff;background:none"></div>
        depends_on
      </div>
      <div class="cl-item">
        <div class="cl-line calls"></div>
        calls
      </div>
    </div>
  </div>
  <div id="conn-svg-wrap">
    <svg id="conn-svg"></svg>
    <div id="conn-tooltip"></div>
    <div id="conn-empty" style="display:none">
      <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2">
        <circle cx="12" cy="12" r="10"/><path d="M12 8v4M12 16h.01"/>
      </svg>
      <p>No dependency relationships extracted yet.<br>Run <code>scripts/extract_relationships.py</code> first.</p>
    </div>
  </div>
</div>
```

### 1d. D3 script tag in `<head>`

Add after `<meta charset="UTF-8">` — substitute `HASH_HERE` with the actual hash from the pre-implementation step:

```html
<script src="https://cdn.jsdelivr.net/npm/d3@7/dist/d3.min.js"
        integrity="sha384-HASH_HERE"
        crossorigin="anonymous"></script>
```

- [ ] Run: `python3 -c "import json; from scripts.pilot import build_graph, write_viewer, CACHE; import pathlib; g=json.loads(pathlib.Path('architecture-overview/architecture-graph.json').read_text()); write_viewer(g)"`
- [ ] Open `architecture-overview/index.html` in browser
- [ ] Verify: Map / Connections toggle buttons appear in topbar
- [ ] Verify: clicking "Connections" shows empty area (no crash), "Map" returns to existing view
- [ ] Verify: all existing Map functionality is unaffected
- [ ] Commit: `git add scripts/pilot.py && git commit -m "feat: add connections view HTML shell and CSS"`

---

## Task 2 — Add `switchView()` and D3 data-preparation helpers

**Files:**
- Modify: `scripts/pilot.py` — inside `<script>` block of the f-string, after `init(); renderBreadcrumb();`

```javascript
/* ══════════════════════════════════════════════════════════════
   CONNECTIONS VIEW
   ══════════════════════════════════════════════════════════════ */

/* ── View switch ───────────────────────────────────────────── */
let _currentView = 'map';

function switchView(view) {{
  _currentView = view;
  const mapEl  = document.getElementById('body');
  const connEl = document.getElementById('connections-view');
  document.getElementById('btn-map').classList.toggle('active', view === 'map');
  document.getElementById('btn-connections').classList.toggle('active', view === 'connections');
  if (view === 'map') {{
    if (_simulation) _simulation.stop();
    mapEl.style.display  = 'flex';
    connEl.classList.remove('visible');
  }} else {{
    mapEl.style.display  = 'none';
    connEl.classList.add('visible');
    initConnections();
  }}
}}

/* ── Data preparation ──────────────────────────────────────── */
const nodeById = {{}};
G.nodes.forEach(n => nodeById[n.id] = n);

const relEdges = G.edges.filter(e => e.type === 'depends_on' || e.type === 'calls');

function buildDomainGraph() {{
  const domainNodes = G.nodes.filter(n => n.type === 'domain');
  const repoDomain = {{}};
  G.nodes.filter(n => n.type === 'repo').forEach(r => repoDomain[r.id] = r.domain);

  const edgeMap = {{}};
  relEdges.forEach(e => {{
    const sd = repoDomain[e.source];
    const td = repoDomain[e.target];
    if (!sd || !td || sd === td) return;
    const key = sd + '||' + td + '||' + e.type;
    if (!edgeMap[key]) edgeMap[key] = {{ source: sd, target: td, type: e.type, weight: 0 }};
    edgeMap[key].weight++;
  }});

  const repoCounts = {{}};
  G.nodes.filter(n => n.type === 'repo').forEach(r => {{
    repoCounts[r.domain] = (repoCounts[r.domain] || 0) + 1;
  }});

  const nodes = domainNodes.map(d => ({{
    id: d.id, name: d.name, repoCount: repoCounts[d.name] || 0,
  }}));
  return {{ nodes, edges: Object.values(edgeMap) }};
}}

function buildServiceGraph(domainName) {{
  const domainRepos   = G.nodes.filter(n => n.type === 'repo' && n.domain === domainName);
  const domainRepoIds = new Set(domainRepos.map(r => r.id));

  const neighbourIds = new Set();
  relEdges.forEach(e => {{
    if (domainRepoIds.has(e.source) && !domainRepoIds.has(e.target)) neighbourIds.add(e.target);
    if (domainRepoIds.has(e.target) && !domainRepoIds.has(e.source)) neighbourIds.add(e.source);
  }});

  const nodeIds = new Set([...domainRepoIds, ...neighbourIds]);
  const nodes = [...nodeIds].map(id => {{
    const n = nodeById[id];
    return {{
      id, name: n ? n.name.split('/').pop() : id, fullName: n ? n.name : id,
      url: n ? n.url : '', domain: n ? n.domain : '',
      health_tier: n ? n.health_tier : '', health_score: n ? (n.health_score || 0) : 0,
      confidence: n ? n.confidence : '', isNeighbour: !domainRepoIds.has(id),
    }};
  }});

  const edges = relEdges.filter(e => nodeIds.has(e.source) && nodeIds.has(e.target));
  return {{ nodes, edges, domainName }};
}}
```

- [ ] Reload `index.html`, open browser DevTools console
- [ ] Run `buildDomainGraph()` — confirm returns `{{ nodes: [...], edges: [...] }}` without errors
- [ ] Run `relEdges.length` — confirm 0 (expected until extraction script runs)
- [ ] Commit: `git add scripts/pilot.py && git commit -m "feat: add connections data-prep helpers"`

---

## Task 3 — Tooltip helpers

**Files:**
- Modify: `scripts/pilot.py` — inside `<script>` block, before `initConnections()`

```javascript
/* ── Tooltip helpers ───────────────────────────────────────── */
function showTooltip(event, text) {{
  const t = document.getElementById('conn-tooltip');
  t.textContent = text;
  t.style.display = 'block';
  positionTooltip(event);
}}

function hideTooltip() {{
  document.getElementById('conn-tooltip').style.display = 'none';
}}

function positionTooltip(event) {{
  const t    = document.getElementById('conn-tooltip');
  const wrap = document.getElementById('conn-svg-wrap');
  const rect = wrap.getBoundingClientRect();
  let x = event.clientX - rect.left + 12;
  let y = event.clientY - rect.top  + 12;
  if (x + 280 > rect.width)  x = event.clientX - rect.left - 280 - 4;
  if (y + 60  > rect.height) y = event.clientY - rect.top  - 60  - 4;
  t.style.left = x + 'px';
  t.style.top  = y + 'px';
}}

document.getElementById('conn-svg').addEventListener('mousemove', event => {{
  const t = document.getElementById('conn-tooltip');
  if (t.style.display === 'block') positionTooltip(event);
}});
```

- [ ] Commit: `git add scripts/pilot.py && git commit -m "feat: add connections tooltip helpers"`

---

## Task 4 — Domain-level D3 force simulation (`renderDomainGraph`)

**Files:**
- Modify: `scripts/pilot.py` — inside `<script>` block

```javascript
let _connState  = {{ level: 'domain', domain: null }};
let _simulation = null;

const TIER_COLOR = {{
  governed:   '#3fb950',
  ungoverned: '#d29922',
  dormant:    '#484f58',
}};

function tierColor(tier)   {{ return TIER_COLOR[tier] || '#8b949e'; }}
function confStroke(conf)  {{ return conf === 'high' ? 2.5 : conf === 'medium' ? 1.5 : 0.8; }}

function initConnections() {{
  if (_connState.level === 'domain') renderDomainGraph();
  else                               renderServiceGraph(_connState.domain);
}}

function connBack() {{
  _connState = {{ level: 'domain', domain: null }};
  document.getElementById('conn-back').classList.remove('visible');
  document.getElementById('conn-title').textContent = 'Domain dependency map';
  renderDomainGraph();
}}

function renderDomainGraph() {{
  if (_simulation) _simulation.stop();
  const wrap = document.getElementById('conn-svg-wrap');
  const svg  = document.getElementById('conn-svg');
  const W = wrap.clientWidth  || 900;
  const H = wrap.clientHeight || 600;
  svg.innerHTML = '';

  const {{ nodes, edges }} = buildDomainGraph();
  const emptyEl = document.getElementById('conn-empty');
  if (relEdges.length === 0) {{ emptyEl.style.display = 'flex'; return; }}
  emptyEl.style.display = 'none';

  const ns = 'http://www.w3.org/2000/svg';
  const defs   = document.createElementNS(ns, 'defs');
  const marker = document.createElementNS(ns, 'marker');
  marker.setAttribute('id', 'arrow-calls'); marker.setAttribute('viewBox', '0 -5 10 10');
  marker.setAttribute('refX', '22'); marker.setAttribute('refY', '0');
  marker.setAttribute('markerWidth', '6'); marker.setAttribute('markerHeight', '6');
  marker.setAttribute('orient', 'auto');
  const mp = document.createElementNS(ns, 'path');
  mp.setAttribute('d', 'M0,-5L10,0L0,5'); mp.setAttribute('fill', '#d97706');
  marker.appendChild(mp); defs.appendChild(marker); svg.appendChild(defs);

  const d3svg  = d3.select(svg).attr('width', W).attr('height', H);
  const g      = d3svg.append('g');
  d3svg.call(d3.zoom().scaleExtent([0.3, 3]).on('zoom', e => g.attr('transform', e.transform)));

  const maxCount = Math.max(...nodes.map(n => n.repoCount), 1);
  const rScale   = d3.scaleSqrt().domain([0, maxCount]).range([18, 50]);

  const simNodes = nodes.map(n => ({{ ...n }}));
  const simEdges = edges.map(e => ({{
    ...e,
    source: simNodes.find(n => n.name === e.source) || e.source,
    target: simNodes.find(n => n.name === e.target) || e.target,
  }}));

  _simulation = d3.forceSimulation(simNodes)
    .force('link',    d3.forceLink(simEdges).id(n => n.name).distance(160).strength(0.4))
    .force('charge',  d3.forceManyBody().strength(-400))
    .force('center',  d3.forceCenter(W / 2, H / 2))
    .force('collide', d3.forceCollide(n => rScale(n.repoCount) + 12));

  const link = g.append('g').selectAll('line').data(simEdges).join('line')
    .attr('stroke', e => e.type === 'depends_on' ? '#58a6ff' : '#d97706')
    .attr('stroke-width', e => Math.max(1, Math.log1p(e.weight) * 2))
    .attr('stroke-dasharray', e => e.type === 'depends_on' ? '6 3' : null)
    .attr('marker-end', e => e.type === 'calls' ? 'url(#arrow-calls)' : null)
    .attr('opacity', 0.7)
    .on('mouseenter', (event, e) => showTooltip(event, `${{e.type}} x${{e.weight}}`))
    .on('mouseleave', hideTooltip);

  const node = g.append('g').selectAll('g').data(simNodes).join('g')
    .attr('cursor', 'pointer')
    .on('click', (event, d) => {{
      _connState = {{ level: 'service', domain: d.name }};
      document.getElementById('conn-back').classList.add('visible');
      document.getElementById('conn-title').textContent = d.name;
      renderServiceGraph(d.name);
    }});

  node.call(d3.drag()
    .on('start', (event, d) => {{ if (!event.active) _simulation.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; }})
    .on('drag',  (event, d) => {{ d.fx = event.x; d.fy = event.y; }})
    .on('end',   (event, d) => {{ if (!event.active) _simulation.alphaTarget(0); d.fx = null; d.fy = null; }}));

  node.append('circle')
    .attr('r', d => rScale(d.repoCount))
    .attr('fill', '#1c2128').attr('stroke', '#58a6ff').attr('stroke-width', 1.5);

  node.append('text').attr('text-anchor', 'middle').attr('dy', '0.35em')
    .attr('fill', '#e6edf3')
    .attr('font-size', d => Math.min(12, rScale(d.repoCount) * 0.4) + 'px')
    .attr('pointer-events', 'none')
    .text(d => d.name.replace(/^\d+\.\s*/, ''));

  node.append('text').attr('text-anchor', 'middle')
    .attr('dy', d => rScale(d.repoCount) + 14)
    .attr('fill', '#8b949e').attr('font-size', '10px').attr('pointer-events', 'none')
    .text(d => d.repoCount ? d.repoCount + ' repos' : '');

  _simulation.on('tick', () => {{
    link.attr('x1', e => e.source.x).attr('y1', e => e.source.y)
        .attr('x2', e => e.target.x).attr('y2', e => e.target.y);
    node.attr('transform', d => `translate(${{d.x}},${{d.y}})`);
  }});
}}
```

- [ ] After manually adding one test edge to `architecture-graph.json` crossing two domains, regenerate viewer and reload
- [ ] Verify: domain nodes appear as circles, sized by repo count
- [ ] Verify: test edge appears with correct colour/dash style
- [ ] Verify: clicking a domain node transitions to service level (empty until Task 5)
- [ ] Commit: `git add scripts/pilot.py && git commit -m "feat: add domain-level D3 force graph"`

---

## Task 5 — Service-level D3 force simulation (`renderServiceGraph`)

**Files:**
- Modify: `scripts/pilot.py` — inside `<script>` block, after `renderDomainGraph`

```javascript
function renderServiceGraph(domainName) {{
  if (_simulation) _simulation.stop();
  const wrap = document.getElementById('conn-svg-wrap');
  const svg  = document.getElementById('conn-svg');
  const W = wrap.clientWidth  || 900;
  const H = wrap.clientHeight || 600;
  svg.innerHTML = '';
  document.getElementById('conn-empty').style.display = 'none';

  const {{ nodes, edges }} = buildServiceGraph(domainName);
  if (nodes.length === 0) {{ document.getElementById('conn-empty').style.display = 'flex'; return; }}

  const ns = 'http://www.w3.org/2000/svg';
  const defs = document.createElementNS(ns, 'defs');
  const marker = document.createElementNS(ns, 'marker');
  marker.setAttribute('id', 'arrow-svc'); marker.setAttribute('viewBox', '0 -5 10 10');
  marker.setAttribute('refX', '18'); marker.setAttribute('refY', '0');
  marker.setAttribute('markerWidth', '6'); marker.setAttribute('markerHeight', '6');
  marker.setAttribute('orient', 'auto');
  const mp = document.createElementNS(ns, 'path');
  mp.setAttribute('d', 'M0,-5L10,0L0,5'); mp.setAttribute('fill', '#d97706');
  marker.appendChild(mp); defs.appendChild(marker); svg.appendChild(defs);

  const d3svg = d3.select(svg).attr('width', W).attr('height', H);
  const g     = d3svg.append('g');
  d3svg.call(d3.zoom().scaleExtent([0.2, 4]).on('zoom', e => g.attr('transform', e.transform)));

  const maxScore = Math.max(...nodes.map(n => n.health_score || 0), 1);
  const rScale   = d3.scaleSqrt().domain([0, maxScore]).range([10, 28]);

  const simNodes = nodes.map(n => ({{ ...n }}));
  const idToSim  = {{}};
  simNodes.forEach(n => idToSim[n.id] = n);

  const simEdges = edges
    .filter(e => idToSim[e.source] && idToSim[e.target])
    .map(e => ({{ ...e, source: idToSim[e.source], target: idToSim[e.target] }}));

  _simulation = d3.forceSimulation(simNodes)
    .force('link',    d3.forceLink(simEdges).id(n => n.id).distance(100).strength(0.5))
    .force('charge',  d3.forceManyBody().strength(-250))
    .force('center',  d3.forceCenter(W / 2, H / 2))
    .force('collide', d3.forceCollide(n => rScale(n.health_score || 0) + 8));

  const link = g.append('g').selectAll('line').data(simEdges).join('line')
    .attr('stroke', e => e.type === 'depends_on' ? '#58a6ff' : '#d97706')
    .attr('stroke-width', 1.5)
    .attr('stroke-dasharray', e => e.type === 'depends_on' ? '5 3' : null)
    .attr('marker-end', e => e.type === 'calls' ? 'url(#arrow-svc)' : null)
    .attr('opacity', 0.6)
    .on('mouseenter', (event, e) => showTooltip(event, e.detail || e.type))
    .on('mouseleave', hideTooltip);

  const node = g.append('g').selectAll('g').data(simNodes).join('g')
    .attr('cursor', 'pointer')
    .on('click', (event, d) => {{ if (d.url) window.open(d.url, '_blank'); }});

  node.call(d3.drag()
    .on('start', (event, d) => {{ if (!event.active) _simulation.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; }})
    .on('drag',  (event, d) => {{ d.fx = event.x; d.fy = event.y; }})
    .on('end',   (event, d) => {{ if (!event.active) _simulation.alphaTarget(0); d.fx = null; d.fy = null; }}));

  node.append('circle')
    .attr('r', d => rScale(d.health_score || 0))
    .attr('fill', d => d.isNeighbour ? '#21262d' : '#1c2128')
    .attr('stroke', d => d.isNeighbour ? '#484f58' : tierColor(d.health_tier))
    .attr('stroke-width', d => d.isNeighbour ? 1 : confStroke(d.confidence))
    .attr('stroke-dasharray', d => d.isNeighbour ? '4 2' : null);

  node.append('text')
    .attr('text-anchor', 'middle').attr('dy', d => rScale(d.health_score || 0) + 12)
    .attr('fill', d => d.isNeighbour ? '#484f58' : '#8b949e')
    .attr('font-size', '9px').attr('pointer-events', 'none')
    .text(d => d.name.length > 20 ? d.name.slice(0, 18) + '…' : d.name);

  node.filter(d => d.isNeighbour).append('text')
    .attr('text-anchor', 'middle').attr('dy', d => rScale(d.health_score || 0) + 22)
    .attr('fill', '#484f58').attr('font-size', '8px').attr('pointer-events', 'none')
    .text(d => (d.domain || '').replace(/^\d+\.\s*/, '').slice(0, 18));

  _simulation.on('tick', () => {{
    link.attr('x1', e => e.source.x).attr('y1', e => e.source.y)
        .attr('x2', e => e.target.x).attr('y2', e => e.target.y);
    node.attr('transform', d => `translate(${{d.x}},${{d.y}})`);
  }});
}}
```

- [ ] Verify: clicking a domain node in connections view renders service-level graph
- [ ] Verify: cross-domain neighbours shown with dashed grey border
- [ ] Verify: hover on edge shows `detail` field in tooltip
- [ ] Verify: clicking service node opens GitHub URL in new tab
- [ ] Verify: "← Domain overview" resets to domain view
- [ ] Commit: `git add scripts/pilot.py && git commit -m "feat: add service-level D3 force graph"`

---

## Task 6 — Resize handling

**Files:**
- Modify: `scripts/pilot.py` — `<script>` block, after `renderServiceGraph`

```javascript
let _resizeTimer = null;
window.addEventListener('resize', () => {{
  if (_currentView !== 'connections') return;
  clearTimeout(_resizeTimer);
  _resizeTimer = setTimeout(() => initConnections(), 150);
}});
```

- [ ] Resize browser window while in Connections view — verify SVG re-renders to fill new dimensions
- [ ] Commit: `git add scripts/pilot.py && git commit -m "feat: add connections view resize handling"`

---

## Task 7 — End-to-end integration validation

**Prerequisites:** Run `scripts/extract_relationships.py` to populate real edges, then regenerate viewer.

- [ ] Domain-level view: 11 nodes visible, sized by repo count
- [ ] `depends_on` edges: blue dashed; `calls` edges: orange solid
- [ ] Heavier-weight edges (higher count) render thicker
- [ ] Click domain node → transitions to service view with back button
- [ ] Service view: domain repos with coloured tier borders; neighbours with grey dashed borders
- [ ] Hover edge in domain view → tooltip "depends_on x3" or similar
- [ ] Hover edge in service view → tooltip shows `detail` string
- [ ] Click service node → GitHub URL opens in new tab
- [ ] Back button → resets to domain view
- [ ] Empty state shown when no relationship edges in graph
- [ ] Map view unchanged: domain blocks, mid-panel, detail-panel, search all work
- [ ] D3 SRI: DevTools Network → `d3.min.js` loads 200, no integrity errors

---

## f-string brace escaping reference

| JS construct | Python f-string |
|---|---|
| `{ key: val }` | `{{ key: val }}` |
| `${variable}` | `${{variable}}` |
| `function() {}` | `function() {{}}` |
| `if (x) { ... }` | `if (x) {{ ... }}` |

`{graph_json}` (f-string substitution) stays as single braces — do not escape.

---

## Implementation sequence

```
Pre-impl (SRI hash) → Task 1 (CSS+HTML) → Task 2 (switchView+data prep) →
Task 3 (tooltip) → Task 4 (domain D3) → Task 5 (service D3) →
Task 6 (resize) → Task 7 (integration)
```
