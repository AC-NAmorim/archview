from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


@dataclass
class CVEAlert:
    repo_full_name: str
    package: str
    ecosystem: str
    severity: str        # CRITICAL | HIGH | MODERATE | LOW
    summary: str
    cvss_score: Optional[float]
    cve_id: Optional[str]


class SCMSource(str, Enum):
    GITHUB = "github"
    GITLAB = "gitlab"


class HealthTier(str, Enum):
    GOVERNED = "governed"          # clear ownership, active, low risk
    NEEDS_WORK = "needs_work"      # some signals missing, improvable
    UNGOVERNED = "ungoverned"      # active but no ownership/CI/docs declared
    DORMANT = "dormant"            # no activity + no owner → archive candidate


@dataclass
class RepoSnapshot:
    id: str
    name: str
    full_name: str
    url: str
    source: SCMSource
    org: str

    primary_language: Optional[str]
    created_at: datetime
    is_archived: bool
    is_fork: bool
    is_private: bool
    size_kb: int

    last_commit_at: Optional[datetime]
    last_pr_merged_at: Optional[datetime]
    commits_last_30d: int = 0
    commits_last_90d: int = 0

    has_codeowners: bool = False
    has_readme: bool = False
    has_ci_pipeline: bool = False
    ci_is_passing: Optional[bool] = None
    team_names: list[str] = field(default_factory=list)

    open_security_alerts: int = 0
    unique_contributors_90d: int = 0
    cve_alerts: list[CVEAlert] = field(default_factory=list)

    # GitHub Actions signals
    last_workflow_run_at: Optional[datetime] = None
    last_workflow_status: Optional[str] = None   # success | failure | cancelled | …
    has_deploy_workflow: bool = False             # any workflow with deploy/publish/release intent
    deploy_workflow_names: list[str] = field(default_factory=list)


@dataclass
class HealthScore:
    repo_full_name: str
    total: int             # 0-100
    staleness_score: int   # 0-40
    ownership_score: int   # 0-30
    risk_penalty: int      # 0-20 (deducted from total)
    activity_score: int    # 0-10
    tier: HealthTier
    archival_candidate: bool
    tags: list[str] = field(default_factory=list)
