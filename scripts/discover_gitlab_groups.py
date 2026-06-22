"""
Lists all top-level groups and subgroups on the configured GitLab instance.
Run this after setting GITLAB_TOKEN in .env to find the right GITLAB_GROUPS values.

    .venv/bin/python -m scripts.discover_gitlab_groups
"""

import json
import sys
from dotenv import load_dotenv
load_dotenv()

from discovery.config import Config

cfg = Config()

if not cfg.gitlab_token:
    print("ERROR: GITLAB_TOKEN not set in .env")
    print(f"Generate one at: {cfg.gitlab_url}/-/profile/personal_access_tokens")
    print("Required scope: read_api")
    sys.exit(1)

import requests

session = requests.Session()
session.headers["PRIVATE-TOKEN"] = cfg.gitlab_token

def paginate(path: str, params: dict = None):
    params = {**(params or {}), "per_page": 100, "page": 1}
    while True:
        resp = session.get(f"{cfg.gitlab_url}/api/v4{path}", params=params)
        resp.raise_for_status()
        items = resp.json()
        if not items:
            break
        yield from items
        if not resp.headers.get("X-Next-Page"):
            break
        params["page"] = int(resp.headers["X-Next-Page"])

print(f"\nDiscovering groups on {cfg.gitlab_url}...\n")

groups = list(paginate("/groups", {"top_level_only": True, "order_by": "name", "sort": "asc"}))

print(f"{'Path':<50} {'ID':>6}  Name")
print("─" * 80)
for g in groups:
    print(f"{g['full_path']:<50} {g['id']:>6}  {g['name']}")

print(f"\nFound {len(groups)} top-level groups.")
print("\nSet GITLAB_GROUPS in .env to the paths or IDs you want to scan, e.g.:")
if groups:
    example = ",".join(g["full_path"] for g in groups[:3])
    print(f"  GITLAB_GROUPS={example}")
