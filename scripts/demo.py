"""
End-to-end demo: generates realistic mock repos and runs the full Phase 1 pipeline.
Produces CSV, JSON, and a markdown report in ./output/demo/

Run:
    python -m scripts.demo
"""

from datetime import datetime, timezone, timedelta
from discovery.models import RepoSnapshot, SCMSource
from discovery.health import score_repo
from discovery.exporters import export_csv, export_json, export_markdown_report


def days_ago(n: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=n)


MOCK_REPOS: list[RepoSnapshot] = [
    # ── Active, well-governed services ─────────────────────────────────────
    RepoSnapshot(
        id="1", name="api-gateway", full_name="tvplatform/api-gateway",
        url="https://github.com/tvplatform/api-gateway",
        source=SCMSource.GITHUB, org="tvplatform",
        primary_language="Java", created_at=days_ago(900),
        is_archived=False, is_fork=False, is_private=True, size_kb=8200,
        last_commit_at=days_ago(5), last_pr_merged_at=days_ago(6),
        has_codeowners=True, has_readme=True, has_ci_pipeline=True, ci_is_passing=True,
        open_security_alerts=0, unique_contributors_90d=6,
    ),
    RepoSnapshot(
        id="2", name="content-delivery-service", full_name="tvplatform/content-delivery-service",
        url="https://github.com/tvplatform/content-delivery-service",
        source=SCMSource.GITHUB, org="tvplatform",
        primary_language="Java", created_at=days_ago(1100),
        is_archived=False, is_fork=False, is_private=True, size_kb=14500,
        last_commit_at=days_ago(18), last_pr_merged_at=days_ago(20),
        has_codeowners=True, has_readme=True, has_ci_pipeline=True, ci_is_passing=True,
        open_security_alerts=1, unique_contributors_90d=4,
    ),
    RepoSnapshot(
        id="3", name="user-auth-service", full_name="tvplatform/user-auth-service",
        url="https://github.com/tvplatform/user-auth-service",
        source=SCMSource.GITHUB, org="tvplatform",
        primary_language="Java", created_at=days_ago(730),
        is_archived=False, is_fork=False, is_private=True, size_kb=5100,
        last_commit_at=days_ago(45), last_pr_merged_at=days_ago(48),
        has_codeowners=True, has_readme=True, has_ci_pipeline=True, ci_is_passing=True,
        open_security_alerts=0, unique_contributors_90d=2,
    ),

    # ── Active but governance gaps ──────────────────────────────────────────
    RepoSnapshot(
        id="4", name="player-sdk-web", full_name="tvplatform/player-sdk-web",
        url="https://github.com/tvplatform/player-sdk-web",
        source=SCMSource.GITHUB, org="tvplatform",
        primary_language="JavaScript", created_at=days_ago(600),
        is_archived=False, is_fork=False, is_private=False, size_kb=3400,
        last_commit_at=days_ago(12), last_pr_merged_at=days_ago(15),
        has_codeowners=False, has_readme=True, has_ci_pipeline=True, ci_is_passing=True,
        open_security_alerts=0, unique_contributors_90d=3,
    ),
    RepoSnapshot(
        id="5", name="billing-service", full_name="tvplatform/billing-service",
        url="https://github.com/tvplatform/billing-service",
        source=SCMSource.GITHUB, org="tvplatform",
        primary_language="Java", created_at=days_ago(500),
        is_archived=False, is_fork=False, is_private=True, size_kb=6700,
        last_commit_at=days_ago(22), last_pr_merged_at=days_ago(25),
        has_codeowners=False, has_readme=False, has_ci_pipeline=True, ci_is_passing=True,
        open_security_alerts=3, unique_contributors_90d=2,
    ),

    # ── Stale but owned ────────────────────────────────────────────────────
    RepoSnapshot(
        id="6", name="legacy-epg-service", full_name="tvplatform/legacy-epg-service",
        url="https://gitlab.com/tvplatform/legacy-epg-service",
        source=SCMSource.GITLAB, org="tvplatform",
        primary_language="Java", created_at=days_ago(2000),
        is_archived=False, is_fork=False, is_private=True, size_kb=22000,
        last_commit_at=days_ago(210), last_pr_merged_at=days_ago(240),
        has_codeowners=True, has_readme=True, has_ci_pipeline=True, ci_is_passing=False,
        open_security_alerts=2, unique_contributors_90d=0,
    ),
    RepoSnapshot(
        id="7", name="recommendation-engine-v1", full_name="tvplatform/recommendation-engine-v1",
        url="https://gitlab.com/tvplatform/recommendation-engine-v1",
        source=SCMSource.GITLAB, org="tvplatform",
        primary_language="Java", created_at=days_ago(1800),
        is_archived=False, is_fork=False, is_private=True, size_kb=9100,
        last_commit_at=days_ago(195), last_pr_merged_at=days_ago(200),
        has_codeowners=True, has_readme=True, has_ci_pipeline=False,
        open_security_alerts=0, unique_contributors_90d=0,
    ),

    # ── Dead + no owner = archival candidates ──────────────────────────────
    RepoSnapshot(
        id="8", name="old-analytics-pipeline", full_name="tvplatform/old-analytics-pipeline",
        url="https://github.com/tvplatform/old-analytics-pipeline",
        source=SCMSource.GITHUB, org="tvplatform",
        primary_language="Java", created_at=days_ago(2500),
        is_archived=False, is_fork=False, is_private=True, size_kb=4400,
        last_commit_at=days_ago(420), last_pr_merged_at=days_ago(500),
        has_codeowners=False, has_readme=False, has_ci_pipeline=False,
        open_security_alerts=0, unique_contributors_90d=0,
    ),
    RepoSnapshot(
        id="9", name="prototype-drm-poc", full_name="tvplatform/prototype-drm-poc",
        url="https://github.com/tvplatform/prototype-drm-poc",
        source=SCMSource.GITHUB, org="tvplatform",
        primary_language="JavaScript", created_at=days_ago(1400),
        is_archived=False, is_fork=False, is_private=True, size_kb=800,
        last_commit_at=days_ago(550), last_pr_merged_at=None,
        has_codeowners=False, has_readme=False, has_ci_pipeline=False,
        open_security_alerts=0, unique_contributors_90d=0,
    ),
    RepoSnapshot(
        id="10", name="test-env-scripts", full_name="tvplatform/test-env-scripts",
        url="https://gitlab.com/tvplatform/test-env-scripts",
        source=SCMSource.GITLAB, org="tvplatform",
        primary_language=None, created_at=days_ago(900),
        is_archived=False, is_fork=False, is_private=True, size_kb=120,
        last_commit_at=days_ago(400), last_pr_merged_at=None,
        has_codeowners=False, has_readme=False, has_ci_pipeline=False,
        open_security_alerts=0, unique_contributors_90d=0,
    ),

    # ── High risk: active but open CVEs ────────────────────────────────────
    RepoSnapshot(
        id="11", name="streaming-ingest-service", full_name="tvplatform/streaming-ingest-service",
        url="https://gitlab.com/tvplatform/streaming-ingest-service",
        source=SCMSource.GITLAB, org="tvplatform",
        primary_language="Java", created_at=days_ago(700),
        is_archived=False, is_fork=False, is_private=True, size_kb=11200,
        last_commit_at=days_ago(10), last_pr_merged_at=days_ago(11),
        has_codeowners=True, has_readme=True, has_ci_pipeline=True, ci_is_passing=True,
        open_security_alerts=6, unique_contributors_90d=5,
    ),

    # ── Already archived by owner ───────────────────────────────────────────
    RepoSnapshot(
        id="12", name="old-cms-v1", full_name="tvplatform/old-cms-v1",
        url="https://github.com/tvplatform/old-cms-v1",
        source=SCMSource.GITHUB, org="tvplatform",
        primary_language="Java", created_at=days_ago(3000),
        is_archived=True, is_fork=False, is_private=True, size_kb=7800,
        last_commit_at=days_ago(800), last_pr_merged_at=days_ago(820),
        has_codeowners=False, has_readme=True, has_ci_pipeline=False,
        open_security_alerts=0, unique_contributors_90d=0,
    ),
]


def main():
    print("Running Phase 1 demo pipeline...\n")

    scores = {
        repo.full_name: score_repo(repo)
        for repo in MOCK_REPOS
    }

    out_dir = "./output/demo"
    csv_path  = export_csv(MOCK_REPOS, scores, out_dir)
    json_path = export_json(MOCK_REPOS, scores, out_dir)
    md_path   = export_markdown_report(MOCK_REPOS, scores, out_dir)

    print(f"Outputs → {out_dir}/\n")

    # Console summary table
    print(f"{'Repo':<42} {'Tier':<22} {'Score':>5}  Tags")
    print("─" * 100)
    for repo in sorted(MOCK_REPOS, key=lambda r: scores[r.full_name].total):
        s = scores[repo.full_name]
        print(f"{repo.full_name:<42} {s.tier.value:<22} {s.total:>5}  {', '.join(s.tags)}")

    print()
    archival = [s for s in scores.values() if s.archival_candidate]
    critical  = [s for s in scores.values() if s.tier.value == "critical" and not s.archival_candidate]
    warning   = [s for s in scores.values() if s.tier.value == "warning"]
    healthy   = [s for s in scores.values() if s.tier.value == "healthy"]
    print(f"Archival candidates : {len(archival)}")
    print(f"Critical            : {len(critical)}")
    print(f"Warning             : {len(warning)}")
    print(f"Healthy             : {len(healthy)}")
    print(f"\nFull report → {md_path}")


if __name__ == "__main__":
    main()
