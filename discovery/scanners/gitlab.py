import time
from datetime import datetime, timezone
from typing import Iterator

import requests

from ..models import RepoSnapshot, SCMSource


class GitLabScanner:
    def __init__(self, token: str, base_url: str = "https://gitlab.com"):
        self.base = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers["PRIVATE-TOKEN"] = token

    def _get(self, path: str, params: dict = None) -> requests.Response:
        resp = self.session.get(f"{self.base}/api/v4{path}", params=params or {})
        if resp.status_code == 429:
            wait = int(resp.headers.get("Retry-After", 60))
            print(f"  GitLab rate limited, sleeping {wait}s...")
            time.sleep(wait)
            return self._get(path, params)
        resp.raise_for_status()
        return resp

    def _paginate(self, path: str, params: dict = None) -> Iterator[dict]:
        params = {**(params or {}), "per_page": 100, "page": 1}
        while True:
            resp = self._get(path, params)
            items = resp.json()
            if not items:
                break
            yield from items
            next_page = resp.headers.get("X-Next-Page", "")
            if not next_page:
                break
            params["page"] = int(next_page)

    def scan_group(self, group_id: str) -> Iterator[RepoSnapshot]:
        for project in self._paginate(
            f"/groups/{group_id}/projects",
            {"include_subgroups": True, "with_shared": False, "statistics": True},
        ):
            yield self._parse(project, group_id)

    def _parse(self, project: dict, group: str) -> RepoSnapshot:
        last_commit_at = None
        if project.get("last_activity_at"):
            last_commit_at = datetime.fromisoformat(
                project["last_activity_at"].replace("Z", "+00:00")
            )

        return RepoSnapshot(
            id=str(project["id"]),
            name=project["name"],
            full_name=project["path_with_namespace"],
            url=project["web_url"],
            source=SCMSource.GITLAB,
            org=group,
            primary_language=None,  # not in REST response without extra call
            created_at=datetime.fromisoformat(project["created_at"].replace("Z", "+00:00")),
            is_archived=project.get("archived", False),
            is_fork=project.get("forked_from_project") is not None,
            is_private=project.get("visibility") == "private",
            size_kb=project.get("statistics", {}).get("repository_size", 0) // 1024,
            last_commit_at=last_commit_at,
            last_pr_merged_at=self._last_merged_mr(project["id"]),
            has_codeowners=self._file_exists(project["id"], "CODEOWNERS"),
            has_readme=bool(project.get("readme_url")),
            has_ci_pipeline=self._has_pipeline(project["id"]),
            open_security_alerts=0,  # requires GitLab Ultimate tier
        )

    def _file_exists(self, project_id: int, path: str) -> bool:
        try:
            resp = self.session.head(
                f"{self.base}/api/v4/projects/{project_id}/repository/files/{path}",
                params={"ref": "HEAD"},
            )
            return resp.status_code == 200
        except Exception:
            return False

    def _has_pipeline(self, project_id: int) -> bool:
        try:
            resp = self._get(f"/projects/{project_id}/pipelines", {"per_page": 1})
            return len(resp.json()) > 0
        except Exception:
            return False

    def _last_merged_mr(self, project_id: int) -> datetime | None:
        try:
            resp = self._get(
                f"/projects/{project_id}/merge_requests",
                {"state": "merged", "order_by": "updated_at", "sort": "desc", "per_page": 1},
            )
            mrs = resp.json()
            if mrs and mrs[0].get("merged_at"):
                return datetime.fromisoformat(mrs[0]["merged_at"].replace("Z", "+00:00"))
        except Exception:
            pass
        return None
