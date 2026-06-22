"""
Extract architectural dependency edges from active repo build files.

Usage:
    .venv/bin/python -m scripts.extract_relationships
    .venv/bin/python -m scripts.extract_relationships --from-cache
    .venv/bin/python -m scripts.extract_relationships --edges-only
"""
import argparse
import base64
import json
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

import defusedxml.ElementTree as ET  # safe against XXE and billion-laughs attacks
import requests
from dotenv import load_dotenv

from discovery.config import _github_token

INTERNAL_GROUP_PREFIXES: tuple[str, ...] = (
    "com.agilecontent",
    "com.agiletv",
    "ctv.",          # legacy brand prefix (Contenidos TV) — covers ctv.agiletv, ctv.cadena100, etc.
    "com.ctv",       # variant used in some older repos
)
SKIP_ARTIFACT_TARGETS: frozenset[str] = frozenset({"agile-java-base"})
INTERNAL_NPM_SCOPES: tuple[str, ...] = ("@agilecontent/", "@agiletv/")


def _strip_parent_block(pom_xml: str) -> str:
    return re.sub(r"<parent>.*?</parent>", "", pom_xml, flags=re.DOTALL)


def parse_coord_map_entry(pom_xml: str) -> Optional[str]:
    if not pom_xml:
        return None
    stripped = _strip_parent_block(pom_xml)
    try:
        root = ET.fromstring(stripped)
    except ET.ParseError:
        return None
    ns_match = re.match(r"\{[^}]+\}", root.tag)
    ns = ns_match.group(0) if ns_match else ""
    gid_el = root.find(f"{ns}groupId")
    aid_el = root.find(f"{ns}artifactId")
    if gid_el is None or aid_el is None:
        return None
    gid = (gid_el.text or "").strip()
    aid = (aid_el.text or "").strip()
    if not any(gid.startswith(p) for p in INTERNAL_GROUP_PREFIXES):
        return None
    return f"{gid}:{aid}" if gid and aid else None


def extract_maven_deps(
    source_id: str, pom_xml: str, coord_map: dict[str, str]
) -> list[dict]:
    if not pom_xml:
        return []
    try:
        root = ET.fromstring(_strip_parent_block(pom_xml))
    except ET.ParseError:
        return []
    ns_match = re.match(r"\{[^}]+\}", root.tag)
    ns = ns_match.group(0) if ns_match else ""
    edges: list[dict] = []
    for dep in root.iter(f"{ns}dependency"):
        gid_el = dep.find(f"{ns}groupId")
        aid_el = dep.find(f"{ns}artifactId")
        ver_el = dep.find(f"{ns}version")
        if gid_el is None or aid_el is None:
            continue
        gid = (gid_el.text or "").strip()
        aid = (aid_el.text or "").strip()
        ver = (ver_el.text or "").strip() if ver_el is not None else ""
        if not any(gid.startswith(p) for p in INTERNAL_GROUP_PREFIXES):
            continue
        if aid in SKIP_ARTIFACT_TARGETS:
            continue
        coord = f"{gid}:{aid}"
        target_id = coord_map.get(coord)
        if target_id is None or target_id == source_id:
            continue
        detail = f"{coord}:{ver}" if ver else coord
        edges.append({"source": source_id, "target": target_id, "type": "depends_on",
                      "confidence": "high", "evidence": ["pom.xml"], "detail": detail})
    return edges


_URL_RE = re.compile(
    r"(?:\$\{[^}]*:)?(https?://([A-Za-z0-9_-]+)(?::\d+)?(?:/[^\s\"']*)?)",
    re.IGNORECASE,
)


def _normalise_hostname(hostname: str) -> str:
    for prefix in ("agiletv-", "agilecontent-"):
        if hostname.startswith(prefix):
            return hostname[len(prefix):]
    return hostname


def _find_repo_by_hostname(hostname: str, repo_names: list[str]) -> Optional[str]:
    bare = _normalise_hostname(hostname.lower())
    for full_name in repo_names:
        short = full_name.split("/")[-1].lower()
        if _normalise_hostname(short) == bare or short == bare:
            return full_name
    return None


def extract_spring_urls(
    source_id: str, content: str, repo_names: list[str], filename: str
) -> list[dict]:
    edges: list[dict] = []
    source_short = source_id.split("/")[-1].lower() if "/" in source_id else source_id.lower()
    for match in _URL_RE.finditer(content):
        full_url = match.group(1)
        hostname  = match.group(2).lower()
        if hostname in ("localhost", "127.0.0.1"):
            continue
        if _normalise_hostname(hostname) == _normalise_hostname(source_short):
            continue
        matched = _find_repo_by_hostname(hostname, repo_names)
        if not matched:
            continue
        target_id = f"repo:{matched}"
        if target_id == source_id:
            continue
        edges.append({"source": source_id, "target": target_id, "type": "calls",
                      "confidence": "medium", "evidence": [filename], "detail": full_url})
    return edges


def extract_npm_deps(
    source_id: str, package_json: str, repo_names: list[str]
) -> list[dict]:
    try:
        pkg = json.loads(package_json)
    except (json.JSONDecodeError, ValueError):
        return []
    all_deps: dict[str, str] = {}
    all_deps.update(pkg.get("dependencies") or {})
    all_deps.update(pkg.get("devDependencies") or {})
    edges: list[dict] = []
    for dep_name in all_deps:
        if not any(dep_name.startswith(s) for s in INTERNAL_NPM_SCOPES):
            continue
        pkg_short = dep_name.split("/", 1)[-1].lower()
        matched = next(
            (fn for fn in repo_names
             if _normalise_hostname(fn.split("/")[-1].lower()) == pkg_short
             or fn.split("/")[-1].lower() == pkg_short),
            None,
        )
        if not matched:
            continue
        target_id = f"repo:{matched}"
        if target_id == source_id:
            continue
        edges.append({"source": source_id, "target": target_id, "type": "depends_on",
                      "confidence": "high", "evidence": ["package.json"], "detail": dep_name})
    return edges


def deduplicate_edges(edges: list[dict]) -> list[dict]:
    _CONF_ORDER = {"high": 0, "medium": 1, "low": 2}
    seen: dict[tuple[str, str, str], dict] = {}
    for e in edges:
        key = (e["source"], e["target"], e["type"])
        if key not in seen:
            seen[key] = {**e, "evidence": list(e.get("evidence", []))}
        else:
            ex = seen[key]
            if _CONF_ORDER.get(e["confidence"], 99) < _CONF_ORDER.get(ex["confidence"], 99):
                ex["confidence"] = e["confidence"]
                ex["detail"] = e.get("detail", ex.get("detail", ""))
            for ev in e.get("evidence", []):
                if ev not in ex["evidence"]:
                    ex["evidence"].append(ev)
    return list(seen.values())


# Graph I/O and parallel file-fetching layer

load_dotenv()

OUT_DIR = Path("architecture-overview")
CACHE_DIR = OUT_DIR / ".cache"
GRAPH_PATH = OUT_DIR / "architecture-graph.json"
DIAGRAMS_DIR = OUT_DIR / "diagrams"
MAX_WORKERS = 20
_MAX_FILE_BYTES = 65_536  # 64 KB — no truncation for full dep blocks
FETCH_FILES = [
    "pom.xml",
    "package.json",
    "src/main/resources/application.yml",
    "src/main/resources/application.properties",
]

_print_lock = threading.Lock()
_thread_local = threading.local()


def _log(msg: str) -> None:
    with _print_lock:
        print(msg, flush=True)


def load_graph() -> dict:
    with GRAPH_PATH.open() as f:
        return json.load(f)


def select_active(graph: dict) -> list[dict]:
    return [
        n for n in graph["nodes"]
        if n.get("type") == "repo"
        and n.get("health_tier") not in ("dormant",)
        and "archived" not in (n.get("flags") or [])
    ]


def _files_cache_path(full_name: str) -> Path:
    return CACHE_DIR / (full_name.replace("/", "__") + "_files.json")


def _load_files_cache(full_name: str) -> Optional[dict[str, str]]:
    p = _files_cache_path(full_name)
    return json.loads(p.read_text()) if p.exists() else None


def _save_files_cache(full_name: str, files: dict[str, str]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _files_cache_path(full_name).write_text(json.dumps(files, indent=2))


def _get_session(token: str) -> requests.Session:
    if not hasattr(_thread_local, "session"):
        s = requests.Session()
        s.headers.update({"Authorization": f"Bearer {token}",
                           "Accept": "application/vnd.github.v3+json"})
        _thread_local.session = s
    return _thread_local.session


def _fetch_file_tree(session: requests.Session, full_name: str) -> Optional[set[str]]:
    try:
        resp = session.get(
            f"https://api.github.com/repos/{full_name}/git/trees/HEAD",
            params={"recursive": "1"}, timeout=15,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        if data.get("truncated"):
            return None
        return {i["path"] for i in data.get("tree", []) if i["type"] == "blob"}
    except Exception:
        return None


def _fetch_one_file(session: requests.Session, full_name: str, path: str) -> Optional[str]:
    try:
        resp = session.get(
            f"https://api.github.com/repos/{full_name}/contents/{path}", timeout=15,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        if isinstance(data, list):
            return None
        if data.get("encoding") == "base64":
            return base64.b64decode(data["content"])[:_MAX_FILE_BYTES].decode("utf-8", errors="replace")
    except Exception:
        pass
    return None


def fetch_build_files(repo_node: dict, token: str, from_cache: bool = False) -> dict[str, str]:
    full_name = repo_node["name"]
    cached = _load_files_cache(full_name)
    if cached is not None:
        return cached
    if from_cache:
        return {}   # cache miss + cache-only mode → skip this repo
    session = _get_session(token)
    tree = _fetch_file_tree(session, full_name)
    results: dict[str, str] = {}
    for path in FETCH_FILES:
        if tree is not None and path not in tree:
            continue
        content = _fetch_one_file(session, full_name, path)
        if content:
            results[path] = content
    _save_files_cache(full_name, results)
    return results


def fetch_all_build_files(
    repos: list[dict], token: str, from_cache: bool = False
) -> dict[str, dict[str, str]]:
    all_files: dict[str, dict[str, str]] = {}
    counter = [0]

    def _do(repo: dict) -> tuple[str, dict[str, str]]:
        files = fetch_build_files(repo, token, from_cache=from_cache)
        with _print_lock:                          # print directly — never call _log() inside _print_lock
            counter[0] += 1
            print(f"  [{counter[0]:>4}/{len(repos)}] {repo['name']:<50}  "
                  f"{', '.join(files.keys()) or '(none)'}", flush=True)
        return repo["name"], files

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(_do, r): r for r in repos}
        for fut in as_completed(futures):
            try:
                name, files = fut.result()
                all_files[name] = files
            except Exception as e:
                repo = futures[fut]
                _log(f"  ! {repo['name']}: {e}")
                all_files[repo["name"]] = {}
    return all_files


# Orchestration layer


def build_coord_map(
    all_files: dict[str, dict[str, str]], repo_nodes: list[dict]
) -> dict[str, str]:
    """Return {'groupId:artifactId': 'repo:org/name'} for all active repos with internal pom.xml."""
    coord_map: dict[str, str] = {}
    for node in repo_nodes:
        pom = all_files.get(node["name"], {}).get("pom.xml", "")
        if pom:
            coord = parse_coord_map_entry(pom)
            if coord:
                coord_map[coord] = f"repo:{node['name']}"
    return coord_map


def extract_all_edges(
    active_repos: list[dict],
    all_files: dict[str, dict[str, str]],
    coord_map: dict[str, str],
) -> list[dict]:
    """Run all three extractors across all active repos and return deduplicated edge list."""
    repo_names = [n["name"] for n in active_repos]
    raw: list[dict] = []
    for node in active_repos:
        full_name = node["name"]
        source_id = f"repo:{full_name}"
        files = all_files.get(full_name, {})
        if pom := files.get("pom.xml", ""):
            raw.extend(extract_maven_deps(source_id, pom, coord_map))
        for conf_file in ("src/main/resources/application.yml",
                          "src/main/resources/application.properties"):
            if content := files.get(conf_file, ""):
                raw.extend(extract_spring_urls(
                    source_id, content, repo_names, conf_file.split("/")[-1]
                ))
        if pkg := files.get("package.json", ""):
            raw.extend(extract_npm_deps(source_id, pkg, repo_names))
    return deduplicate_edges(raw)


def update_graph(graph: dict, new_edges: list[dict]) -> dict:
    """Remove prior relationship edges and append new ones. Idempotent."""
    RELATIONSHIP_TYPES = frozenset({"depends_on", "calls", "reads_writes"})
    graph["edges"] = [e for e in graph["edges"] if e.get("type") not in RELATIONSHIP_TYPES]
    graph["edges"].extend(new_edges)
    return graph


def _mermaid_slug(name: object) -> str:
    return re.sub(r"[^A-Za-z0-9]", "_", str(name))


def generate_mermaid(graph: dict, edges: list[dict]) -> list[Path]:
    """Write overview.md + per-domain Mermaid files to architecture-overview/diagrams/."""
    DIAGRAMS_DIR.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    repo_nodes   = {n["id"]: n for n in graph["nodes"] if n["type"] == "repo"}
    domain_nodes = {n["name"]: n for n in graph["nodes"]
                    if n["type"] == "domain" and isinstance(n.get("name"), str)}
    domain_to_repos: dict[str, list[str]] = {}
    for rn in repo_nodes.values():
        domain_to_repos.setdefault(rn.get("domain", "Unknown"), []).append(rn["id"])
    repo_to_domain = {n["id"]: n.get("domain", "Unknown") for n in repo_nodes.values()}

    # Overview (domain-level)
    domain_edge_counts: dict[tuple[str, str, str], int] = {}
    for e in edges:
        sd = repo_to_domain.get(e["source"])
        td = repo_to_domain.get(e["target"])
        if sd and td and sd != td:
            k = (sd, td, e["type"])
            domain_edge_counts[k] = domain_edge_counts.get(k, 0) + 1

    lines = ["# TVaaS Architecture Overview\n", "```mermaid", "flowchart LR"]
    for dn in sorted(domain_nodes, key=str):
        nid = _mermaid_slug(dn)
        cnt = len(domain_to_repos.get(dn, []))
        short = dn.split(". ", 1)[-1] if ". " in dn else dn
        lines.append(f'  {nid}["{short}\\n{cnt} repos"]')
    for (sd, td, etype), count in sorted(domain_edge_counts.items()):
        arrow = "-->" if etype == "calls" else "-.->"
        lines.append(f"  {_mermaid_slug(sd)} {arrow}|{etype} x{count}| {_mermaid_slug(td)}")
    lines.append("```")
    p = DIAGRAMS_DIR / "overview.md"
    p.write_text("\n".join(lines))
    written.append(p)

    # Per-domain
    for dn in sorted(domain_nodes, key=str):
        domain_repo_ids = set(domain_to_repos.get(dn, []))
        relevant = [e for e in edges if e["source"] in domain_repo_ids or e["target"] in domain_repo_ids]
        if not relevant:
            continue
        all_ids = domain_repo_ids | {e["source"] for e in relevant} | {e["target"] for e in relevant}
        n_prefix = dn.split(".")[0].strip()
        slug = _mermaid_slug(dn.split(". ", 1)[-1] if ". " in dn else dn).lower()
        short_dn = dn.split(". ", 1)[-1] if ". " in dn else dn
        dlines = [f"# Domain: {dn}\n", "```mermaid", "flowchart LR",
                  f'  subgraph "{short_dn}"']
        for rid in sorted(domain_repo_ids):
            if node := repo_nodes.get(rid):
                dlines.append(f'    {_mermaid_slug(rid)}["{node["name"].split("/")[-1]}"]')
        dlines.append("  end")
        for rid in sorted(all_ids - domain_repo_ids):
            if node := repo_nodes.get(rid):
                ext = repo_to_domain.get(rid, "?")
                ext_short = ext.split(". ", 1)[-1] if ". " in ext else ext
                dlines.append(f'  {_mermaid_slug(rid)}["{node["name"].split("/")[-1]} ({ext_short})"]')
        for e in relevant:
            arrow = "-->" if e["type"] == "calls" else "-.->"
            dlines.append(f"  {_mermaid_slug(e['source'])} {arrow}|{e['type']}| {_mermaid_slug(e['target'])}")
        dlines.append("```")
        out = DIAGRAMS_DIR / f"domain-{n_prefix}-{slug}.md"
        out.write_text("\n".join(dlines))
        written.append(out)
    return written


def print_summary(active, all_files, edges, graph, diagrams):
    pom_count = sum(1 for f in all_files.values() if "pom.xml" in f)
    pkg_count = sum(1 for f in all_files.values() if "package.json" in f)
    cfg_count = sum(1 for f in all_files.values()
                    if any(k.endswith(("application.yml","application.properties")) for k in f))
    dep_edges   = [e for e in edges if e["type"] == "depends_on"]
    calls_edges = [e for e in edges if e["type"] == "calls"]
    high   = sum(1 for e in edges if e["confidence"] == "high")
    medium = sum(1 for e in edges if e["confidence"] == "medium")
    low    = sum(1 for e in edges if e["confidence"] == "low")
    repo_to_domain = {n["id"]: n.get("domain","") for n in graph["nodes"] if n["type"]=="repo"}
    cross  = sum(1 for e in edges
                 if repo_to_domain.get(e["source"]) != repo_to_domain.get(e["target"])
                 and repo_to_domain.get(e["source"]) and repo_to_domain.get(e["target"]))
    print("\n" + "=" * 55)
    print(f"Active repos scanned:      {len(active)}")
    print(f"Repos with build files:    {sum(1 for f in all_files.values() if f)} "
          f"(pom.xml: {pom_count}, package.json: {pkg_count})")
    print(f"Repos with config files:   {cfg_count}")
    print(f"Edges extracted:           {len(edges)} "
          f"(depends_on: {len(dep_edges)}, calls: {len(calls_edges)})")
    print(f"High confidence:           {high} / Medium: {medium} / Low: {low}")
    print(f"Cross-domain edges:        {cross}")
    print(f"Diagrams written:          {len(diagrams)}")
    print("=" * 55)


# ── Rancher deployment config extraction ──────────────────────────────────────
#
# The devops repo holds Rancher/k8s deployment configs for all platform services.
# These expose service-to-service HTTP calls (env vars like ATHENA_URI) and
# shared infrastructure (DB_SERVER, MONGO_SERVER) — higher-signal than pom.xml.

DEVOPS_REPO        = "agilecontent/tvopenplatform-devops"
RANCHER_BASE_PATH  = "rancher-exporter"

# Environment variable patterns that indicate a dependency
_URL_PATTERNS = re.compile(
    r"https?://([A-Za-z0-9_.-]+)(?::\d+)?",
    re.IGNORECASE,
)
# Keys that indicate a shared datastore
_DB_KEYS = re.compile(
    r"(?:DB_SERVER|DB_HOST|MONGO_SERVER|REDIS_HOST|MEMCACHED|BOOTSTRAP_SERVER|KAFKA)",
    re.IGNORECASE,
)

try:
    import yaml as _yaml
    _YAML_OK = True
except ImportError:
    _YAML_OK = False


def _fetch_raw(session: "requests.Session", repo: str, path: str) -> str | None:
    """Fetch a single file from GitHub and return decoded content."""
    try:
        resp = session.get(
            f"https://api.github.com/repos/{repo}/contents/{path}", timeout=15
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        if data.get("encoding") == "base64":
            return base64.b64decode(data["content"]).decode("utf-8", errors="replace")
    except Exception:
        pass
    return None


def _normalise_service_name(name: str) -> str:
    """Strip common prefixes/suffixes to get a bare service slug."""
    return (
        name.lower()
        .replace("tvopenplatform-", "")
        .replace("agiletv-", "")
        .replace("-api", "")
        .replace("-service", "")
        .replace("-web", "")
        .strip()
    )


def _match_service_to_repo(service: str, repo_names: list[str]) -> str | None:
    """Fuzzy-match a docker-compose service name to a known repo."""
    bare = _normalise_service_name(service)
    for full_name in repo_names:
        short = _normalise_service_name(full_name.split("/")[-1])
        if short == bare or bare in short or short in bare:
            return f"repo:{full_name}"
    return None


def extract_rancher_edges(graph: dict, token: str) -> list[dict]:
    """
    Fetch Rancher docker-compose configs from the devops repo and extract:
      - calls      edges: service A uses ATHENA_URI=http://athena → A calls athena
      - reads_writes edges: services sharing the same DB_SERVER
    """
    if not _YAML_OK:
        _log("  Warning: pyyaml not installed — skipping Rancher extraction (pip install pyyaml)")
        return []

    repo_names = [n["name"] for n in graph["nodes"] if n["type"] == "repo"]

    session = requests.Session()
    session.headers.update({
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json",
    })

    # Discover all docker-compose files in rancher-exporter
    try:
        resp = session.get(
            f"https://api.github.com/repos/{DEVOPS_REPO}/git/trees/HEAD",
            params={"recursive": "1"}, timeout=15,
        )
        if resp.status_code != 200:
            _log(f"  Warning: could not access {DEVOPS_REPO} ({resp.status_code})")
            return []
        tree = [i["path"] for i in resp.json().get("tree", []) if i["type"] == "blob"]
    except Exception as e:
        _log(f"  Warning: Rancher tree fetch failed — {e}")
        return []

    compose_paths = sorted(
        p for p in tree
        if "docker-compose.yml" in p and RANCHER_BASE_PATH in p
    )
    _log(f"  Found {len(compose_paths)} Rancher compose files")

    # Parse all compose files
    db_users: dict[str, list[str]] = {}   # db_server → [service_names]
    calls_map: dict[tuple, dict] = {}     # (caller_svc, callee_svc) → edge

    for path in compose_paths:
        content = _fetch_raw(session, DEVOPS_REPO, path)
        if not content:
            continue
        try:
            data = _yaml.safe_load(content)
        except Exception:
            continue

        for svc_name, svc_cfg in (data.get("services") or {}).items():
            env = svc_cfg.get("environment") or {}
            if isinstance(env, list):
                env = {k: v for k, v in (e.split("=", 1) for e in env if "=" in e)}

            caller_id = _match_service_to_repo(svc_name, repo_names)

            for key, value in env.items():
                if not value:
                    continue
                value = str(value)

                # Shared datastore detection
                if _DB_KEYS.search(key):
                    # Extract hostname from connection strings
                    host = value.split(";")[0].split(",")[0].split(":")[0].strip()
                    if host and "." in host and host not in ("localhost", "127.0.0.1"):
                        db_users.setdefault(host, []).append(svc_name)

                # HTTP service-to-service calls
                for m in _URL_PATTERNS.finditer(value):
                    hostname = m.group(1).lower()
                    # Skip external/infrastructure hosts
                    if any(x in hostname for x in ["amazonaws", "gvp-dev.com", "localhost",
                                                    "127.0.0.1", "10.0.", "gvpdb"]):
                        continue
                    # Match hostname to a known service/repo
                    callee_id = _match_service_to_repo(hostname, repo_names)
                    if callee_id and caller_id and caller_id != callee_id:
                        edge_key = (caller_id, callee_id)
                        if edge_key not in calls_map:
                            calls_map[edge_key] = {
                                "source":     caller_id,
                                "target":     callee_id,
                                "type":       "calls",
                                "confidence": "medium",
                                "evidence":   [path],
                                "detail":     f"{key}={value[:80]}",
                            }

    # Build edges from shared DB servers (reads_writes)
    rw_edges: list[dict] = []
    for db_host, services in db_users.items():
        if len(services) < 2:
            continue
        # Create a shared datastore node label for the detail
        repo_ids = [_match_service_to_repo(s, repo_names) for s in services]
        repo_ids = [r for r in repo_ids if r]
        for i, src in enumerate(repo_ids):
            for tgt in repo_ids[i + 1:]:
                rw_edges.append({
                    "source":     src,
                    "target":     tgt,
                    "type":       "reads_writes",
                    "confidence": "high",
                    "evidence":   [DEVOPS_REPO],
                    "detail":     f"shared DB: {db_host}",
                })

    all_edges = list(calls_map.values()) + rw_edges
    _log(f"  Rancher: {len(calls_map)} calls edges, {len(rw_edges)} reads_writes edges")
    return all_edges


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract architectural dependency edges from active repo build files."
    )
    parser.add_argument("--from-cache", action="store_true",
                        help="Skip GitHub API; read from _files.json cache only.")
    parser.add_argument("--edges-only", action="store_true",
                        help="Extract edges only; skip Mermaid and viewer generation.")
    args = parser.parse_args()

    if not GRAPH_PATH.exists():
        print(f"ERROR: {GRAPH_PATH} not found. Run scripts.pilot first.")
        raise SystemExit(1)

    token = _github_token()
    if not token and not args.from_cache:
        print("ERROR: No GitHub token. Set GITHUB_TOKEN or run 'gh auth login'.")
        raise SystemExit(1)

    print("Loading graph …")
    graph = load_graph()
    print("Selecting active repos …")
    active_repos = select_active(graph)
    print(f"  {len(active_repos)} active repos\n")

    print("Fetching build files …")
    all_files = fetch_all_build_files(active_repos, token, from_cache=args.from_cache)

    print("\nBuilding coordinate map …")
    coord_map = build_coord_map(all_files, active_repos)
    print(f"  {len(coord_map)} Maven coordinates mapped\n")

    print("Extracting edges from build files …")
    edges = extract_all_edges(active_repos, all_files, coord_map)
    print(f"  {len(edges)} edges from build files\n")

    print("Extracting edges from Rancher deployment configs …")
    rancher_edges = extract_rancher_edges(graph, token) if token else []
    edges = deduplicate_edges(edges + rancher_edges)
    print(f"  {len(edges)} total edges (after dedup)\n")

    print("Updating architecture-graph.json …")
    graph = update_graph(graph, edges)
    GRAPH_PATH.write_text(json.dumps(graph, indent=2))

    diagrams: list[Path] = []
    if not args.edges_only:
        print("Generating Mermaid diagrams …")
        diagrams = generate_mermaid(graph, edges)
        print(f"  {len(diagrams)} files → {DIAGRAMS_DIR}\n")

    print_summary(active_repos, all_files, edges, graph, diagrams)


if __name__ == "__main__":
    main()
