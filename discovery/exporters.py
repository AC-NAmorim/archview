import csv
import json
import os
from datetime import datetime
from pathlib import Path

from .models import RepoSnapshot, HealthScore, HealthTier


def _dt(val) -> str:
    return val.isoformat() if val else ""


def export_csv(repos: list[RepoSnapshot], scores: dict[str, HealthScore], out_dir: str) -> str:
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    path = os.path.join(out_dir, "repo_health.csv")

    fields = [
        "full_name", "source", "org", "primary_language",
        "is_archived", "is_fork", "is_private", "size_kb",
        "last_commit_at", "last_pr_merged_at",
        "has_codeowners", "has_readme", "has_ci_pipeline",
        "open_security_alerts", "unique_contributors_90d",
        "health_total", "health_tier", "archival_candidate", "tags",
        "url",
    ]
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for repo in repos:
            s = scores.get(repo.full_name)
            writer.writerow({
                "full_name": repo.full_name,
                "source": repo.source.value,
                "org": repo.org,
                "primary_language": repo.primary_language or "",
                "is_archived": repo.is_archived,
                "is_fork": repo.is_fork,
                "is_private": repo.is_private,
                "size_kb": repo.size_kb,
                "last_commit_at": _dt(repo.last_commit_at),
                "last_pr_merged_at": _dt(repo.last_pr_merged_at),
                "has_codeowners": repo.has_codeowners,
                "has_readme": repo.has_readme,
                "has_ci_pipeline": repo.has_ci_pipeline,
                "open_security_alerts": repo.open_security_alerts,
                "unique_contributors_90d": repo.unique_contributors_90d,
                "health_total": s.total if s else "",
                "health_tier": s.tier.value if s else "",
                "archival_candidate": s.archival_candidate if s else "",
                "tags": "|".join(s.tags) if s else "",
                "url": repo.url,
            })
    return path


def export_json(repos: list[RepoSnapshot], scores: dict[str, HealthScore], out_dir: str) -> str:
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    path = os.path.join(out_dir, "repo_health.json")

    data = [
        {
            "full_name": r.full_name,
            "source": r.source.value,
            "org": r.org,
            "url": r.url,
            "language": r.primary_language,
            "last_commit_at": _dt(r.last_commit_at),
            "workflow": {
                "last_run_at":       _dt(r.last_workflow_run_at),
                "last_run_status":   r.last_workflow_status,
                "has_deploy":        r.has_deploy_workflow,
                "deploy_workflows":  r.deploy_workflow_names,
            } if r.last_workflow_run_at or r.has_deploy_workflow else None,
            "cve_alerts": [
                {
                    "package": c.package,
                    "ecosystem": c.ecosystem,
                    "severity": c.severity,
                    "summary": c.summary,
                    "cvss_score": c.cvss_score,
                    "cve_id": c.cve_id,
                }
                for c in r.cve_alerts
            ],
            "health": {
                "total": s.total,
                "tier": s.tier.value,
                "archival_candidate": s.archival_candidate,
                "tags": s.tags,
                "breakdown": {
                    "staleness": s.staleness_score,
                    "ownership": s.ownership_score,
                    "risk_penalty": s.risk_penalty,
                    "activity": s.activity_score,
                },
            } if (s := scores.get(r.full_name)) else None,
        }
        for r in repos
    ]

    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)
    return path


def export_markdown_report(repos: list[RepoSnapshot], scores: dict[str, HealthScore], out_dir: str) -> str:
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    path = os.path.join(out_dir, "report.md")

    all_scores = list(scores.values())
    archival    = [s for s in all_scores if s.tier == HealthTier.DORMANT]
    ungoverned  = [s for s in all_scores if s.tier == HealthTier.UNGOVERNED]
    needs_work  = [s for s in all_scores if s.tier == HealthTier.NEEDS_WORK]
    governed    = [s for s in all_scores if s.tier == HealthTier.GOVERNED]
    total     = len(all_scores)

    def pct(n): return f"{n/total*100:.0f}%" if total else "0%"

    repo_by_name = {r.full_name: r for r in repos}

    with open(path, "w") as f:
        f.write(f"# Platform Repository Health Report\n")
        f.write(f"_Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}_\n\n")

        f.write("## Summary\n\n")
        f.write("| Tier | Count | % |\n|---|---|---|\n")
        for label, items in [
            ("Dormant", archival),
            ("Ungoverned", ungoverned),
            ("Needs Work", needs_work),
            ("Governed", governed),
        ]:
            f.write(f"| {label} | {len(items)} | {pct(len(items))} |\n")
        f.write(f"| **Total** | **{total}** | |\n\n")

        ownership_pct = sum(1 for r in repos if r.has_codeowners) / len(repos) * 100 if repos else 0
        readme_pct    = sum(1 for r in repos if r.has_readme) / len(repos) * 100 if repos else 0
        ci_pct        = sum(1 for r in repos if r.has_ci_pipeline) / len(repos) * 100 if repos else 0
        alert_total   = sum(r.open_security_alerts for r in repos)

        f.write("## Governance Coverage\n\n")
        f.write("| Signal | Coverage |\n|---|---|\n")
        f.write(f"| Ownership declared (CODEOWNERS) | {ownership_pct:.0f}% |\n")
        f.write(f"| README present | {readme_pct:.0f}% |\n")
        f.write(f"| CI pipeline present | {ci_pct:.0f}% |\n")
        f.write(f"| Open security alerts | {alert_total} |\n\n")

        f.write(f"## Dormant Repos ({len(archival)} repos)\n\n")
        f.write("_No activity across any branch + no declared owner. Verify before archiving._\n\n")
        f.write("| Repo | Last Commit | Tags |\n|---|---|---|\n")
        for s in sorted(archival, key=lambda x: x.total)[:50]:
            r = repo_by_name.get(s.repo_full_name)
            last = _dt(r.last_commit_at)[:10] if r and r.last_commit_at else "never"
            url = r.url if r else "#"
            f.write(f"| [{s.repo_full_name}]({url}) | {last} | {', '.join(s.tags)} |\n")

        if len(archival) > 50:
            f.write(f"\n_...and {len(archival) - 50} more — see repo_health.csv._\n")

    return path
