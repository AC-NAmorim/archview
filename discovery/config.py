import os
import subprocess
from dataclasses import dataclass, field


def _csv_env(key: str) -> list[str]:
    return [v.strip() for v in os.environ.get(key, "").split(",") if v.strip()]


def _cli_token(cmd: list[str]) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        return r.stdout.strip() if r.returncode == 0 else ""
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""


def _github_token() -> str:
    return (
        os.environ.get("GITHUB_TOKEN")
        or _cli_token(["gh", "auth", "token"])
    )


def _gitlab_token(host: str = "") -> str:
    """Resolve GitLab token: env var → glab CLI (with host if self-hosted)."""
    token = os.environ.get("GITLAB_TOKEN")
    if token:
        return token
    # glab auth token --hostname <host> for self-hosted instances
    cmd = ["glab", "auth", "token"]
    if host and host not in ("https://gitlab.com", "gitlab.com"):
        hostname = host.replace("https://", "").replace("http://", "").rstrip("/")
        cmd += ["--hostname", hostname]
    return _cli_token(cmd)


@dataclass
class Config:
    github_token: str = field(default_factory=_github_token)
    github_orgs: list[str] = field(default_factory=lambda: _csv_env("GITHUB_ORGS"))

    # GitLab — supports both gitlab.com and self-hosted instances
    gitlab_url: str = field(default_factory=lambda: os.environ.get(
        "GITLAB_URL", "https://gitlab.agilecontent.com"  # default to self-hosted
    ))
    gitlab_groups: list[str] = field(default_factory=lambda: _csv_env("GITLAB_GROUPS"))

    @property
    def gitlab_token(self) -> str:
        return _gitlab_token(self.gitlab_url)

    # Thresholds in days — tune these to your governance policy
    stale_commit_days: int = int(os.environ.get("STALE_COMMIT_DAYS", "180"))
    dead_commit_days: int = int(os.environ.get("DEAD_COMMIT_DAYS", "365"))

    output_dir: str = field(default_factory=lambda: os.environ.get("OUTPUT_DIR", "./output"))
    max_workers: int = int(os.environ.get("MAX_WORKERS", "10"))
