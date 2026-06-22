from datetime import datetime, timezone

from .models import RepoSnapshot, HealthScore, HealthTier


def score_repo(repo: RepoSnapshot, stale_days: int = 180, dead_days: int = 365) -> HealthScore:
    now = datetime.now(timezone.utc)
    tags: list[str] = []

    staleness_score = _staleness(repo, now, stale_days, dead_days, tags)
    ownership_score = _ownership(repo, tags)
    risk_penalty    = _risk(repo, tags)
    activity_score  = _activity(repo, now, tags)

    total = max(0, min(100, staleness_score + ownership_score - risk_penalty + activity_score))

    # Archival candidate: dead AND no owner AND no evidence of active CI/CD deployment.
    # A repo with a recently-run deploy workflow is likely in production even if
    # direct commits are infrequent — do not mark it for archival.
    archival_candidate = (
        "dead" in tags
        and "no-owner" in tags
        and not repo.has_deploy_workflow
    )

    if archival_candidate:
        tier = HealthTier.DORMANT
    elif total >= 70:
        tier = HealthTier.GOVERNED
    elif total >= 40:
        tier = HealthTier.NEEDS_WORK
    else:
        tier = HealthTier.UNGOVERNED

    return HealthScore(
        repo_full_name=repo.full_name,
        total=total,
        staleness_score=staleness_score,
        ownership_score=ownership_score,
        risk_penalty=risk_penalty,
        activity_score=activity_score,
        tier=tier,
        archival_candidate=archival_candidate,
        tags=tags,
    )


def _staleness(
    repo: RepoSnapshot,
    now: datetime,
    stale_days: int,
    dead_days: int,
    tags: list[str],
) -> int:
    if repo.is_archived:
        tags.append("archived")
        return 0

    # Use the most recent of: last commit, last workflow run.
    # A repo with no direct commits but active CI pipelines is not dead.
    candidates = [repo.last_commit_at, repo.last_workflow_run_at]
    last_activity = max((d for d in candidates if d), default=None)

    if last_activity is None:
        tags.append("dead")
        return 0

    days = (now - last_activity).days

    if repo.has_deploy_workflow and repo.last_workflow_run_at:
        wf_days = (now - repo.last_workflow_run_at).days
        if wf_days <= 90:
            tags.append("ci-deployed")  # CI is actively deploying

    if days > dead_days:
        tags.append("dead")
        return 5
    elif days > stale_days:
        tags.append("stale")
        return 20
    elif days > 90:
        tags.append("aging")
        return 28
    elif days > 30:
        tags.append("active")
        return 35
    else:
        tags.append("active")
        return 40


def _ownership(repo: RepoSnapshot, tags: list[str]) -> int:
    score = 0

    if repo.has_codeowners:
        score += 20
        tags.append("has-owner")
    else:
        tags.append("no-owner")

    if repo.has_readme:
        score += 5
    else:
        tags.append("no-readme")

    if repo.has_ci_pipeline:
        score += 5

    return score


def _risk(repo: RepoSnapshot, tags: list[str]) -> int:
    penalty = 0

    if repo.open_security_alerts >= 5:
        penalty += 20
        tags.append("critical-cve")
    elif repo.open_security_alerts >= 2:
        penalty += 12
        tags.append("has-cve")
    elif repo.open_security_alerts == 1:
        penalty += 6
        tags.append("has-cve")

    if repo.has_ci_pipeline and repo.ci_is_passing is False:
        penalty += 5
        tags.append("ci-failing")
    elif not repo.has_ci_pipeline and not repo.is_archived:
        penalty += 3
        tags.append("no-ci")

    return min(20, penalty)


def _activity(repo: RepoSnapshot, now: datetime, tags: list[str]) -> int:
    # Contributors are the strongest signal
    if repo.unique_contributors_90d > 3:
        return 10
    if repo.unique_contributors_90d > 0:
        return 5

    # Recent deploy workflow is a strong proxy for active production use
    if repo.has_deploy_workflow and repo.last_workflow_run_at:
        wf_days = (now - repo.last_workflow_run_at).days
        if wf_days <= 30:
            return 8   # actively deploying
        if wf_days <= 90:
            return 5

    # Fall back to last commit recency
    if repo.last_commit_at:
        days = (now - repo.last_commit_at).days
        if days <= 30:
            return 3
    return 0
