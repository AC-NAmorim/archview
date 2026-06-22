# Relationship Extraction — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce `scripts/extract_relationships.py` that reads `architecture-graph.json`, fetches build files for ~400 active repos in parallel, extracts Maven/Spring/npm dependency edges, merges them into `architecture-graph.json`, and generates per-domain Mermaid diagrams plus a `connections.js` sidecar for the D3 Connections tab in `index.html`.

**Architecture:** Single standalone script following the same module-as-script pattern as `scripts/pilot.py`. Pure parsing helpers are isolated in `scripts/extract_relationships.py` (no separate module). Tests live in `tests/test_extract_relationships.py`. The script reads from and writes to `architecture-overview/` (same output dir as pilot.py). It implements its own uncapped file fetcher (bypassing FileFetcher's 3 KB truncation cap) to avoid dropping dependency blocks from large pom.xml files.

**Tech Stack:** Python 3.12, `defusedxml` (safe XML — replaces stdlib ET which is vulnerable to XXE/billion-laughs), `re`, `json`, `pathlib`, `concurrent.futures`, `argparse`, `threading`, `requests`, `pytest`.

---

## Prerequisites

- `architecture-overview/architecture-graph.json` is populated (pilot.py has been run)
- `architecture-overview/.cache/` exists with classification entries
- `.venv` is present with `requests` and `python-dotenv` installed
- `GITHUB_TOKEN` or `gh` CLI is available

---

## Task 0 — Scaffold

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/test_extract_relationships.py` (empty)
- Create: `scripts/extract_relationships.py` (stub)

- [ ] Create `tests/` and `tests/__init__.py`:
  ```bash
  mkdir -p tests && touch tests/__init__.py
  ```
- [ ] Create the stub module:
  ```python
  # scripts/extract_relationships.py
  """
  Extract architectural dependency edges from active repo build files.

  Usage:
      .venv/bin/python -m scripts.extract_relationships
      .venv/bin/python -m scripts.extract_relationships --from-cache
      .venv/bin/python -m scripts.extract_relationships --edges-only
  """
  ```
- [ ] Verify import works:
  ```bash
  .venv/bin/python -c "import scripts.extract_relationships"
  # Expect: exits 0 with no output
  ```
- [ ] Commit:
  ```bash
  git add scripts/extract_relationships.py tests/ && git commit -m "chore: scaffold extract_relationships and tests dir"
  ```

---

## Task 1 — Write failing tests for pure parsing helpers (TDD Red)

**Files:**
- Write: `tests/test_extract_relationships.py`

- [ ] Write all unit tests (expect ImportError — Red phase):

```python
"""
Unit tests for extract_relationships.py pure parsing functions.
No GitHub API calls — only pure functions tested here.
"""
import pytest
from scripts.extract_relationships import (
    parse_coord_map_entry,
    extract_maven_deps,
    extract_spring_urls,
    extract_npm_deps,
    deduplicate_edges,
)

INTERNAL_PREFIXES = ("com.agilecontent", "com.agiletv")

# ── parse_coord_map_entry ──────────────────────────────────────────────────────

class TestParseCoordMapEntry:
    def test_returns_coord_for_valid_internal_group(self):
        pom = """
        <project>
          <groupId>com.agilecontent</groupId>
          <artifactId>common-lib</artifactId>
        </project>
        """
        assert parse_coord_map_entry(pom) == "com.agilecontent:common-lib"

    def test_strips_parent_block_before_reading_group(self):
        pom = """
        <project>
          <parent>
            <groupId>com.agilecontent</groupId>
            <artifactId>agile-java-base</artifactId>
          </parent>
          <artifactId>ingest-service</artifactId>
          <groupId>com.agiletv</groupId>
        </project>
        """
        assert parse_coord_map_entry(pom) == "com.agiletv:ingest-service"

    def test_returns_none_for_external_group(self):
        pom = """
        <project>
          <groupId>org.springframework.boot</groupId>
          <artifactId>spring-boot-starter</artifactId>
        </project>
        """
        assert parse_coord_map_entry(pom) is None

    def test_returns_none_for_empty_pom(self):
        assert parse_coord_map_entry("") is None

    def test_returns_none_for_malformed_xml(self):
        assert parse_coord_map_entry("<project><groupId>unclosed") is None

    def test_agiletv_prefix_accepted(self):
        pom = """
        <project>
          <groupId>com.agiletv</groupId>
          <artifactId>player-sdk</artifactId>
        </project>
        """
        assert parse_coord_map_entry(pom) == "com.agiletv:player-sdk"


# ── extract_maven_deps ─────────────────────────────────────────────────────────

COORD_MAP = {
    "com.agilecontent:common-lib": "repo:agilecontent/common-lib",
    "com.agiletv:player-sdk": "repo:agiletv/player-sdk",
}

class TestExtractMavenDeps:
    def test_extracts_matching_internal_dependency(self):
        pom = """
        <project>
          <groupId>com.agilecontent</groupId>
          <artifactId>ingest-service</artifactId>
          <dependencies>
            <dependency>
              <groupId>com.agilecontent</groupId>
              <artifactId>common-lib</artifactId>
              <version>2.1.0</version>
            </dependency>
          </dependencies>
        </project>
        """
        edges = extract_maven_deps("repo:agilecontent/ingest-service", pom, COORD_MAP)
        assert len(edges) == 1
        e = edges[0]
        assert e["source"] == "repo:agilecontent/ingest-service"
        assert e["target"] == "repo:agilecontent/common-lib"
        assert e["type"] == "depends_on"
        assert e["confidence"] == "high"
        assert "pom.xml" in e["evidence"]

    def test_skips_self_edge(self):
        pom = """
        <project>
          <groupId>com.agilecontent</groupId>
          <artifactId>common-lib</artifactId>
          <dependencies>
            <dependency>
              <groupId>com.agilecontent</groupId>
              <artifactId>common-lib</artifactId>
            </dependency>
          </dependencies>
        </project>
        """
        edges = extract_maven_deps("repo:agilecontent/common-lib", pom, COORD_MAP)
        assert edges == []

    def test_skips_agile_java_base(self):
        base_map = {"com.agilecontent:agile-java-base": "repo:agilecontent/agile-java-base"}
        pom = """
        <project>
          <groupId>com.agilecontent</groupId>
          <artifactId>ingest-service</artifactId>
          <dependencies>
            <dependency>
              <groupId>com.agilecontent</groupId>
              <artifactId>agile-java-base</artifactId>
            </dependency>
          </dependencies>
        </project>
        """
        edges = extract_maven_deps("repo:agilecontent/ingest-service", pom, base_map)
        assert edges == []

    def test_skips_unknown_coord(self):
        pom = """
        <project>
          <dependencies>
            <dependency>
              <groupId>com.agilecontent</groupId>
              <artifactId>nonexistent-lib</artifactId>
            </dependency>
          </dependencies>
        </project>
        """
        edges = extract_maven_deps("repo:agilecontent/ingest-service", pom, COORD_MAP)
        assert edges == []

    def test_returns_empty_for_malformed_xml(self):
        edges = extract_maven_deps("repo:agilecontent/foo", "<broken>", COORD_MAP)
        assert edges == []

    def test_version_stored_in_detail(self):
        pom = """
        <project>
          <dependencies>
            <dependency>
              <groupId>com.agilecontent</groupId>
              <artifactId>common-lib</artifactId>
              <version>3.0.0</version>
            </dependency>
          </dependencies>
        </project>
        """
        edges = extract_maven_deps("repo:agilecontent/ingest-service", pom, COORD_MAP)
        assert edges[0]["detail"] == "com.agilecontent:common-lib:3.0.0"


# ── extract_spring_urls ────────────────────────────────────────────────────────

REPO_NAMES = [
    "agilecontent/cms-api",
    "agiletv/cms-api",
    "agilecontent/user-service",
]

class TestExtractSpringUrls:
    def test_extracts_http_url_hostname(self):
        content = "cms.url: http://cms-api:8080/api/v1\n"
        edges = extract_spring_urls(
            "repo:agilecontent/ingest-service", content, REPO_NAMES, "application.yml"
        )
        assert len(edges) == 1
        assert edges[0]["target"] in ("repo:agilecontent/cms-api", "repo:agiletv/cms-api")
        assert edges[0]["type"] == "calls"
        assert edges[0]["confidence"] == "medium"

    def test_extracts_https_url(self):
        content = "url: https://user-service/api\n"
        edges = extract_spring_urls(
            "repo:agilecontent/ingest-service", content, REPO_NAMES, "application.properties"
        )
        assert any(e["target"] == "repo:agilecontent/user-service" for e in edges)

    def test_handles_spring_placeholder_syntax(self):
        content = "url: ${USER_SERVICE_URL:http://user-service:8080}\n"
        edges = extract_spring_urls(
            "repo:agilecontent/ingest-service", content, REPO_NAMES, "application.yml"
        )
        assert any("user-service" in e["target"] for e in edges)

    def test_skips_self_reference(self):
        content = "url: http://ingest-service:8080/health\n"
        edges = extract_spring_urls(
            "repo:agilecontent/ingest-service", content, REPO_NAMES, "application.yml"
        )
        assert all(e["target"] != "repo:agilecontent/ingest-service" for e in edges)

    def test_ignores_external_urls(self):
        content = "url: https://api.example.com/v2\n"
        edges = extract_spring_urls(
            "repo:agilecontent/ingest-service", content, REPO_NAMES, "application.yml"
        )
        assert edges == []

    def test_detail_contains_full_url(self):
        content = "url: http://cms-api:8080/api\n"
        edges = extract_spring_urls(
            "repo:agilecontent/ingest-service", content, REPO_NAMES, "application.yml"
        )
        assert edges[0]["detail"].startswith("http://cms-api")


# ── extract_npm_deps ───────────────────────────────────────────────────────────

NPM_REPO_NAMES = [
    "agilecontent/player-sdk",
    "agiletv/player-sdk",
    "agilecontent/ui-components",
]

class TestExtractNpmDeps:
    def test_extracts_scoped_agilecontent_dep(self):
        pkg = '{"dependencies": {"@agilecontent/player-sdk": "^1.2.3"}}'
        edges = extract_npm_deps("repo:agilecontent/frontend", pkg, NPM_REPO_NAMES)
        assert len(edges) == 1
        assert edges[0]["target"] in ("repo:agilecontent/player-sdk", "repo:agiletv/player-sdk")
        assert edges[0]["type"] == "depends_on"
        assert edges[0]["confidence"] == "high"
        assert "package.json" in edges[0]["evidence"]

    def test_extracts_scoped_agiletv_dep(self):
        pkg = '{"devDependencies": {"@agiletv/ui-components": "^2.0.0"}}'
        edges = extract_npm_deps("repo:agilecontent/frontend", pkg, NPM_REPO_NAMES)
        assert len(edges) == 1
        assert "ui-components" in edges[0]["target"]

    def test_skips_self_edge(self):
        pkg = '{"dependencies": {"@agilecontent/player-sdk": "1.0.0"}}'
        edges = extract_npm_deps("repo:agilecontent/player-sdk", pkg, NPM_REPO_NAMES)
        assert edges == []

    def test_ignores_non_internal_scopes(self):
        pkg = '{"dependencies": {"@angular/core": "^15.0.0", "lodash": "4.17"}}'
        edges = extract_npm_deps("repo:agilecontent/frontend", pkg, NPM_REPO_NAMES)
        assert edges == []

    def test_returns_empty_for_malformed_json(self):
        edges = extract_npm_deps("repo:agilecontent/frontend", "{broken json", NPM_REPO_NAMES)
        assert edges == []

    def test_includes_both_dependencies_and_dev_dependencies(self):
        pkg = """{
          "dependencies": {"@agilecontent/player-sdk": "1.0.0"},
          "devDependencies": {"@agilecontent/ui-components": "2.0.0"}
        }"""
        edges = extract_npm_deps("repo:agilecontent/frontend", pkg, NPM_REPO_NAMES)
        assert len(edges) == 2


# ── deduplicate_edges ──────────────────────────────────────────────────────────

class TestDeduplicateEdges:
    def test_keeps_single_edge_unchanged(self):
        edges = [{"source": "a", "target": "b", "type": "depends_on",
                  "confidence": "high", "evidence": ["pom.xml"], "detail": "x:y:1.0"}]
        assert len(deduplicate_edges(edges)) == 1

    def test_deduplicates_by_source_target_type(self):
        edges = [
            {"source": "a", "target": "b", "type": "depends_on",
             "confidence": "medium", "evidence": ["application.yml"], "detail": "url"},
            {"source": "a", "target": "b", "type": "depends_on",
             "confidence": "high", "evidence": ["pom.xml"], "detail": "x:y"},
        ]
        result = deduplicate_edges(edges)
        assert len(result) == 1
        assert result[0]["confidence"] == "high"

    def test_merges_evidence_arrays(self):
        edges = [
            {"source": "a", "target": "b", "type": "calls",
             "confidence": "medium", "evidence": ["application.yml"], "detail": "u"},
            {"source": "a", "target": "b", "type": "calls",
             "confidence": "medium", "evidence": ["application.properties"], "detail": "u"},
        ]
        result = deduplicate_edges(edges)
        assert set(result[0]["evidence"]) == {"application.yml", "application.properties"}

    def test_different_types_not_merged(self):
        edges = [
            {"source": "a", "target": "b", "type": "depends_on",
             "confidence": "high", "evidence": ["pom.xml"], "detail": "x"},
            {"source": "a", "target": "b", "type": "calls",
             "confidence": "medium", "evidence": ["application.yml"], "detail": "url"},
        ]
        assert len(deduplicate_edges(edges)) == 2
```

- [ ] Run tests to confirm Red (ImportError expected):
  ```bash
  .venv/bin/python -m pytest tests/test_extract_relationships.py -v 2>&1 | head -20
  ```
  Expected: `ImportError: cannot import name 'parse_coord_map_entry'`

---

## Task 2 — Implement pure parsing helpers (TDD Green)

**Files:**
- Modify: `scripts/extract_relationships.py`

- [ ] Add all four parsing functions + deduplication to the script:

```python
import json
import re
from typing import Optional

import defusedxml.ElementTree as ET  # safe against XXE and billion-laughs attacks

INTERNAL_GROUP_PREFIXES: tuple[str, ...] = ("com.agilecontent", "com.agiletv")
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
```

- [ ] Run tests to confirm Green:
  ```bash
  .venv/bin/python -m pytest tests/test_extract_relationships.py -v
  ```
  Expected: `25 passed`
- [ ] Commit:
  ```bash
  git add scripts/extract_relationships.py tests/test_extract_relationships.py
  git commit -m "feat: add relationship parsing helpers (TDD green)"
  ```

---

## Task 3 — Graph I/O, repo selection, and parallel file fetching

**Files:**
- Modify: `scripts/extract_relationships.py`

- [ ] Add the following (after the parsing helpers):

```python
import argparse
import base64
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests
from dotenv import load_dotenv

from discovery.config import _github_token

load_dotenv()

OUT_DIR      = Path("architecture-overview")
CACHE_DIR    = OUT_DIR / ".cache"
GRAPH_PATH   = OUT_DIR / "architecture-graph.json"
DIAGRAMS_DIR = OUT_DIR / "diagrams"
MAX_WORKERS  = 20
_MAX_FILE_BYTES = 65_536   # 64 KB — no truncation for full dep blocks
FETCH_FILES  = [
    "pom.xml",
    "package.json",
    "src/main/resources/application.yml",
    "src/main/resources/application.properties",
]

_print_lock  = threading.Lock()
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
    session = _get_session(token)
    tree    = _fetch_file_tree(session, full_name)
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
        with _print_lock:
            counter[0] += 1
            _log(f"  [{counter[0]:>4}/{len(repos)}] {repo['name']:<50}  "
                 f"{', '.join(files.keys()) or '(none)'}")
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
```

- [ ] Smoke test (graph only, no GitHub):
  ```bash
  .venv/bin/python -c "
  from scripts.extract_relationships import load_graph, select_active
  g = load_graph()
  active = select_active(g)
  print(f'Active repos: {len(active)}')
  assert len(active) > 100
  print('OK')
  "
  ```
- [ ] Commit: `git add scripts/extract_relationships.py && git commit -m "feat: add graph I/O and parallel file fetcher"`

---

## Task 4 — Coordinate map, edge extraction, graph update, Mermaid, and main()

**Files:**
- Modify: `scripts/extract_relationships.py`

- [ ] Add the orchestration layer:

```python
def build_coord_map(
    all_files: dict[str, dict[str, str]], repo_nodes: list[dict]
) -> dict[str, str]:
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
    RELATIONSHIP_TYPES = frozenset({"depends_on", "calls"})
    graph["edges"] = [e for e in graph["edges"] if e.get("type") not in RELATIONSHIP_TYPES]
    graph["edges"].extend(new_edges)
    return graph


def _mermaid_slug(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "_", name)


def generate_mermaid(graph: dict, edges: list[dict]) -> list[Path]:
    DIAGRAMS_DIR.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    repo_nodes   = {n["id"]: n for n in graph["nodes"] if n["type"] == "repo"}
    domain_nodes = {n["name"]: n for n in graph["nodes"] if n["type"] == "domain"}
    domain_to_repos: dict[str, list[str]] = {}
    for rn in repo_nodes.values():
        domain_to_repos.setdefault(rn.get("domain", "Unknown"), []).append(rn["id"])
    repo_to_domain = {n["id"]: n.get("domain", "Unknown") for n in repo_nodes.values()}

    # Overview
    domain_edge_counts: dict[tuple[str, str, str], int] = {}
    for e in edges:
        sd = repo_to_domain.get(e["source"])
        td = repo_to_domain.get(e["target"])
        if sd and td and sd != td:
            k = (sd, td, e["type"])
            domain_edge_counts[k] = domain_edge_counts.get(k, 0) + 1

    lines = ["# TVaaS Architecture Overview\n", "```mermaid", "flowchart LR"]
    for dn in sorted(domain_nodes):
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
    for dn in sorted(domain_nodes):
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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--from-cache", action="store_true")
    parser.add_argument("--edges-only", action="store_true")
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

    print("Extracting edges …")
    edges = extract_all_edges(active_repos, all_files, coord_map)
    print(f"  {len(edges)} edges (after dedup)\n")

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
```

- [ ] Run all tests:
  ```bash
  .venv/bin/python -m pytest tests/test_extract_relationships.py -v
  ```
  Expected: all 25+ tests pass
- [ ] Dry run using cache (no API):
  ```bash
  .venv/bin/python -m scripts.extract_relationships --from-cache --edges-only 2>&1 | tail -10
  ```
  Expected: summary block printed, no crash
- [ ] Commit: `git add scripts/extract_relationships.py && git commit -m "feat: add orchestration layer and CLI for relationship extraction"`

---

## Task 5 — Integration smoke test

- [ ] Run with cache only (safe — no API calls):
  ```bash
  .venv/bin/python -m scripts.extract_relationships --from-cache
  ```
- [ ] Check Mermaid output:
  ```bash
  ls architecture-overview/diagrams/
  # Expect: overview.md + at least 1 domain-*.md
  cat architecture-overview/diagrams/overview.md | head -30
  ```
- [ ] Verify idempotency:
  ```bash
  cp architecture-overview/architecture-graph.json /tmp/graph_first.json
  .venv/bin/python -m scripts.extract_relationships --from-cache
  diff /tmp/graph_first.json architecture-overview/architecture-graph.json
  # Expect: no diff
  ```
- [ ] Run full pipeline against GitHub (requires token, ~5 min):
  ```bash
  .venv/bin/python -m scripts.extract_relationships
  ```
  Expected summary:
  ```
  Active repos scanned:      ~400
  Repos with build files:    >60
  Edges extracted:           >20
  Diagrams written:          >5
  ```
- [ ] Commit: `git add architecture-overview/diagrams/ architecture-overview/architecture-graph.json && git commit -m "feat: first relationship extraction run"`

---

## Key Design Decisions

**Custom file fetcher (64 KB cap):** `FileFetcher` truncates at 3 KB per file. Maven pom.xml files with many dependencies easily exceed this, silently dropping dependency blocks. The extraction script uses its own `_fetch_one_file` with a 64 KB cap.

**Cache naming `{slug}_files.json`:** Avoids collision with the pilot.py classification cache (`{slug}.json`). Both live in `.cache/`.

**`--from-cache` falls back to API on miss:** Prefer-cache behaviour, not crash-on-miss.

**`agile-java-base` excluded:** Module-level constant `SKIP_ARTIFACT_TARGETS` — easy to extend.

**XML namespace handling:** Detected dynamically from root tag — handles both namespaced and bare Maven pom.xml.

**Viewer extension:** The D3 Connections tab is implemented separately in `docs/superpowers/plans/2026-06-17-d3-connections-viewer.md`. Run that plan after this one.
