import json
import os
import sys

from dotenv import load_dotenv
load_dotenv()

from .config import Config
from .models import RepoSnapshot
from .scanners.github import GitHubScanner
from .scanners.gitlab import GitLabScanner
from .health import score_repo
from .exporters import export_csv, export_json, export_markdown_report
from scripts.generate_dashboard import build_html


def run():
    cfg = Config()

    if not cfg.github_orgs and not cfg.gitlab_groups:
        print("ERROR: Set GITHUB_ORGS and/or GITLAB_GROUPS environment variables.")
        sys.exit(1)

    # Show auth source so it's clear where credentials came from
    if cfg.github_orgs:
        src = "GITHUB_TOKEN env" if os.environ.get("GITHUB_TOKEN") else "gh CLI"
        print(f"GitHub auth: {src}" + ("" if cfg.github_token else " [NOT FOUND]"))
    if cfg.gitlab_groups:
        src = "GITLAB_TOKEN env" if os.environ.get("GITLAB_TOKEN") else "glab CLI"
        print(f"GitLab auth: {src}" + ("" if cfg.gitlab_token else " [NOT FOUND]"))

    repos: list[RepoSnapshot] = []

    github_scanner = None
    if cfg.github_orgs and cfg.github_token:
        github_scanner = GitHubScanner(cfg.github_token)
        for org in cfg.github_orgs:
            print(f"Scanning GitHub org: {org}")
            batch = list(github_scanner.scan_org(org))
            print(f"  {len(batch)} repos")
            repos.extend(batch)

    if cfg.gitlab_groups and cfg.gitlab_token:
        scanner = GitLabScanner(cfg.gitlab_token, cfg.gitlab_url)
        for group in cfg.gitlab_groups:
            print(f"Scanning GitLab group: {group}")
            batch = list(scanner.scan_group(group))
            print(f"  {len(batch)} repos")
            repos.extend(batch)

    if github_scanner:
        cve_repos = [r for r in repos if r.open_security_alerts > 0]
        if cve_repos:
            print(f"Fetching CVE details for {len(cve_repos)} repos...")
            github_scanner.enrich_cve(cve_repos)

        github_repos = [r for r in repos if r.source.value == "github"]
        print(f"Fetching GitHub Actions signals for {len(github_repos)} repos...")
        github_scanner.enrich_workflows(github_repos)
        deployed = sum(1 for r in github_repos if r.has_deploy_workflow)
        print(f"  {deployed} repos have deploy/publish workflows")

    print(f"\nScoring {len(repos)} repos...")
    scores = {
        repo.full_name: score_repo(repo, cfg.stale_commit_days, cfg.dead_commit_days)
        for repo in repos
    }

    csv_path = export_csv(repos, scores, cfg.output_dir)
    json_path = export_json(repos, scores, cfg.output_dir)
    md_path   = export_markdown_report(repos, scores, cfg.output_dir)

    print(f"\nOutputs written to {cfg.output_dir}/")
    print(f"  {csv_path}")
    print(f"  {json_path}")
    print(f"  {md_path}")

    dormant    = sum(1 for s in scores.values() if s.tier.value == "dormant")
    ungoverned = sum(1 for s in scores.values() if s.tier.value == "ungoverned")
    print(f"\n{dormant} dormant | {ungoverned} ungoverned | {len(repos)} total")

    dash_path = os.path.join(cfg.output_dir, "dashboard.html")
    with open(json_path) as f:
        repo_data = json.load(f)
    with open(dash_path, "w") as f:
        f.write(build_html(repo_data))
    print(f"  {dash_path}")


if __name__ == "__main__":
    run()
