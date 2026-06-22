import base64
import re
from typing import Optional

import requests

PRIORITY_FILES = [
    # Documentation
    "README.md", "readme.md", "README.rst",
    # Build manifests — root level
    "pom.xml", "package.json", "build.gradle",
    "requirements.txt", "go.mod",
    # Containers
    "Dockerfile",
    # Ownership
    ".github/CODEOWNERS",
    # Spring config
    "src/main/resources/application.yml",
    "src/main/resources/application.properties",
    # API specs
    "openapi.yaml", "swagger.yaml",
    "api/openapi.yaml", "docs/api.yaml",
    # Helm / Kubernetes (if used, these expose service URLs in env vars)
    "helm/values.yaml",
    "helm/values-prod.yaml",
    "helm/values-production.yaml",
    "helm/values-staging.yaml",
    "k8s/deployment.yaml",
    "k8s/values.yaml",
    "kubernetes/deployment.yaml",
    "deploy/deployment.yaml",
    "docker-compose.yml",
    "docker-compose.yaml",
]

# Files to look for one level into subdirectories (monorepo / sub-module patterns)
SUBDIR_FILES = [
    "pom.xml",
    "package.json",
    "build.gradle",
    "src/main/resources/application.yml",
    "src/main/resources/application.properties",
]

MAX_CHARS_PER_FILE = 3000
MAX_TOTAL_CHARS    = 16000  # raised slightly to accommodate more signal files
MAX_SUBDIR_MATCHES = 3      # cap per file type to avoid huge monorepos


class FileFetcher:
    def __init__(self, token: str):
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github.v3+json",
        })

    def fetch_signals(self, full_name: str) -> dict[str, str]:
        """
        1. Fetch the repo file tree in one API call.
        2. Check PRIORITY_FILES at root and known paths.
        3. Scan tree for build/config files one level into subdirectories.
        """
        existing = self._file_tree(full_name)
        results: dict[str, str] = {}
        total = 0

        # ── Priority files (root + explicit paths) ────────────────────────────
        for path in PRIORITY_FILES:
            if total >= MAX_TOTAL_CHARS:
                break
            if existing is not None and path not in existing:
                continue
            content = self._fetch_file(full_name, path)
            if content:
                chunk = content[:MAX_CHARS_PER_FILE]
                results[path] = chunk
                total += len(chunk)

        # ── Subdirectory scan: look for build/config files one level deep ─────
        if existing is not None and total < MAX_TOTAL_CHARS:
            for target_fname in SUBDIR_FILES:
                # Match paths like "backend/pom.xml" or "app/src/main/resources/application.yml"
                # "one level deep" = exactly one directory prefix before the target pattern
                suffix = "/" + target_fname
                candidates = sorted(
                    p for p in existing
                    if p.endswith(suffix)
                    and p.count("/") == target_fname.count("/") + 1  # one extra dir
                    and p not in results                              # not already fetched
                )
                for path in candidates[:MAX_SUBDIR_MATCHES]:
                    if total >= MAX_TOTAL_CHARS:
                        break
                    content = self._fetch_file(full_name, path)
                    if content:
                        chunk = content[:MAX_CHARS_PER_FILE]
                        results[path] = chunk
                        total += len(chunk)

        return results

    def _file_tree(self, full_name: str) -> Optional[set[str]]:
        """Return the set of all file paths in the repo, or None if unreachable."""
        try:
            resp = self.session.get(
                f"https://api.github.com/repos/{full_name}/git/trees/HEAD",
                params={"recursive": "1"},
                timeout=15,
            )
            if resp.status_code != 200:
                return None
            data = resp.json()
            if data.get("truncated"):
                return None
            return {item["path"] for item in data.get("tree", []) if item["type"] == "blob"}
        except Exception:
            return None

    def _fetch_file(self, full_name: str, path: str) -> Optional[str]:
        try:
            resp = self.session.get(
                f"https://api.github.com/repos/{full_name}/contents/{path}",
                timeout=10,
            )
            if resp.status_code != 200:
                return None
            data = resp.json()
            if isinstance(data, list):
                return None
            if data.get("encoding") == "base64":
                return base64.b64decode(data["content"]).decode("utf-8", errors="replace")
        except Exception:
            pass
        return None
