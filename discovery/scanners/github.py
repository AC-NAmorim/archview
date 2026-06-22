import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Iterator

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from ..models import RepoSnapshot, SCMSource, CVEAlert

GRAPHQL_ENDPOINT = "https://api.github.com/graphql"

# One round-trip per 100 repos — fetch everything we need in a single query.
REPO_QUERY = """
query($org: String!, $cursor: String) {
  organization(login: $org) {
    repositories(first: 25, after: $cursor, isFork: false) {
      pageInfo { hasNextPage endCursor }
      nodes {
        databaseId
        name
        nameWithOwner
        url
        primaryLanguage { name }
        createdAt
        pushedAt
        isArchived
        isFork
        isPrivate
        diskUsage
        pullRequests(states: MERGED, first: 1, orderBy: {field: UPDATED_AT, direction: DESC}) {
          nodes { mergedAt }
        }
        codeowners:    object(expression: "HEAD:CODEOWNERS") { id }
        readme:        object(expression: "HEAD:README.md") { id }
        readmeLower:   object(expression: "HEAD:readme.md") { id }
        vulnerabilityAlerts(states: OPEN) { totalCount }
      }
    }
  }
  rateLimit { remaining resetAt }
}
"""


class GitHubScanner:
    def __init__(self, token: str):
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        })
        retry = Retry(
            total=5,
            backoff_factor=2,
            status_forcelist=[500, 502, 503, 504],
            allowed_methods=frozenset(["GET", "POST"]),  # GraphQL is POST
        )
        self.session.mount("https://", HTTPAdapter(max_retries=retry))

    def _graphql(self, variables: dict) -> dict:
        resp = self.session.post(GRAPHQL_ENDPOINT, json={"query": REPO_QUERY, "variables": variables})
        resp.raise_for_status()
        body = resp.json()
        if "errors" in body:
            raise RuntimeError(f"GraphQL errors: {body['errors']}")

        rate = body.get("data", {}).get("rateLimit", {})
        if rate.get("remaining", 100) < 50:
            reset = datetime.fromisoformat(rate["resetAt"].replace("Z", "+00:00"))
            wait = (reset - datetime.now(timezone.utc)).total_seconds() + 5
            if wait > 0:
                print(f"  Rate limit low, sleeping {wait:.0f}s...")
                time.sleep(wait)

        return body["data"]

    def scan_org(self, org: str) -> Iterator[RepoSnapshot]:
        cursor = None
        while True:
            data = self._graphql({"org": org, "cursor": cursor})
            org_data = data.get("organization")
            if not org_data:
                break

            conn = org_data["repositories"]
            for node in conn["nodes"]:
                yield self._parse(node, org)

            page = conn["pageInfo"]
            if not page["hasNextPage"]:
                break
            cursor = page["endCursor"]

    def _parse(self, node: dict, org: str) -> RepoSnapshot:
        # pushedAt covers any branch — a better "is anyone working here" signal
        # than defaultBranchRef which only sees main/master.
        last_commit_at = None
        if node.get("pushedAt"):
            last_commit_at = datetime.fromisoformat(node["pushedAt"].replace("Z", "+00:00"))

        last_pr_at = None
        prs = node.get("pullRequests", {}).get("nodes", [])
        if prs and prs[0].get("mergedAt"):
            last_pr_at = datetime.fromisoformat(prs[0]["mergedAt"].replace("Z", "+00:00"))

        return RepoSnapshot(
            id=str(node["databaseId"]),
            name=node["name"],
            full_name=node["nameWithOwner"],
            url=node["url"],
            source=SCMSource.GITHUB,
            org=org,
            primary_language=(
                node["primaryLanguage"]["name"] if node.get("primaryLanguage") else None
            ),
            created_at=datetime.fromisoformat(node["createdAt"].replace("Z", "+00:00")),
            is_archived=node["isArchived"],
            is_fork=node["isFork"],
            is_private=node["isPrivate"],
            size_kb=node.get("diskUsage", 0),
            last_commit_at=last_commit_at,
            last_pr_merged_at=last_pr_at,
            has_codeowners=bool(node.get("codeowners")),
            has_readme=bool(node.get("readme") or node.get("readmeLower")),
            open_security_alerts=node.get("vulnerabilityAlerts", {}).get("totalCount", 0),
        )

    def fetch_teams(self, org: str) -> dict[str, list[str]]:
        """
        Returns {repo_full_name: [team_names]} for all GitHub Teams in the org.
        Requires read:org scope — falls back to empty dict with a warning if absent.
        """
        # Check scope from a lightweight API call
        probe = self.session.get("https://api.github.com/rate_limit")
        scopes = probe.headers.get("X-OAuth-Scopes", "")
        if "read:org" not in scopes and "admin:org" not in scopes:
            print("  Warning: token lacks read:org scope — skipping GitHub Teams fetch.")
            print("           Run: gh auth refresh -s read:org  to add it.")
            return {}

        repo_to_teams: dict[str, list[str]] = {}

        try:
            teams_resp = self.session.get(
                f"https://api.github.com/orgs/{org}/teams",
                params={"per_page": 100},
            )
            if teams_resp.status_code in (403, 404):
                print(f"  Warning: cannot list teams for {org} (status {teams_resp.status_code})")
                return {}
            teams_resp.raise_for_status()
            teams = teams_resp.json()
        except Exception as e:
            print(f"  Warning: GitHub Teams fetch failed — {e}")
            return {}

        for team in teams:
            slug = team["slug"]
            name = team["name"]
            page = 1
            while True:
                try:
                    r = self.session.get(
                        f"https://api.github.com/orgs/{org}/teams/{slug}/repos",
                        params={"per_page": 100, "page": page},
                    )
                    r.raise_for_status()
                    repos = r.json()
                except Exception:
                    break
                for repo in repos:
                    repo_to_teams.setdefault(repo["full_name"], []).append(name)
                if len(repos) < 100:
                    break
                page += 1

        return repo_to_teams

    def enrich_cve(self, repos: list[RepoSnapshot]) -> None:
        """Fetch full CVE details for repos that have open alerts. Mutates in place."""
        targets = [r for r in repos if r.open_security_alerts > 0]
        if not targets:
            return

        # Build a lookup by full_name for fast update
        by_name = {r.full_name: r for r in targets}

        # Batch 20 repos per GraphQL request using aliases
        batch_size = 20
        for i in range(0, len(targets), batch_size):
            batch = targets[i : i + batch_size]
            query = self._build_cve_query(batch)
            resp = self.session.post(
                GRAPHQL_ENDPOINT,
                json={"query": query},
            )
            resp.raise_for_status()
            data = resp.json().get("data", {})

            for j, repo in enumerate(batch):
                node = data.get(f"r{j}", {}) or {}
                alerts = node.get("vulnerabilityAlerts", {}).get("nodes", [])
                repo.cve_alerts = [
                    self._parse_alert(repo.full_name, a)
                    for a in alerts
                    if a.get("securityVulnerability")
                ]

    def _build_cve_query(self, repos: list[RepoSnapshot]) -> str:
        CVE_FRAGMENT = """
          vulnerabilityAlerts(states: OPEN, first: 25) {
            nodes {
              securityVulnerability {
                severity
                package { name ecosystem }
                advisory {
                  summary
                  cvss { score }
                  identifiers { type value }
                }
              }
            }
          }
        """
        parts = []
        for i, repo in enumerate(repos):
            owner, name = repo.full_name.split("/", 1)
            parts.append(f'r{i}: repository(owner: "{owner}", name: "{name}") {{{CVE_FRAGMENT}}}')
        return "{ " + "\n".join(parts) + " }"

    def _parse_alert(self, repo_full_name: str, node: dict) -> CVEAlert:
        vuln = node["securityVulnerability"]
        pkg  = vuln.get("package", {})
        adv  = vuln.get("advisory", {})
        ids  = adv.get("identifiers", [])
        cve_id = next((i["value"] for i in ids if i.get("type") == "CVE"), None)
        return CVEAlert(
            repo_full_name=repo_full_name,
            package=pkg.get("name", "unknown"),
            ecosystem=pkg.get("ecosystem", ""),
            severity=vuln.get("severity", "UNKNOWN"),
            summary=adv.get("summary", ""),
            cvss_score=adv.get("cvss", {}).get("score"),
            cve_id=cve_id,
        )

    # ── Workflow enrichment ───────────────────────────────────────────────────

    # Keywords that indicate a workflow deploys, publishes, or ships software.
    # Intentionally broad — false positives are fine; false negatives mean we
    # might wrongly archive something still in production.
    _DEPLOY_KEYWORDS = frozenset({
        "deploy", "publish", "release", "push", "ship", "deliver",
        "docker", "helm", "k8s", "kubernetes", "image", "registry",
        "staging", "production", "prod", "cd",
    })

    def enrich_workflows(self, repos: list[RepoSnapshot]) -> None:
        """
        Fetch the last 10 GitHub Actions runs per repo.
        Detects deploy/publish workflows and records last run date + status.
        Uses per-thread sessions for concurrency safety.
        Mutates repos in place.
        """
        _tl = threading.local()

        def _session() -> requests.Session:
            if not hasattr(_tl, "s"):
                s = requests.Session()
                s.headers.update(self.session.headers)
            return _tl.s if hasattr(_tl, "s") else (_tl.__setattr__("s", requests.Session()) or _tl.s)

        def _enrich(repo: RepoSnapshot) -> None:
            token = self.session.headers.get("Authorization", "")
            if not hasattr(_tl, "s"):
                _tl.s = requests.Session()
                _tl.s.headers.update({"Authorization": token,
                                       "Accept": "application/vnd.github.v3+json"})
            s = _tl.s
            try:
                resp = s.get(
                    f"https://api.github.com/repos/{repo.full_name}/actions/runs",
                    params={"per_page": 10},
                    timeout=10,
                )
                if resp.status_code != 200:
                    return
                runs = resp.json().get("workflow_runs", [])
                if not runs:
                    return

                # Most recent run
                latest = runs[0]
                repo.last_workflow_run_at = datetime.fromisoformat(
                    latest["updated_at"].replace("Z", "+00:00")
                )
                repo.last_workflow_status = latest.get("conclusion")  # success/failure/…

                # Detect deploy intent across all recent runs
                deploy_names = []
                for run in runs:
                    name = (run.get("name") or "").lower()
                    path = (run.get("path") or "").lower()
                    if any(kw in name or kw in path for kw in self._DEPLOY_KEYWORDS):
                        wf_name = run.get("name") or run.get("path") or "unknown"
                        if wf_name not in deploy_names:
                            deploy_names.append(wf_name)

                repo.has_deploy_workflow = bool(deploy_names)
                repo.deploy_workflow_names = deploy_names[:5]  # cap for storage
            except Exception:
                pass

        with ThreadPoolExecutor(max_workers=20) as pool:
            futures = [pool.submit(_enrich, r) for r in repos]
            for fut in as_completed(futures):
                fut.result()  # surface exceptions
