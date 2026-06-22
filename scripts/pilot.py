"""
Classify repos into the TVaaS domain taxonomy.

Run:
    .venv/bin/python -m scripts.pilot             # top 10 active repos
    .venv/bin/python -m scripts.pilot --top 25    # top 25
    .venv/bin/python -m scripts.pilot --all       # all repos
"""

import json
import os
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from discovery.config import _github_token
from discovery.file_fetcher import FileFetcher
from discovery.classifier import Classifier
from discovery.scanners.github import GitHubScanner

OUT_DIR  = Path("architecture-overview")

def _load_taxonomy() -> list[dict]:
    p = Path(__file__).parent.parent / "discovery" / "taxonomy.json"
    return json.loads(p.read_text())["domains"]
CACHE       = OUT_DIR / ".cache"
ALL_MODE    = "--all" in sys.argv
TOP_N       = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[1] == "--top" else 10
MAX_WORKERS = 12   # concurrent file-fetch + classify workers
_print_lock = threading.Lock()


# ── helpers ───────────────────────────────────────────────────────────────────

def load_repos(path: str = "output/repo_health.json") -> list[dict]:
    with open(path) as f:
        return json.load(f)

def select_repos(repos: list[dict], all_mode: bool, n: int) -> list[dict]:
    """All mode: every repo. Top-N mode: most recently active non-dormant."""
    if all_mode:
        # Classify everything — dormant repos still need domain assignment for governance
        return [r for r in repos if r.get("full_name")]
    active = [
        r for r in repos
        if r.get("last_commit_at")
        and r.get("health", {}).get("tier") not in ("dormant", None)
    ]
    return sorted(active, key=lambda r: r["last_commit_at"], reverse=True)[:n]

def cached(repo_name: str) -> dict | None:
    p = CACHE / (repo_name.replace("/", "__") + ".json")
    return json.loads(p.read_text()) if p.exists() else None

def cache_write(repo_name: str, data: dict) -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    p = CACHE / (repo_name.replace("/", "__") + ".json")
    p.write_text(json.dumps(data, indent=2))


# ── analysis ──────────────────────────────────────────────────────────────────

def _log(msg: str) -> None:
    with _print_lock:
        print(msg, flush=True)

_thread_local = threading.local()

def _get_thread_fetcher(token: str) -> FileFetcher:
    """One FileFetcher (= one requests.Session) per thread — sessions are not thread-safe."""
    if not hasattr(_thread_local, "fetcher"):
        _thread_local.fetcher = FileFetcher(token)
    return _thread_local.fetcher

def analyze(repo: dict, clf: Classifier, token: str) -> dict:
    """Classify one repo. clf is shared (thread-safe); fetcher is per-thread."""
    name = repo["full_name"]
    hit = cached(name)
    if hit:
        hit["_cached"] = True
        return hit

    fetcher = _get_thread_fetcher(token)
    files   = fetcher.fetch_signals(name)
    try:
        classification = clf.classify(name, repo.get("language"), files)
    except Exception as e:
        _log(f"  ! classify failed for {name}: {e}")
        classification = {
            "domain": "10. Platform foundation", "subdomain": "Cloud Infra",
            "capability": "unknown", "confidence": "low",
            "summary": f"Classification failed: {e}", "flags": ["orphan"], "evidence": [],
        }

    result = {"repo": repo, "files_found": list(files.keys()), "classification": classification}
    cache_write(name, result)
    return result


# ── helpers ───────────────────────────────────────────────────────────────────

def _derive_subdomain(clf: dict) -> str:
    """Return a clean subdomain name: use classifier field if present, else truncate capability."""
    if clf.get("subdomain"):
        return clf["subdomain"].strip()
    cap = clf.get("capability", "")
    if not cap:
        return "General"
    # Take first clause before comma / · / ( / /
    first = re.split(r"[,·/(]", cap)[0].strip()
    words = first.split()
    return " ".join(words[:5]) if words else "General"


def _parse_codeowners(content: str) -> list[str]:
    """Extract team names (@org/team or @user) from CODEOWNERS file content."""
    teams: set[str] = set()
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        for match in re.findall(r"@([\w.-]+/[\w.-]+|[\w.-]+)", line):
            teams.add(match.split("/")[-1])  # take the team slug, strip org prefix
    return list(teams)


# ── graph builder ─────────────────────────────────────────────────────────────

def build_graph(results: list[dict], team_map: dict[str, list[str]] | None = None) -> dict:
    """Build 4-level graph: domain → subdomain → team → repo."""
    nodes, edges = [], []
    domains_seen:    set[str] = set()
    subdomains_seen: set[str] = set()
    teams_seen:      set[str] = set()

    team_map = team_map or {}

    # Pre-seed all domains and subdomains from taxonomy (gaps visible even with 0 repos)
    for td in _load_taxonomy():
        domain = td["name"]
        if domain not in domains_seen:
            nodes.append({"id": f"domain:{domain}", "type": "domain", "name": domain})
            domains_seen.add(domain)
        for sub in td["subdomains"]:
            sub_id = f"sub:{domain}::{sub}"
            if sub_id not in subdomains_seen:
                nodes.append({
                    "id": sub_id, "type": "subdomain",
                    "name": sub, "domain": domain, "repo_count": 0,
                })
                edges.append({"source": sub_id, "target": f"domain:{domain}", "type": "belongs_to"})
                subdomains_seen.add(sub_id)

    for r in results:
        repo = r["repo"]
        clf  = r["classification"]
        domain    = clf.get("domain", "Unknown")
        subdomain = _derive_subdomain(clf)
        full_name = repo["full_name"]

        # Teams: GitHub Teams API + CODEOWNERS fallback
        teams = list(team_map.get(full_name, []))
        # (CODEOWNERS content would need file content stored in cache to parse here)

        # ── domain node ──────────────────────────────────────────────────────
        if domain not in domains_seen:
            nodes.append({"id": f"domain:{domain}", "type": "domain", "name": domain})
            domains_seen.add(domain)

        # ── subdomain node ───────────────────────────────────────────────────
        sub_id = f"sub:{domain}::{subdomain}"
        if sub_id not in subdomains_seen:
            nodes.append({
                "id": sub_id, "type": "subdomain",
                "name": subdomain, "domain": domain,
            })
            edges.append({
                "source": sub_id, "target": f"domain:{domain}", "type": "belongs_to",
            })
            subdomains_seen.add(sub_id)

        # ── team nodes ───────────────────────────────────────────────────────
        for team in teams:
            team_id = f"team:{team}"
            if team_id not in teams_seen:
                nodes.append({"id": team_id, "type": "team", "name": team})
                teams_seen.add(team_id)

        # ── repo node ────────────────────────────────────────────────────────
        rid = f"repo:{full_name}"
        nodes.append({
            "id":           rid,
            "type":         "repo",
            "name":         full_name,
            "url":          repo.get("url", ""),
            "domain":       domain,
            "subdomain":    subdomain,
            "teams":        teams,
            "capability":   clf.get("capability", ""),
            "confidence":   clf.get("confidence", "low"),
            "summary":      clf.get("summary", ""),
            "flags":        clf.get("flags", []),
            "evidence":     clf.get("evidence", []),
            "language":     repo.get("language"),
            "last_commit":  (repo.get("last_commit_at") or "")[:10],
            "health_tier":  (repo.get("health") or {}).get("tier"),
            "health_score": (repo.get("health") or {}).get("total"),
        })
        edges.append({
            "source": rid, "target": sub_id,
            "type": "belongs_to", "confidence": clf.get("confidence", "low"),
        })
        for team in teams:
            edges.append({"source": f"team:{team}", "target": rid, "type": "owns"})

    return {
        "nodes": nodes, "edges": edges,
        "meta": {"pilot_repos": len(results), "teams": len(teams_seen)},
    }


# ── findings.md ───────────────────────────────────────────────────────────────

def write_findings(results: list[dict], graph: dict) -> Path:
    path = OUT_DIR / "findings.md"

    by_domain: dict[str, list] = {}
    low_conf, flags_all = [], []
    for r in results:
        d = r["classification"].get("domain", "Unknown")
        by_domain.setdefault(d, []).append(r)
        if r["classification"].get("confidence") in ("medium", "low"):
            low_conf.append(r)
        for f in r["classification"].get("flags", []):
            flags_all.append((f, r["repo"]["full_name"]))

    lines = [
        "# Architecture Pilot — Findings",
        f"\n_Pilot: top {len(results)} active repos_\n",
        "## Domain distribution\n",
        "| Domain | Repos | Confidence |\n|---|---|---|",
    ]
    for domain, repos in sorted(by_domain.items(), key=lambda x: str(x[0])):
        confs = [r["classification"].get("confidence", "low") for r in repos]
        summary = ", ".join(sorted(set(confs)))
        lines.append(f"| {domain} | {len(repos)} | {summary} |")

    if flags_all:
        lines += ["\n## Flags\n", "| Flag | Repo |\n|---|---|"]
        for flag, name in flags_all:
            lines.append(f"| {flag} | {name} |")

    if low_conf:
        lines += ["\n## Clarification questions\n",
                  "_Answer these to improve confidence:_\n"]
        for r in low_conf:
            name = r["repo"]["full_name"]
            dom  = r["classification"].get("domain", "?")
            conf = r["classification"].get("confidence", "low")
            lines.append(f"- **{name}**: classified as _{dom}_ ({conf}) — what does this repo primarily do?")

    path.write_text("\n".join(lines))
    return path


# ── viewer ────────────────────────────────────────────────────────────────────


def write_viewer(graph: dict) -> Path:
    path = OUT_DIR / "index.html"
    graph_json = json.dumps(graph)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<script
  src="https://cdn.jsdelivr.net/npm/d3@7.9.0/dist/d3.min.js"
  integrity="sha384-CjloA8y00+1SDAUkjs099PVfnY2KmDC2BZnws9kh8D/lX1s46w6EPhpXdqMfjK6i"
  crossorigin="anonymous"></script>
<title>TVaaS Platform Architecture</title>
<style>
/* ── Design tokens ─────────────────────────────────────────────── */
:root {{
  --bg-base:     #0d1117;
  --bg-surface:  #161b22;
  --bg-elevated: #21262d;
  --bg-subtle:   #1c2128;
  --bd-subtle:   #21262d;
  --bd-default:  #30363d;
  --bd-emphasis: #484f58;
  --tx-primary:  #e6edf3;
  --tx-second:   #8b949e;
  --tx-muted:    #484f58;
  --ac-blue:     #58a6ff;
  --ac-blue-bg:  #1f3a5f20;
  --green:       #3fb950;  --green-bg: #0d2818;
  --amber:       #d29922;  --amber-bg: #271d0a;
  --red:         #f85149;  --red-bg:   #2d0f0e;
  --t-fast:      0.12s ease;
  --t-med:       0.2s ease;

  --core-fg:   #c7d2fe; --core-bg:   #1a1f6e18; --core-bd:   #534AB7;
  --hybrid-fg: #d6d3d1; --hybrid-bg: #2a261a18; --hybrid-bd: #857d6e;
  --vendor-fg: #6ee7b7; --vendor-bg: #0a2e1e18; --vendor-bd: #2ea87a;
}}
*,*::before,*::after {{ box-sizing:border-box; margin:0; padding:0 }}
html,body {{ height:100%; background:var(--bg-base); color:var(--tx-primary);
             font-family:system-ui,-apple-system,sans-serif; font-size:13px }}
body {{ display:flex; flex-direction:column; height:100vh; overflow:hidden }}

/* ── Topbar ─────────────────────────────────────────────────────── */
#topbar {{
  flex: 0 0 auto; height:46px; display:flex; align-items:center; gap:0;
  background:var(--bg-surface); border-bottom:1px solid var(--bd-subtle);
  padding:0 16px; gap:12px;
}}
.logo {{ font-size:13px; font-weight:600; color:var(--tx-primary); white-space:nowrap; letter-spacing:-.01em }}

#breadcrumb {{
  display:flex; align-items:center; gap:2px; flex:1;
  font-size:12px; color:var(--tx-muted); overflow:hidden;
}}
.bc-sep {{ margin:0 4px; color:var(--tx-muted); flex-shrink:0 }}
.bc-seg {{
  color:var(--tx-second); cursor:pointer; white-space:nowrap;
  overflow:hidden; text-overflow:ellipsis; max-width:200px;
  padding:3px 6px; border-radius:5px;
  transition:background var(--t-fast), color var(--t-fast);
}}
.bc-seg:hover {{ background:var(--bg-elevated); color:var(--tx-primary) }}
.bc-seg.current {{ color:var(--tx-primary); cursor:default }}
.bc-seg.current:hover {{ background:transparent }}

#topbar input {{
  background:var(--bg-base); border:1px solid var(--bd-default); border-radius:6px;
  color:var(--tx-primary); padding:5px 10px; font-size:12px; width:190px; flex-shrink:0;
}}
#topbar input:focus {{ outline:none; border-color:var(--ac-blue); box-shadow:0 0 0 3px #58a6ff18 }}

/* legend */
.leg {{ display:flex; align-items:center; gap:4px; font-size:10px; color:var(--tx-muted); flex-shrink:0 }}
.leg-sw {{ width:10px; height:10px; border-radius:2px; flex-shrink:0 }}

/* ── Body split ─────────────────────────────────────────────────── */
#body {{ flex:1 1 0; display:flex; overflow:hidden; min-height:0 }}

/* ── Resize handle ──────────────────────────────────────────────── */
.rz {{
  flex:0 0 4px; background:var(--bd-subtle); cursor:col-resize;
  transition:background var(--t-fast);
  position:relative;
}}
.rz:hover, .rz.dragging {{ background:var(--ac-blue) }}
.rz::after {{
  content:''; position:absolute; inset:-4px 0; /* wider hit area */
}}

/* ── Domain map (left) ──────────────────────────────────────────── */
#map {{
  flex: 0 0 460px; min-width:280px; max-width:600px;
  overflow-y:auto; padding:16px; background:var(--bg-surface);
}}
.plane-lbl {{
  font-size:9px; font-weight:700; letter-spacing:.1em; text-transform:uppercase;
  color:var(--tx-muted); margin:16px 0 7px;
}}
.plane-lbl:first-child {{ margin-top:0 }}
.dom {{
  border-radius:8px; border-width:1.5px; border-style:solid;
  padding:10px 11px 8px; cursor:pointer;
  transition:filter var(--t-fast), outline var(--t-fast);
  position:relative;
}}
.dom:hover {{ filter:brightness(1.12) }}
.dom.active {{ outline:2px solid var(--ac-blue); outline-offset:2px }}
.dom-header {{ display:flex; align-items:flex-start; justify-content:space-between; gap:6px }}
.dom-name {{ font-size:12px; font-weight:600; line-height:1.3 }}
.dom-pill {{
  font-size:10px; font-weight:700; padding:1px 7px; border-radius:10px;
  background:rgba(0,0,0,.25); flex-shrink:0;
}}
/* segmented bar: fixed 3px height, flex segments by proportion */
.conf-bar {{ display:flex; height:3px; border-radius:2px; margin-top:7px; overflow:hidden; gap:1px; background:var(--bd-subtle); }}
.cb-seg   {{ height:100%; border-radius:1px; }}
/* subdomain dots: 3 fixed dots, dimmed when zero */
.cdots {{ display:flex; gap:3px; flex-shrink:0 }}
.cdot  {{ width:7px; height:7px; border-radius:50%; opacity:.18 }}
.cdot.lit {{ opacity:1 }}

.core   {{ background:var(--core-bg);   border-color:var(--core-bd);   color:var(--core-fg) }}
.hybrid {{ background:var(--hybrid-bg); border-color:var(--hybrid-bd); color:var(--hybrid-fg) }}
.vendor {{ background:var(--vendor-bg); border-color:var(--vendor-bd); color:var(--vendor-fg) }}
.dashed {{ border-style:dashed }}

.row-full {{ display:flex }}
.row-full .dom {{ flex:1 }}
.row-thirds {{ display:flex; gap:7px; margin-top:7px }}
.row-thirds .dom {{ flex:1 }}
.row-flow {{ display:flex; align-items:stretch; margin-top:7px }}
.row-flow .dom {{ flex:1; min-width:0 }}
.flow-arrow {{ flex:0 0 22px; display:flex; align-items:center; justify-content:center;
               font-size:14px; color:var(--tx-muted) }}
.row-stack {{ display:flex; flex-direction:column; gap:5px; margin-top:7px }}
.row-stack .dom {{ width:100% }}

/* ── Middle nav panel ───────────────────────────────────────────── */
#mid {{
  flex: 0 0 260px; min-width:180px; max-width:400px;
  display:flex; flex-direction:column; overflow:hidden;
  background:var(--bg-base);
}}
#mid-placeholder {{
  flex:1; display:flex; align-items:center; justify-content:center;
  font-size:11px; color:var(--tx-muted); padding:20px; text-align:center;
}}
#mid-body {{ flex:1; overflow-y:auto }}
.msec-hdr {{
  font-size:9px; font-weight:700; letter-spacing:.1em; text-transform:uppercase;
  color:var(--tx-muted); padding:10px 14px 5px;
  position:sticky; top:0; background:var(--bg-base); z-index:1;
}}
.mrow {{
  display:flex; align-items:center; gap:8px; padding:6px 14px;
  cursor:pointer; border-left:2px solid transparent;
  transition:background var(--t-fast), border-color var(--t-fast);
}}
.mrow:hover {{ background:var(--bg-elevated) }}
.mrow.sel {{ background:var(--bg-elevated); border-left-color:var(--ac-blue) }}
.mrow .mname {{
  flex:1; font-size:12px; color:var(--tx-primary);
  overflow:hidden; text-overflow:ellipsis; white-space:nowrap;
}}
.mrow .mname.gap {{ color:var(--tx-muted); font-style:italic }}
.mrow .mbadge {{
  flex-shrink:0; font-size:10px; font-weight:600;
  padding:1px 7px; border-radius:10px;
  background:var(--bg-elevated); color:var(--tx-second);
}}
.mrow.sel .mbadge {{ background:var(--ac-blue-bg); color:var(--ac-blue) }}
.gap-badge {{ color:var(--tx-muted)!important; background:transparent!important; font-style:italic }}
.cdots {{ display:flex; gap:2px; flex-shrink:0 }}
.ti {{ font-size:12px; flex-shrink:0; color:var(--tx-muted) }}

/* ── Detail panel (right) ───────────────────────────────────────── */
#detail {{
  flex:1 1 0; display:flex; flex-direction:column; overflow:hidden; min-width:0;
  background:var(--bg-base);
}}
#detail-header {{
  flex:0 0 auto; padding:14px 20px 10px; border-bottom:1px solid var(--bd-subtle);
}}
.dh-title {{ font-size:15px; font-weight:700; color:var(--tx-primary); margin-bottom:3px }}
.dh-sub {{ font-size:11px; color:var(--tx-second); margin-bottom:10px }}
.conf-pills {{ display:flex; gap:8px }}
.cpill {{
  display:flex; align-items:center; gap:5px;
  font-size:11px; padding:3px 9px; border-radius:10px;
  border:1px solid transparent;
}}
.cpill.high   {{ background:var(--green-bg); color:var(--green); border-color:#238636 }}
.cpill.medium {{ background:var(--amber-bg); color:var(--amber); border-color:#9e6a03 }}
.cpill.low    {{ background:var(--red-bg);   color:var(--red);   border-color:#b91c1c }}
.cpill-dot {{ width:6px; height:6px; border-radius:50%; background:currentColor }}

#detail-search {{
  flex:0 0 auto; padding:8px 20px; border-bottom:1px solid var(--bd-subtle);
}}
#detail-search input {{
  width:100%; background:var(--bg-surface); border:1px solid var(--bd-default);
  border-radius:6px; color:var(--tx-primary); padding:5px 10px; font-size:12px;
}}
#detail-search input:focus {{ outline:none; border-color:var(--ac-blue) }}

#detail-empty {{
  flex:1; display:flex; align-items:center; justify-content:center;
  flex-direction:column; gap:10px; color:var(--tx-muted); padding:40px;
}}
#detail-empty p {{ font-size:13px; text-align:center; line-height:1.6 }}

#repo-list {{
  flex:1 1 0; overflow-y:auto; padding:8px 16px 20px;
}}

/* repo card */
.rc {{
  border:1px solid var(--bd-subtle); border-radius:8px; margin-bottom:5px;
  overflow:hidden; cursor:pointer;
  transition:border-color var(--t-fast);
  content-visibility:auto; contain-intrinsic-size:0 54px;
}}
.rc:hover {{ border-color:var(--bd-default) }}
.rc.open {{ border-color:#58a6ff30 }}
.rc-bar {{ width:3px; flex-shrink:0; align-self:stretch; border-radius:2px; margin:-9px 0 }}
.rc-bar.high   {{ background:var(--green) }}
.rc-bar.medium {{ background:var(--amber) }}
.rc-bar.low    {{ background:var(--red) }}
.rc-row {{
  display:flex; align-items:center; gap:9px; padding:9px 12px;
  min-height:54px;
}}
.rc-name {{
  flex:1; font-size:12px; font-weight:600; min-width:0;
  overflow:hidden; text-overflow:ellipsis; white-space:nowrap;
}}
.rc-name a {{ color:var(--ac-blue); text-decoration:none }}
.rc-name a:hover {{ text-decoration:underline }}
.rc-meta {{
  flex-shrink:0; display:flex; align-items:center; gap:6px;
  font-size:11px; color:var(--tx-second);
}}
.badge {{
  padding:2px 8px; border-radius:10px; font-size:10px; font-weight:700; flex-shrink:0;
}}
.badge.high   {{ background:var(--green-bg); color:var(--green); border:1px solid #238636 }}
.badge.medium {{ background:var(--amber-bg); color:var(--amber); border:1px solid #9e6a03 }}
.badge.low    {{ background:var(--red-bg);   color:var(--red);   border:1px solid #b91c1c }}
.tag {{ padding:2px 7px; border-radius:10px; font-size:10px; background:var(--bg-elevated); color:var(--tx-second); border:1px solid var(--bd-subtle) }}
.chev {{ font-size:10px; color:var(--tx-muted); flex-shrink:0; transition:transform var(--t-fast) }}
.rc.open .chev {{ transform:rotate(90deg) }}

.rc-body {{
  display:none; padding:0 12px 11px 24px; border-top:1px solid var(--bd-subtle);
  animation:fadeSlide var(--t-med) both;
}}
.rc.open .rc-body {{ display:block }}
@keyframes fadeSlide {{
  from {{ opacity:0; transform:translateY(-4px) }}
  to   {{ opacity:1; transform:translateY(0) }}
}}
.rc-cap {{
  font-size:10px; font-weight:700; letter-spacing:.06em; text-transform:uppercase;
  color:var(--tx-muted); margin:9px 0 4px;
}}
.rc-summary {{ font-size:12px; color:var(--tx-second); line-height:1.6; margin-bottom:8px }}
.rc-evid {{
  display:flex; flex-wrap:wrap; gap:4px; align-items:center;
  font-size:10px; color:var(--tx-muted);
}}
.evf {{
  font-family:monospace; font-size:10px; padding:1px 6px;
  background:var(--bg-surface); border:1px solid var(--bd-subtle);
  border-radius:4px; color:var(--tx-second);
}}
.rc-flags {{ display:flex; flex-wrap:wrap; gap:4px; margin-top:6px }}

/* panel fade-in */
.panel-in {{ animation:panelFade .18s ease-out both }}
@keyframes panelFade {{
  from {{ opacity:0; transform:translateY(3px) }}
  to   {{ opacity:1; transform:translateY(0) }}
}}

/* ── View toggle ──────────────────────────────────────────────── */
.view-toggle{{display:flex;align-items:center;gap:2px;background:var(--bg-base);
  border:1px solid var(--bd-default);border-radius:6px;padding:2px;flex-shrink:0;}}
.vt-btn{{font-size:11px;font-weight:600;padding:3px 10px;border-radius:4px;cursor:pointer;
  border:none;background:transparent;color:var(--tx-second);transition:background var(--t-fast),color var(--t-fast);}}
.vt-btn.active{{background:var(--bg-elevated);color:var(--tx-primary);}}

/* ── Connections view ──────────────────────────────────────────── */
#connections-view{{display:none;flex:1 1 0;flex-direction:column;overflow:hidden;min-height:0;}}
#connections-view.visible{{display:flex;}}
#conn-toolbar{{flex:0 0 auto;padding:7px 16px;border-bottom:1px solid var(--bd-subtle);
  display:flex;align-items:center;gap:10px;background:var(--bg-surface);font-size:11px;color:var(--tx-second);}}
#conn-back{{display:none;cursor:pointer;padding:3px 8px;border-radius:5px;
  border:1px solid var(--bd-default);background:var(--bg-elevated);color:var(--tx-primary);font-size:11px;}}
#conn-back:hover{{background:var(--bd-subtle);}}
#conn-back.visible{{display:inline-block;}}
#conn-title{{font-weight:500;color:var(--tx-primary);}}
#conn-legend{{display:flex;gap:12px;align-items:center;margin-left:auto;}}
.cl-item{{display:flex;align-items:center;gap:5px;font-size:10px;color:var(--tx-muted);}}
.cl-line{{width:24px;height:2px;flex-shrink:0;}}
#conn-svg-wrap{{flex:1 1 0;overflow:hidden;position:relative;}}
#conn-svg{{width:100%;height:100%;display:block;}}
#conn-tooltip{{position:absolute;pointer-events:none;background:var(--bg-elevated);
  border:1px solid var(--bd-default);border-radius:6px;padding:6px 10px;font-size:11px;
  color:var(--tx-primary);max-width:260px;white-space:pre-wrap;display:none;z-index:10;
  box-shadow:0 4px 12px #00000040;}}
#conn-empty{{position:absolute;inset:0;display:flex;align-items:center;
  justify-content:center;flex-direction:column;gap:8px;color:var(--tx-muted);
  font-size:13px;text-align:center;padding:40px;pointer-events:none;}}
#conn-empty code{{background:var(--bg-elevated);padding:1px 6px;border-radius:4px;
  font-size:11px;color:var(--tx-second);}}
</style>
</head>
<body>

<!-- Topbar -->
<div id="topbar">
  <span class="logo">TVaaS Platform</span>
  <div class="view-toggle">
    <button class="vt-btn active" id="btn-map"         onclick="switchView('map')">Map</button>
    <button class="vt-btn"        id="btn-connections" onclick="switchView('connections')">Connections</button>
  </div>
  <div id="breadcrumb">
    <span class="bc-seg current" onclick="goHome()">Architecture</span>
  </div>
  <div class="leg"><div class="leg-sw" style="background:var(--core-bg);border:1.5px solid var(--core-bd)"></div>core</div>
  <div class="leg"><div class="leg-sw" style="background:var(--vendor-bg);border:1.5px solid var(--vendor-bd)"></div>delegatable</div>
  <div class="leg"><div class="leg-sw" style="background:var(--hybrid-bg);border:1.5px solid var(--hybrid-bd)"></div>hybrid</div>
  <div style="width:1px;height:20px;background:var(--bd-subtle);flex-shrink:0"></div>
  <div class="leg" title="Verified = files found (README, pom.xml…)&#10;Inferred = partial signal&#10;Name only = no readable files; repo name used" style="cursor:help;gap:6px">
    <span style="font-size:10px;padding:1px 6px;border-radius:8px;background:var(--green-bg);color:var(--green);border:1px solid #238636">Verified</span>
    <span style="font-size:10px;padding:1px 6px;border-radius:8px;background:var(--amber-bg);color:var(--amber);border:1px solid #9e6a03">Inferred</span>
    <span style="font-size:10px;padding:1px 6px;border-radius:8px;background:var(--red-bg);color:var(--red);border:1px solid #b91c1c">Name only</span>
    <span style="font-size:9px;color:var(--tx-muted)">← classification confidence</span>
  </div>
  <input id="gsearch" type="text" placeholder="Search repos…" oninput="globalSearch()">
</div>

<!-- Body -->
<div id="body">

  <!-- Domain map -->
  <div id="map">
    <div class="plane-lbl">Experience plane</div>
    <div class="row-full">
      <div class="dom core" id="b-exp" onclick="sel('7. Experience')">
        <div class="dom-header"><span class="dom-name">Experience</span><span class="dom-pill" id="c-exp"></span></div>
        <div class="conf-bar" id="h-exp"></div>
      </div>
    </div>
    <div class="plane-lbl">Decision plane</div>
    <div class="row-thirds">
      <div class="dom core"   id="b-ide" onclick="sel('5. Identity &amp; entitlements')">
        <div class="dom-header"><span class="dom-name">Identity &amp; entitlements</span><span class="dom-pill" id="c-ide"></span></div>
        <div class="conf-bar" id="h-ide"></div>
      </div>
      <div class="dom hybrid" id="b-mon" onclick="sel('6. Monetization')">
        <div class="dom-header"><span class="dom-name">Monetization</span><span class="dom-pill" id="c-mon"></span></div>
        <div class="conf-bar" id="h-mon"></div>
      </div>
      <div class="dom core"   id="b-ten" onclick="sel('9. B2B tenant operations')">
        <div class="dom-header"><span class="dom-name">Tenant operations</span><span class="dom-pill" id="c-ten"></span></div>
        <div class="conf-bar" id="h-ten"></div>
      </div>
    </div>
    <div class="plane-lbl">Content plane</div>
    <div class="row-flow">
      <div class="dom hybrid" id="b-sup" onclick="sel('1. Content supply chain')">
        <div class="dom-header"><span class="dom-name">Supply chain</span><span class="dom-pill" id="c-sup"></span></div>
        <div class="conf-bar" id="h-sup"></div>
      </div>
      <div class="flow-arrow">›</div>
      <div class="dom core"   id="b-cms" onclick="sel('2. Content management')">
        <div class="dom-header"><span class="dom-name">Content mgmt</span><span class="dom-pill" id="c-cms"></span></div>
        <div class="conf-bar" id="h-cms"></div>
      </div>
      <div class="flow-arrow">›</div>
      <div class="dom hybrid" id="b-pla" onclick="sel('3. Playout &amp; time-shift')">
        <div class="dom-header"><span class="dom-name">Playout</span><span class="dom-pill" id="c-pla"></span></div>
        <div class="conf-bar" id="h-pla"></div>
      </div>
      <div class="flow-arrow">›</div>
      <div class="dom vendor" id="b-del" onclick="sel('4. Delivery')">
        <div class="dom-header"><span class="dom-name">Delivery</span><span class="dom-pill" id="c-del"></span></div>
        <div class="conf-bar" id="h-del"></div>
      </div>
    </div>
    <div class="plane-lbl">Horizontal planes</div>
    <div class="row-stack">
      <div class="dom core"   id="b-dat" onclick="sel('8. Data &amp; analytics')">
        <div class="dom-header"><span class="dom-name">Data &amp; analytics</span><span class="dom-pill" id="c-dat"></span></div>
        <div class="conf-bar" id="h-dat"></div>
      </div>
      <div class="dom hybrid" id="b-pla2" onclick="sel('10. Platform foundation')">
        <div class="dom-header"><span class="dom-name">Platform foundation</span><span class="dom-pill" id="c-pla2"></span></div>
        <div class="conf-bar" id="h-pla2"></div>
      </div>
      <div class="dom vendor dashed" id="b-sec" onclick="sel('11. Security')">
        <div class="dom-header"><span class="dom-name">Security — cross-cutting</span><span class="dom-pill" id="c-sec"></span></div>
        <div class="conf-bar" id="h-sec"></div>
      </div>
    </div>
  </div><!-- /map -->

  <div class="rz" id="rz1"></div>

  <!-- Middle nav -->
  <div id="mid">
    <div id="mid-placeholder">← Select a domain</div>
    <div id="mid-body" style="display:none"></div>
  </div>

  <div class="rz" id="rz2"></div>

  <!-- Detail panel -->
  <div id="detail">
    <div id="detail-empty">
      <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2">
        <circle cx="12" cy="12" r="10"/><path d="M12 8v4M12 16h.01"/>
      </svg>
      <p>Select a domain to start exploring.<br>Click any block on the left.</p>
    </div>
  </div>


</div><!-- /body -->

<!-- Connections view — sibling of #body, not inside it -->
<div id="connections-view">
  <div id="conn-toolbar">
    <button id="conn-back" onclick="connBack()">&#8592; Domain overview</button>
    <span id="conn-title">Domain dependency map</span>
    <div id="conn-legend">
      <div class="cl-item">
        <div class="cl-line" style="background:#58a6ff;border-top:2px dashed #58a6ff;height:0"></div>
        depends_on
      </div>
      <div class="cl-item">
        <div class="cl-line" style="background:#d97706"></div>
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
      <p>No dependency relationships extracted yet.<br>
         Run <code>scripts/extract_relationships.py</code> first.</p>
    </div>
  </div>
</div>

<script>
const G = {graph_json};

/* ── Domain block map ──────────────────────────────────────────── */
const BLOCKS = {{
  '7. Experience':              ['b-exp','c-exp','h-exp'],
  '5. Identity & entitlements': ['b-ide','c-ide','h-ide'],
  '6. Monetization':            ['b-mon','c-mon','h-mon'],
  '9. B2B tenant operations':   ['b-ten','c-ten','h-ten'],
  '1. Content supply chain':    ['b-sup','c-sup','h-sup'],
  '2. Content management':      ['b-cms','c-cms','h-cms'],
  '3. Playout & time-shift':    ['b-pla','c-pla','h-pla'],
  '4. Delivery':                ['b-del','c-del','h-del'],
  '8. Data & analytics':        ['b-dat','c-dat','h-dat'],
  '10. Platform foundation':    ['b-pla2','c-pla2','h-pla2'],
  '11. Security':               ['b-sec','c-sec','h-sec'],
}};

const HC = {{high:'#238636',medium:'#9e6a03',low:'#b91c1c'}};

/* ── Data indexes ──────────────────────────────────────────────── */
const repos = G.nodes.filter(n=>n.type==='repo');
const byDomain = {{}};
repos.forEach(r => (byDomain[r.domain]=byDomain[r.domain]||[]).push(r));

const allSubsByDomain = {{}};
G.nodes.filter(n=>n.type==='subdomain').forEach(n => {{
  (allSubsByDomain[n.domain]=allSubsByDomain[n.domain]||[]).push(n.name);
}});

/* ── Navigation state ──────────────────────────────────────────── */
let state = {{ domain:null, sub:null, team:null, search:'' }};

/* ── Resize handles ────────────────────────────────────────────── */
function setupResize(handleId, panelId) {{
  const handle = document.getElementById(handleId);
  const panel  = document.getElementById(panelId);
  handle.addEventListener('mousedown', e => {{
    const startX  = e.clientX;
    const startW  = panel.getBoundingClientRect().width;
    handle.classList.add('dragging');
    const min = parseInt(getComputedStyle(panel).minWidth)||180;
    const max = parseInt(getComputedStyle(panel).maxWidth)||600;
    const onMove = e => {{
      const w = Math.max(min, Math.min(max, startW + (e.clientX - startX)));
      panel.style.flex = `0 0 ${{w}}px`;
    }};
    const onUp = () => {{
      handle.classList.remove('dragging');
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);
      document.body.style.cursor = '';
    }};
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
    document.body.style.cursor = 'col-resize';
    e.preventDefault();
  }});
}}
setupResize('rz1','map');
setupResize('rz2','mid');

/* ── Confidence labels ─────────────────────────────────────────── */
// Confidence = how certain the classifier was, based on files found.
// High   → clear signals from README, pom.xml, package.json, etc.
// Medium → some files found; partial or ambiguous signal
// Low    → no readable files; classified from repo name only
const CONF = {{
  high:   {{ label:'Verified',  tip:'Strong evidence — README, build files or API specs found' }},
  medium: {{ label:'Inferred',  tip:'Partial signal — some files found but ambiguous' }},
  low:    {{ label:'Name only', tip:'No readable files — classified from repo name alone' }},
}};

/* ── Confidence bar ────────────────────────────────────────────── */
function confBar(rs) {{
  if (!rs.length) return '';
  const c = {{high:0,medium:0,low:0}};
  rs.forEach(r => c[r.confidence]++);
  // Proportional segments — same fixed height regardless of repo count
  return Object.entries(HC)
    .filter(([k]) => c[k] > 0)
    .map(([k,col]) => `<div class="cb-seg" style="background:${{col}};flex:${{c[k]}}"></div>`)
    .join('');
}}

/* ── Init domain blocks ────────────────────────────────────────── */
function init() {{
  Object.entries(BLOCKS).forEach(([domain,[bid,cid,hid]]) => {{
    const rs = byDomain[domain]||[];
    const pill = document.getElementById(cid);
    const bar  = document.getElementById(hid);
    if (pill) pill.textContent = rs.length||'';
    if (bar && rs.length) bar.innerHTML = confBar(rs);
  }});
  const teams = G.nodes.filter(n=>n.type==='team').length;
  const domCount = Object.keys(byDomain).length;
  // Update topbar subtitle via breadcrumb
}}

/* ── Breadcrumb ────────────────────────────────────────────────── */
function renderBreadcrumb() {{
  const bc = document.getElementById('breadcrumb');
  const segs = [{{label:'Architecture', fn:'goHome'}}];
  if (state.domain) {{
    const short = state.domain.split('. ').slice(1).join('. ') || state.domain;
    segs.push({{label:short, fn:'() => jumpToDomain()'}});
  }}
  if (state.sub)  segs.push({{label:state.sub,  fn:'() => jumpToSub()'}});
  if (state.team) segs.push({{label:'◈ '+state.team, fn:null}});

  bc.innerHTML = segs.map((s,i) => {{
    const isCurrent = i === segs.length-1;
    const cls = isCurrent ? 'bc-seg current' : 'bc-seg';
    const click = (!isCurrent && s.fn) ? `onclick="${{s.fn}}()"` : '';
    return (i>0 ? '<span class="bc-sep">/</span>' : '') +
           `<span class="${{cls}}" ${{click}} title="${{s.label}}">${{s.label}}</span>`;
  }}).join('');
}}

function goHome() {{
  state = {{domain:null,sub:null,team:null,search:''}};
  document.querySelectorAll('.dom').forEach(e=>e.classList.remove('active'));
  document.getElementById('mid-placeholder').style.display='flex';
  document.getElementById('mid-body').style.display='none';
  document.getElementById('detail').innerHTML = `<div id="detail-empty">
    <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2">
      <circle cx="12" cy="12" r="10"/><path d="M12 8v4M12 16h.01"/>
    </svg><p>Select a domain to start exploring.</p></div>`;
  renderBreadcrumb();
}}
function jumpToDomain() {{ state.sub=null; state.team=null; renderMid(); renderDetail(); renderBreadcrumb(); }}
function jumpToSub()    {{ state.team=null; renderDetail(); renderBreadcrumb(); }}

/* ── Domain select ─────────────────────────────────────────────── */
function sel(domain) {{
  state.domain=domain; state.sub=null; state.team=null; state.search='';
  document.querySelectorAll('.dom').forEach(e=>e.classList.remove('active'));
  const bid=(BLOCKS[domain]||[])[0];
  if (bid) document.getElementById(bid)?.classList.add('active');
  renderMid(); renderDetail(); renderBreadcrumb();
}}

/* ── Middle panel ──────────────────────────────────────────────── */
function renderMid() {{
  if (!state.domain) return;
  const domainRepos = byDomain[state.domain]||[];
  const bySub={{}}, byTeam={{}};
  domainRepos.forEach(r => {{
    const s=r.subdomain||'General';
    (bySub[s]=bySub[s]||[]).push(r);
    (r.teams||[]).forEach(t=>(byTeam[t]=byTeam[t]||[]).push(r));
    if (!(r.teams||[]).length) (byTeam['Unassigned']=byTeam['Unassigned']||[]).push(r);
  }});

  const allSubs = allSubsByDomain[state.domain]||Object.keys(bySub);

  const subRows = allSubs.map(sub => {{
    const rs = bySub[sub]||[];
    const isEmpty = !rs.length;
    const isSel = state.sub===sub;
    const c={{high:0,medium:0,low:0}};
    rs.forEach(r=>c[r.confidence]++);
    // 3 fixed dots (high/medium/low), lit if any repos in that confidence level
    const dots = Object.entries(HC).map(([k,col]) =>
      `<div class="cdot${{c[k]>0?' lit':''}}" style="background:${{col}}"></div>`
    ).join('');
    return `<div class="mrow${{isSel?' sel':''}}" onclick="selSub(this.dataset.s)" data-s="${{sub}}" title="${{sub}}">
      <div class="cdots">${{dots}}</div>
      <div class="mrow-name${{isEmpty?' gap':''}}">${{sub}}</div>
      <div class="mbadge${{isEmpty?' gap-badge':''}}">${{isEmpty?'—':rs.length}}</div>
    </div>`;
  }}).join('');

  const realTeams = Object.keys(byTeam).filter(t=>t!=='Unassigned');
  const teamSection = realTeams.length ? `
    <div class="msec-hdr">Teams</div>
    ${{[...realTeams.sort((a,b)=>(byTeam[b]||[]).length-(byTeam[a]||[]).length),
        byTeam['Unassigned']?'Unassigned':null].filter(Boolean).map(team => {{
      const rs=byTeam[team]||[];
      const isSel=state.team===team;
      const unassigned=team==='Unassigned';
      return `<div class="mrow${{isSel?' sel':''}}" onclick="selTeam(this.dataset.t)" data-t="${{team}}" title="${{team}}">
        <span class="ti">${{unassigned?'?':'◈'}}</span>
        <div class="mrow-name${{unassigned?' gap':''}}">${{team}}</div>
        <div class="mbadge">${{rs.length}}</div>
      </div>`;
    }}).join('')}}` : '';

  document.getElementById('mid-placeholder').style.display='none';
  const mb = document.getElementById('mid-body');
  mb.style.display='block';
  mb.innerHTML = `<div class="msec-hdr">Subdomains</div>${{subRows}}${{teamSection}}`;
}}

function selSub(sub) {{
  state.sub = state.sub===sub ? null : sub;
  state.team=null;
  renderMid(); renderDetail(); renderBreadcrumb();
}}
function selTeam(team) {{
  state.team = state.team===team ? null : team;
  state.sub=null;
  renderMid(); renderDetail(); renderBreadcrumb();
}}

/* ── Detail panel ──────────────────────────────────────────────── */
function currentRepos() {{
  if (!state.domain) return [];
  let rs = byDomain[state.domain]||[];
  if (state.sub)    rs=rs.filter(r=>(r.subdomain||'General')===state.sub);
  if (state.team)   rs=rs.filter(r=> state.team==='Unassigned'
      ? !(r.teams||[]).length : (r.teams||[]).includes(state.team));
  const q = (state.search||document.getElementById('gsearch')?.value||'').toLowerCase();
  if (q) rs=rs.filter(r=>
    r.name.toLowerCase().includes(q)||(r.summary||'').toLowerCase().includes(q)||
    (r.subdomain||'').toLowerCase().includes(q)||(r.capability||'').toLowerCase().includes(q));
  return rs;
}}

function renderDetail() {{
  const rs = currentRepos();
  const detail = document.getElementById('detail');

  if (!state.domain) return;

  const counts={{high:0,medium:0,low:0}};
  rs.forEach(r=>counts[r.confidence]++);

  const subtitle = state.sub ? state.sub : state.team ? '◈ '+state.team : 'All repos';
  const domainShort = (state.domain.split('. ').slice(1).join('. ')||state.domain);

  const pills = Object.entries(counts).filter(([,n])=>n>0).map(([k,n])=>
    `<div class="cpill ${{k}}" title="${{CONF[k]?.tip||k}}">
       <div class="cpill-dot"></div>${{n}} ${{CONF[k]?.label||k}}
     </div>`
  ).join('');

  detail.innerHTML = `
    <div id="detail-header" class="panel-in">
      <div class="dh-title">${{subtitle}}</div>
      <div class="dh-sub">${{domainShort}} · ${{rs.length}} repo${{rs.length!==1?'s':''}}</div>
      <div class="conf-pills">${{pills}}</div>
    </div>
    <div id="detail-search">
      <input type="text" placeholder="Filter within results…"
             value="${{state.search}}" oninput="detailSearch(this.value)">
    </div>
    <div id="repo-list" class="panel-in">
      ${{rs.length===0
        ? '<div style="padding:32px;color:var(--tx-muted);font-size:12px">No repos match the current filter.</div>'
        : rs.sort((a,b)=>{{const o={{high:0,medium:1,low:2}};return(o[a.confidence]??3)-(o[b.confidence]??3)}})
             .map((r,i)=>repoCard(r,i)).join('')
      }}
    </div>`;
}}

function repoCard(r,i) {{
  const short  = r.name.split('/').pop();
  const flags  = (r.flags||[]).map(f=>`<span class="tag">${{f}}</span>`).join('');
  const evFiles= (r.evidence||[]).map(e=>`<span class="evf">${{e}}</span>`).join('');
  const teams  = (r.teams||[]).slice(0,2).map(t=>`<span class="tag">◈ ${{t}}</span>`).join('');
  return `<div class="rc" id="rc${{i}}" onclick="toggleRC(this)">
    <div class="rc-row">
      <div class="rc-bar ${{r.confidence}}"></div>
      <div class="rc-name"><a href="${{r.url}}" target="_blank" onclick="event.stopPropagation()">${{short}}</a></div>
      <div class="rc-meta">
        <span class="badge ${{r.confidence}}" title="${{CONF[r.confidence]?.tip||r.confidence}}">${{CONF[r.confidence]?.label||r.confidence}}</span>
        <span style="color:var(--tx-muted)">${{r.language||'—'}}</span>
        <span style="color:var(--tx-muted)">${{r.last_commit||'—'}}</span>
        ${{teams}}
        ${{(r.flags||[]).length?`<span class="tag">${{r.flags[0]}}</span>`:''}}
      </div>
      <span class="chev">›</span>
    </div>
    <div class="rc-body">
      ${{r.subdomain?`<div class="rc-cap">${{r.subdomain}}</div>`:''}};
      ${{r.capability?`<div style="font-size:11px;color:var(--tx-second);margin-bottom:6px">${{r.capability}}</div>`:''}};
      ${{r.summary?`<div class="rc-summary">${{r.summary}}</div>`:''}};
      ${{flags?`<div class="rc-flags">${{flags}}</div>`:''}};
      ${{evFiles?`<div class="rc-evid"><span style="margin-right:4px">Evidence:</span>${{evFiles}}</div>`:''}};
    </div>
  </div>`;
}}

function toggleRC(el) {{ el.classList.toggle('open') }}

function detailSearch(q) {{
  state.search=q;
  renderDetail();
}}

function globalSearch() {{
  const q = document.getElementById('gsearch').value;
  if (!q) return;
  // Search across all repos and show results in detail panel
  const detail = document.getElementById('detail');
  const rs = repos.filter(r =>
    r.name.toLowerCase().includes(q.toLowerCase())||
    (r.summary||'').toLowerCase().includes(q.toLowerCase())||
    (r.capability||'').toLowerCase().includes(q.toLowerCase())
  ).slice(0,100);

  // Update breadcrumb to show search state
  const bc = document.getElementById('breadcrumb');
  bc.innerHTML = `<span class="bc-seg current">Search: "${{q}}" — ${{rs.length}} repos</span>
    <span class="bc-sep">·</span><span class="bc-seg" onclick="goHome()">Clear</span>`;

  detail.innerHTML = `
    <div id="detail-header" class="panel-in">
      <div class="dh-title">Search results</div>
      <div class="dh-sub">"${{q}}" · ${{rs.length}} repos</div>
    </div>
    <div id="repo-list" class="panel-in">
      ${{rs.map((r,i)=>repoCard(r,i)).join('') || '<div style="padding:32px;color:var(--tx-muted)">No results.</div>'}}
    </div>`;
}}

/* ══════════════════════════════════════════════════════════════
   CONNECTIONS VIEW — Tasks 20-24
   ══════════════════════════════════════════════════════════════ */

/* ── View switch ───────────────────────────────────────────── */
let _currentView = 'map';

function switchView(view) {{
  _currentView = view;
  const bodyEl = document.getElementById('body');           // map+mid+detail
  const connEl = document.getElementById('connections-view'); // sibling, not child
  document.getElementById('btn-map').classList.toggle('active', view === 'map');
  document.getElementById('btn-connections').classList.toggle('active', view === 'connections');
  if (view === 'map') {{
    if (_simulation) _simulation.stop();
    bodyEl.style.display = 'flex';
    connEl.style.display = 'none';
  }} else {{
    bodyEl.style.display = 'none';
    connEl.style.display = 'flex';   // now connEl is a direct child of <body>, gets full height
    requestAnimationFrame(() => {{
      requestAnimationFrame(() => initConnections());
    }});
  }}
}}

/* ── Data indexes ──────────────────────────────────────────── */
const nodeById = {{}};
G.nodes.forEach(n => nodeById[n.id] = n);

const relEdges = G.edges.filter(e => e.type === 'depends_on' || e.type === 'calls');

function buildDomainGraph() {{
  const domainNodes = G.nodes.filter(n => n.type === 'domain');
  const repoDomain  = {{}};
  G.nodes.filter(n => n.type === 'repo').forEach(r => repoDomain[r.id] = r.domain);
  const edgeMap = {{}};
  relEdges.forEach(e => {{
    const sd = repoDomain[e.source], td = repoDomain[e.target];
    if (!sd || !td || sd === td) return;
    const key = sd + '||' + td + '||' + e.type;
    if (!edgeMap[key]) edgeMap[key] = {{source:sd,target:td,type:e.type,weight:0}};
    edgeMap[key].weight++;
  }});
  const repoCounts = {{}};
  G.nodes.filter(n => n.type === 'repo').forEach(r => {{
    repoCounts[r.domain] = (repoCounts[r.domain]||0)+1;
  }});
  const nodes = domainNodes.map(d => ({{id:d.id,name:d.name,repoCount:repoCounts[d.name]||0}}));
  return {{nodes, edges: Object.values(edgeMap)}};
}}

function buildServiceGraph(domainName) {{
  const domainRepos   = G.nodes.filter(n => n.type==='repo' && n.domain===domainName);
  const domainRepoIds = new Set(domainRepos.map(r => r.id));
  const neighbourIds  = new Set();
  relEdges.forEach(e => {{
    if (domainRepoIds.has(e.source) && !domainRepoIds.has(e.target)) neighbourIds.add(e.target);
    if (domainRepoIds.has(e.target) && !domainRepoIds.has(e.source)) neighbourIds.add(e.source);
  }});
  const nodeIds = new Set([...domainRepoIds,...neighbourIds]);
  const nodes = [...nodeIds].map(id => {{
    const n = nodeById[id];
    return {{id,name:n?n.name.split('/').pop():id,fullName:n?n.name:id,
             url:n?n.url:'',domain:n?n.domain:'',health_tier:n?n.health_tier:'',
             health_score:n?(n.health_score||0):0,confidence:n?n.confidence:'',
             isNeighbour:!domainRepoIds.has(id)}};
  }});
  const edges = relEdges.filter(e => nodeIds.has(e.source) && nodeIds.has(e.target));
  return {{nodes,edges,domainName}};
}}

/* ── Tooltip ────────────────────────────────────────────────── */
function showTooltip(event, text) {{
  const t = document.getElementById('conn-tooltip');
  t.textContent = text; t.style.display = 'block'; _posTooltip(event);
}}
function hideTooltip() {{ document.getElementById('conn-tooltip').style.display = 'none'; }}
function _posTooltip(event) {{
  const t = document.getElementById('conn-tooltip');
  const wrap = document.getElementById('conn-svg-wrap');
  const rect = wrap.getBoundingClientRect();
  let x = event.clientX - rect.left + 12, y = event.clientY - rect.top + 12;
  if (x + 280 > rect.width)  x = event.clientX - rect.left - 284;
  if (y + 60  > rect.height) y = event.clientY - rect.top  - 64;
  t.style.left = x + 'px'; t.style.top = y + 'px';
}}
document.addEventListener('DOMContentLoaded', () => {{
  document.getElementById('conn-svg').addEventListener('mousemove', e => {{
    if (document.getElementById('conn-tooltip').style.display === 'block') _posTooltip(e);
  }});
}});

/* ── D3 state ───────────────────────────────────────────────── */
let _connState  = {{level:'domain',domain:null}};
let _simulation = null;

const TIER_COL = {{governed:'#3fb950',ungoverned:'#d29922',dormant:'#484f58'}};
function tierCol(tier)  {{ return TIER_COL[tier] || '#8b949e'; }}
function confStroke(c)  {{ return c==='high'?2.5:c==='medium'?1.5:0.8; }}

function initConnections() {{
  if (_connState.level === 'domain') renderDomainGraph();
  else                               renderServiceGraph(_connState.domain);
}}

function connBack() {{
  _connState = {{level:'domain',domain:null}};
  document.getElementById('conn-back').classList.remove('visible');
  document.getElementById('conn-title').textContent = 'Domain dependency map';
  renderDomainGraph();
}}

/* ── Domain-level D3 force graph ───────────────────────────── */
function renderDomainGraph() {{
  if (_simulation) _simulation.stop();
  const wrap = document.getElementById('conn-svg-wrap');
  const svg  = document.getElementById('conn-svg');
  const rect = wrap.getBoundingClientRect();
  // Fallback: viewport minus fixed panels (topbar 48px; map/mid hidden in connections mode)
  const W = rect.width  > 10 ? rect.width  : (window.innerWidth  - 2);
  const H = rect.height > 10 ? rect.height : (window.innerHeight - 90);
  svg.innerHTML = '';

  const {{nodes,edges}} = buildDomainGraph();
  const emptyEl = document.getElementById('conn-empty');
  if (relEdges.length === 0) {{ emptyEl.style.display='flex'; return; }}
  emptyEl.style.display = 'none';

  const ns = 'http://www.w3.org/2000/svg';
  const defs = document.createElementNS(ns,'defs');
  const mk = document.createElementNS(ns,'marker');
  mk.setAttribute('id','arrow-calls'); mk.setAttribute('viewBox','0 -5 10 10');
  mk.setAttribute('refX','22'); mk.setAttribute('refY','0');
  mk.setAttribute('markerWidth','6'); mk.setAttribute('markerHeight','6');
  mk.setAttribute('orient','auto');
  const mp = document.createElementNS(ns,'path');
  mp.setAttribute('d','M0,-5L10,0L0,5'); mp.setAttribute('fill','#d97706');
  mk.appendChild(mp); defs.appendChild(mk);
  const mk2 = document.createElementNS(ns,'marker');
  mk2.setAttribute('id','arrow-dep'); mk2.setAttribute('viewBox','0 -5 10 10');
  mk2.setAttribute('refX','22'); mk2.setAttribute('refY','0');
  mk2.setAttribute('markerWidth','6'); mk2.setAttribute('markerHeight','6');
  mk2.setAttribute('orient','auto');
  const mp2 = document.createElementNS(ns,'path');
  mp2.setAttribute('d','M0,-5L10,0L0,5'); mp2.setAttribute('fill','#58a6ff');
  mk2.appendChild(mp2); defs.appendChild(mk2); svg.appendChild(defs);

  const d3svg = d3.select(svg)
    .attr('width',  W).attr('height', H)
    .attr('viewBox', `0 0 ${{W}} ${{H}}`)
    .style('width','100%').style('height','100%');
  const g     = d3svg.append('g');
  d3svg.call(d3.zoom().scaleExtent([0.3,3]).on('zoom',e=>g.attr('transform',e.transform)));

  const maxCnt = Math.max(...nodes.map(n=>n.repoCount),1);
  const rScale = d3.scaleSqrt().domain([0,maxCnt]).range([18,50]);

  const simNodes = nodes.map(n=>({{...n}}));
  const simEdges = edges.map(e=>({{...e,
    source:simNodes.find(n=>n.name===e.source)||e.source,
    target:simNodes.find(n=>n.name===e.target)||e.target}}));

  _simulation = d3.forceSimulation(simNodes)
    .force('link', d3.forceLink(simEdges).id(n=>n.name).distance(160).strength(0.4))
    .force('charge', d3.forceManyBody().strength(-400))
    .force('center', d3.forceCenter(W/2,H/2))
    .force('collide', d3.forceCollide(n=>rScale(n.repoCount)+12));

  const link = g.append('g').selectAll('line').data(simEdges).join('line')
    .attr('stroke',e=>e.type==='depends_on'?'#58a6ff':'#d97706')
    .attr('stroke-width',e=>Math.max(1,Math.log1p(e.weight)*2))
    .attr('stroke-dasharray',e=>e.type==='depends_on'?'6 3':null)
    .attr('marker-end',e=>e.type==='depends_on'?'url(#arrow-dep)':'url(#arrow-calls)')
    .attr('opacity',0.7)
    .on('mouseenter',(ev,e)=>showTooltip(ev,e.type))
    .on('mouseleave',hideTooltip);

  const node = g.append('g').selectAll('g').data(simNodes).join('g')
    .attr('cursor','pointer')
    .on('click',(ev,d)=>{{
      _connState={{level:'service',domain:d.name}};
      document.getElementById('conn-back').classList.add('visible');
      document.getElementById('conn-title').textContent = d.name;
      renderServiceGraph(d.name);
    }});

  node.call(d3.drag()
    .on('start',(ev,d)=>{{if(!ev.active)_simulation.alphaTarget(0.3).restart();d.fx=d.x;d.fy=d.y;}})
    .on('drag', (ev,d)=>{{d.fx=ev.x;d.fy=ev.y;}})
    .on('end',  (ev,d)=>{{if(!ev.active)_simulation.alphaTarget(0);d.fx=null;d.fy=null;}}));

  node.append('circle')
    .attr('r',d=>rScale(d.repoCount))
    .attr('fill','#1c2128').attr('stroke','#58a6ff').attr('stroke-width',1.5);

  node.append('text').attr('text-anchor','middle').attr('dy','0.35em')
    .attr('fill','#e6edf3').attr('pointer-events','none')
    .attr('font-size',d=>Math.min(12,rScale(d.repoCount)*0.4)+'px')
    .text(d=>d.name.replace(/^[0-9]+[.][ ]*/,''));

  node.append('text').attr('text-anchor','middle')
    .attr('dy',d=>rScale(d.repoCount)+14)
    .attr('fill','#8b949e').attr('font-size','10px').attr('pointer-events','none')
    .text(d=>d.repoCount?d.repoCount+' repos':'');

  // Edge labels — background rect + text at midpoint
  const edgeLabelG = g.append('g').attr('pointer-events','none');
  const edgeLabelBg = edgeLabelG.selectAll('rect').data(simEdges).join('rect')
    .attr('rx',3).attr('ry',3).attr('height',14)
    .attr('fill','#0d1117').attr('opacity',0.75);
  const edgeLabelTx = edgeLabelG.selectAll('text').data(simEdges).join('text')
    .attr('text-anchor','middle').attr('dominant-baseline','middle')
    .attr('font-size','9px').attr('font-weight','600')
    .attr('fill',e=>e.type==='depends_on'?'#58a6ff':'#d97706')
    .text(e=>e.type);
  // measure text width after creation so we can size the background rect
  edgeLabelTx.each(function(e) {{
    try {{ e._tw = this.getBBox().width + 6; }} catch(_) {{ e._tw = 80; }}
  }});
  edgeLabelBg.attr('width',e=>e._tw||80);

  _simulation.on('tick',()=>{{
    link.attr('x1',e=>e.source.x).attr('y1',e=>e.source.y)
        .attr('x2',e=>e.target.x).attr('y2',e=>e.target.y);
    node.attr('transform',d=>`translate(${{d.x}},${{d.y}})`);
    edgeLabelTx
      .attr('x',e=>(e.source.x+e.target.x)/2)
      .attr('y',e=>(e.source.y+e.target.y)/2);
    edgeLabelBg
      .attr('x',e=>(e.source.x+e.target.x)/2-(e._tw||80)/2)
      .attr('y',e=>(e.source.y+e.target.y)/2-7);
  }});
}}

/* ── Service-level D3 force graph ──────────────────────────── */
function renderServiceGraph(domainName) {{
  if (_simulation) _simulation.stop();
  const wrap = document.getElementById('conn-svg-wrap');
  const svg  = document.getElementById('conn-svg');
  const rect = wrap.getBoundingClientRect();
  // Fallback: viewport minus fixed panels (topbar 48px; map/mid hidden in connections mode)
  const W = rect.width  > 10 ? rect.width  : (window.innerWidth  - 2);
  const H = rect.height > 10 ? rect.height : (window.innerHeight - 90);
  svg.innerHTML = '';
  document.getElementById('conn-empty').style.display = 'none';

  const {{nodes,edges}} = buildServiceGraph(domainName);
  if (nodes.length === 0) {{ document.getElementById('conn-empty').style.display='flex'; return; }}

  const ns = 'http://www.w3.org/2000/svg';
  const defs = document.createElementNS(ns,'defs');
  const mk = document.createElementNS(ns,'marker');
  mk.setAttribute('id','arrow-svc'); mk.setAttribute('viewBox','0 -5 10 10');
  mk.setAttribute('refX','18'); mk.setAttribute('refY','0');
  mk.setAttribute('markerWidth','6'); mk.setAttribute('markerHeight','6');
  mk.setAttribute('orient','auto');
  const mp = document.createElementNS(ns,'path');
  mp.setAttribute('d','M0,-5L10,0L0,5'); mp.setAttribute('fill','#d97706');
  mk.appendChild(mp); defs.appendChild(mk); svg.appendChild(defs);

  const d3svg = d3.select(svg)
    .attr('width',  W).attr('height', H)
    .attr('viewBox', `0 0 ${{W}} ${{H}}`)
    .style('width','100%').style('height','100%');
  const g     = d3svg.append('g');
  d3svg.call(d3.zoom().scaleExtent([0.2,4]).on('zoom',e=>g.attr('transform',e.transform)));

  const maxScore = Math.max(...nodes.map(n=>n.health_score||0),1);
  const rScale   = d3.scaleSqrt().domain([0,maxScore]).range([10,28]);

  const simNodes = nodes.map(n=>({{...n}}));
  const idToSim  = {{}};
  simNodes.forEach(n=>idToSim[n.id]=n);

  const simEdges = edges
    .filter(e=>idToSim[e.source]&&idToSim[e.target])
    .map(e=>({{...e,source:idToSim[e.source],target:idToSim[e.target]}}));

  _simulation = d3.forceSimulation(simNodes)
    .force('link', d3.forceLink(simEdges).id(n=>n.id).distance(100).strength(0.5))
    .force('charge', d3.forceManyBody().strength(-250))
    .force('center', d3.forceCenter(W/2,H/2))
    .force('collide', d3.forceCollide(n=>rScale(n.health_score||0)+8));

  const link = g.append('g').selectAll('line').data(simEdges).join('line')
    .attr('stroke',e=>e.type==='depends_on'?'#58a6ff':'#d97706')
    .attr('stroke-width',1.5)
    .attr('stroke-dasharray',e=>e.type==='depends_on'?'5 3':null)
    .attr('marker-end',e=>e.type==='depends_on'?'url(#arrow-dep)':'url(#arrow-svc)')
    .attr('opacity',0.6)
    .on('mouseenter',(ev,e)=>showTooltip(ev,e.detail||e.type))
    .on('mouseleave',hideTooltip);

  const node = g.append('g').selectAll('g').data(simNodes).join('g')
    .attr('cursor','pointer')
    .on('click',(ev,d)=>{{if(d.url)window.open(d.url,'_blank');}});

  node.call(d3.drag()
    .on('start',(ev,d)=>{{if(!ev.active)_simulation.alphaTarget(0.3).restart();d.fx=d.x;d.fy=d.y;}})
    .on('drag', (ev,d)=>{{d.fx=ev.x;d.fy=ev.y;}})
    .on('end',  (ev,d)=>{{if(!ev.active)_simulation.alphaTarget(0);d.fx=null;d.fy=null;}}));

  node.append('circle')
    .attr('r',d=>rScale(d.health_score||0))
    .attr('fill',d=>d.isNeighbour?'#21262d':'#1c2128')
    .attr('stroke',d=>d.isNeighbour?'#484f58':tierCol(d.health_tier))
    .attr('stroke-width',d=>d.isNeighbour?1:confStroke(d.confidence))
    .attr('stroke-dasharray',d=>d.isNeighbour?'4 2':null);

  node.append('text').attr('text-anchor','middle')
    .attr('dy',d=>rScale(d.health_score||0)+12)
    .attr('fill',d=>d.isNeighbour?'#484f58':'#8b949e')
    .attr('font-size','9px').attr('pointer-events','none')
    .text(d=>d.name.length>20?d.name.slice(0,18)+'…':d.name);

  node.filter(d=>d.isNeighbour).append('text')
    .attr('text-anchor','middle')
    .attr('dy',d=>rScale(d.health_score||0)+22)
    .attr('fill','#484f58').attr('font-size','8px').attr('pointer-events','none')
    .text(d=>(d.domain||'').replace(/^[0-9]+[.][ ]*/,'').slice(0,20));

  // Edge labels for service graph
  const svcLabelG  = g.append('g').attr('pointer-events','none');
  const svcLabelBg = svcLabelG.selectAll('rect').data(simEdges).join('rect')
    .attr('rx',3).attr('ry',3).attr('height',13)
    .attr('fill','#0d1117').attr('opacity',0.8);
  const svcLabelTx = svcLabelG.selectAll('text').data(simEdges).join('text')
    .attr('text-anchor','middle').attr('dominant-baseline','middle')
    .attr('font-size','8px').attr('font-weight','600')
    .attr('fill',e=>e.type==='depends_on'?'#58a6ff':'#d97706')
    .text(e=>e.type);
  svcLabelTx.each(function(e) {{
    try {{ e._tw = this.getBBox().width + 6; }} catch(_) {{ e._tw = 60; }}
  }});
  svcLabelBg.attr('width',e=>e._tw||60);

  _simulation.on('tick',()=>{{
    link.attr('x1',e=>e.source.x).attr('y1',e=>e.source.y)
        .attr('x2',e=>e.target.x).attr('y2',e=>e.target.y);
    node.attr('transform',d=>`translate(${{d.x}},${{d.y}})`);
    svcLabelTx
      .attr('x',e=>(e.source.x+e.target.x)/2)
      .attr('y',e=>(e.source.y+e.target.y)/2);
    svcLabelBg
      .attr('x',e=>(e.source.x+e.target.x)/2-(e._tw||60)/2)
      .attr('y',e=>(e.source.y+e.target.y)/2-6.5);
  }});
}}

/* ── Resize ─────────────────────────────────────────────────── */
let _resizeTimer = null;
window.addEventListener('resize',()=>{{
  if (_currentView!=='connections') return;
  clearTimeout(_resizeTimer);
  _resizeTimer = setTimeout(()=>initConnections(),150);
}});

init();
renderBreadcrumb();
</script>
</body>
</html>"""

    path.write_text(html)
    return path



# ── main ──────────────────────────────────────────────────────────────────────

def main():
    if not Path("output/repo_health.json").exists():
        print("ERROR: Run discovery first: .venv/bin/python -m discovery.main")
        sys.exit(1)

    try:
        clf = Classifier()
    except RuntimeError as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    fetcher = FileFetcher(_github_token())

    repos   = load_repos()
    targets = select_repos(repos, ALL_MODE, TOP_N)

    already = sum(1 for r in targets if cached(r["full_name"]))
    todo    = len(targets) - already
    scope   = "all" if ALL_MODE else f"top {TOP_N}"
    print(f"\nScope: {scope}  →  {len(targets)} repos  ({already} cached, {todo} to classify)\n")

    OUT_DIR.mkdir(exist_ok=True)

    results: list[dict] = []
    counter = [0]
    token = _github_token()

    def _analyze_and_track(repo: dict) -> dict:
        result = analyze(repo, clf, token)
        clf_result = result["classification"]
        hit = " [cached]" if result.get("_cached") else ""
        with _print_lock:   # only holds lock for print — no nested _log() call
            counter[0] += 1
            print(f"  [{counter[0]:>4}/{len(targets)}] {repo['full_name']:<50}"
                  f"  {clf_result.get('subdomain','?'):<22}  ({clf_result.get('confidence','?')}){hit}",
                  flush=True)
        return result

    if todo == 0:
        results = [analyze(r, clf, token) for r in targets]
    else:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            futures = {pool.submit(_analyze_and_track, r): r for r in targets}
            for fut in as_completed(futures):
                try:
                    results.append(fut.result())
                except Exception as e:
                    _log(f"  ! error: {e}")

    # Fetch GitHub team → repo ownership (use cache if available)
    token = _github_token()
    orgs  = list({r["full_name"].split("/")[0] for r in targets})
    team_map: dict[str, list[str]] = {}
    if token:
        gh = GitHubScanner(token)
        for org in orgs:
            team_cache = CACHE / f"teams_{org}.json"
            if team_cache.exists():
                org_teams = json.loads(team_cache.read_text())
                print(f"\nTeams for {org}: loaded from cache ({len(org_teams)} mappings)")
            else:
                print(f"\nFetching GitHub teams for {org}...")
                org_teams = gh.fetch_teams(org)
                team_cache.write_text(json.dumps(org_teams, indent=2))
                print(f"  {len(org_teams)} mappings cached → {team_cache}")
            for repo, teams in org_teams.items():
                team_map.setdefault(repo, []).extend(teams)

    graph      = build_graph(results, team_map)
    graph_path = OUT_DIR / "architecture-graph.json"
    graph_path.write_text(json.dumps(graph, indent=2))

    findings_path = write_findings(results, graph)
    viewer_path   = write_viewer(graph)

    teams_count = graph["meta"].get("teams", 0)
    print(f"\nOutputs → {OUT_DIR}/")
    print(f"  {graph_path}  ({graph['meta']['pilot_repos']} repos, {teams_count} teams)")
    print(f"  {findings_path}")
    print(f"  {viewer_path}")


if __name__ == "__main__":
    main()
