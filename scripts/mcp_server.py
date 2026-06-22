"""
archView MCP Server — exposes the architecture knowledge graph to AI agents.

Agents query this server to understand:
  - What domain/subdomain/team owns a repo
  - What a repo depends on, what depends on it
  - Which repos are ungoverned or dormant in a domain
  - Cross-domain dependency hotspots

Run (stdio transport, compatible with Claude Code / Cursor / Windsurf):
    .venv/bin/python -m scripts.mcp_server

Register in .mcp.json:
    {
      "mcpServers": {
        "archview": {
          "command": "/path/to/archView/.venv/bin/python",
          "args": ["-m", "scripts.mcp_server"]
        }
      }
    }
"""

import asyncio
import json
from pathlib import Path

import ladybug
import mcp.server.stdio
import mcp.types as types
from mcp.server import Server

DB_PATH = Path("architecture-overview/graph.db")

# ── DB connection (module-level, reused across calls) ─────────────────────────
_db   = None
_conn = None


def get_conn() -> ladybug.Connection:
    global _db, _conn
    if _conn is None:
        if not DB_PATH.exists():
            raise RuntimeError(
                f"Graph DB not found at {DB_PATH}. "
                "Run: python -m scripts.load_graph"
            )
        _db   = ladybug.Database(str(DB_PATH))
        _conn = ladybug.Connection(_db)
    return _conn


def cypher(q: str, params: dict | None = None) -> list[list]:
    """Execute a Cypher query and return all rows."""
    conn   = get_conn()
    result = conn.execute(q, params or {})
    rows   = []
    while result.has_next():
        rows.append(result.get_next())
    return rows


# ── MCP server ────────────────────────────────────────────────────────────────
server = Server("archview-graph")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="get_repo_context",
            description=(
                "Get full architectural context for a repo: domain, subdomain, "
                "owning team(s), repos it depends on, repos that depend on it. "
                "Use this before implementing a change to understand impact."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "repo_name": {
                        "type": "string",
                        "description": "Repo full name, e.g. 'agilecontent/cms-api' or partial name 'cms-api'",
                    }
                },
                "required": ["repo_name"],
            },
        ),
        types.Tool(
            name="find_repos",
            description=(
                "Search repos by name, domain, subdomain, team, or health tier. "
                "All parameters are optional — combine to narrow results."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "name_contains":  {"type": "string", "description": "Partial repo name match"},
                    "domain":         {"type": "string", "description": "Exact domain name, e.g. '7. Experience'"},
                    "subdomain":      {"type": "string", "description": "Exact subdomain name, e.g. 'Apps'"},
                    "team":           {"type": "string", "description": "Team name (partial match)"},
                    "health_tier":    {"type": "string", "enum": ["governed", "needs_work", "ungoverned", "dormant"]},
                    "limit":          {"type": "integer", "default": 20},
                },
            },
        ),
        types.Tool(
            name="get_domain_overview",
            description=(
                "Summary of a domain: repo count by subdomain, team coverage, "
                "governance health breakdown, and cross-domain dependencies."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "domain": {
                        "type": "string",
                        "description": "Domain name or number prefix, e.g. '7. Experience' or '7'",
                    }
                },
                "required": ["domain"],
            },
        ),
        types.Tool(
            name="get_ungoverned_repos",
            description="List repos with no declared team owner. Filter by domain or health tier.",
            inputSchema={
                "type": "object",
                "properties": {
                    "domain":      {"type": "string", "description": "Filter to a specific domain"},
                    "health_tier": {"type": "string", "enum": ["governed", "needs_work", "ungoverned", "dormant"]},
                    "limit":       {"type": "integer", "default": 20},
                },
            },
        ),
        types.Tool(
            name="get_cross_domain_deps",
            description=(
                "Show cross-domain dependency edges. "
                "Identifies architectural coupling between domains — "
                "high-risk findings where one domain's build imports from another."
            ),
            inputSchema={"type": "object", "properties": {}},
        ),
        types.Tool(
            name="query_graph",
            description=(
                "Run a raw Cypher query against the architecture graph. "
                "Node types: Domain, Subdomain, Repo, Team. "
                "Rel types: SubToDomain, RepoToSub, TeamOwns, DependsOn, Calls. "
                "Use for custom analysis not covered by other tools."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "cypher": {"type": "string", "description": "Cypher query string"},
                    "params": {"type": "object", "description": "Optional query parameters"},
                },
                "required": ["cypher"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    try:
        result = _dispatch(name, arguments)
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]
    except Exception as e:
        return [types.TextContent(type="text", text=f"Error: {e}")]


def _dispatch(name: str, args: dict) -> dict:
    if name == "get_repo_context":
        return _get_repo_context(args["repo_name"])
    elif name == "find_repos":
        return _find_repos(args)
    elif name == "get_domain_overview":
        return _get_domain_overview(args["domain"])
    elif name == "get_ungoverned_repos":
        return _get_ungoverned(args)
    elif name == "get_cross_domain_deps":
        return _get_cross_domain_deps()
    elif name == "query_graph":
        rows = cypher(args["cypher"], args.get("params", {}))
        return {"rows": rows, "count": len(rows)}
    else:
        raise ValueError(f"Unknown tool: {name}")


# ── Tool implementations ──────────────────────────────────────────────────────

def _get_repo_context(repo_name: str) -> dict:
    # Resolve partial name
    rows = cypher(
        "MATCH (r:Repo) WHERE r.name CONTAINS $n RETURN r.id, r.name, r.domain, r.subdomain, r.health_tier, r.confidence, r.language, r.url LIMIT 5",
        {"n": repo_name},
    )
    if not rows:
        return {"error": f"No repo found matching '{repo_name}'"}

    repo_id, repo_name_full, domain, subdomain, tier, conf, lang, url = rows[0]

    # Owning teams
    teams = [r[0] for r in cypher(
        "MATCH (t:Team)-[:TeamOwns]->(r:Repo {id:$id}) RETURN t.name",
        {"id": repo_id},
    )]

    # What this repo depends on
    deps_on = [{"repo": r[0], "confidence": r[1], "detail": r[2]}
               for r in cypher(
        "MATCH (r:Repo {id:$id})-[e:DependsOn]->(dep:Repo) RETURN dep.name, e.confidence, e.detail",
        {"id": repo_id},
    )]

    # What depends on this repo
    depended_by = [{"repo": r[0], "confidence": r[1]}
                   for r in cypher(
        "MATCH (dep:Repo)-[:DependsOn]->(r:Repo {id:$id}) RETURN dep.name, dep.domain",
        {"id": repo_id},
    )]

    return {
        "repo":         repo_name_full,
        "url":          url,
        "domain":       domain,
        "subdomain":    subdomain,
        "health_tier":  tier,
        "confidence":   conf,
        "language":     lang,
        "teams":        teams if teams else ["⚠ Unassigned"],
        "depends_on":   deps_on,
        "depended_by":  depended_by,
        "ambiguous_matches": [r[1] for r in rows[1:]] if len(rows) > 1 else [],
    }


def _find_repos(args: dict) -> dict:
    where, params = [], {}
    if nc := args.get("name_contains"):
        where.append("r.name CONTAINS $name"); params["name"] = nc
    if d := args.get("domain"):
        where.append("r.domain = $domain"); params["domain"] = d
    if s := args.get("subdomain"):
        where.append("r.subdomain = $sub"); params["sub"] = s
    if ht := args.get("health_tier"):
        where.append("r.health_tier = $tier"); params["tier"] = ht

    where_clause = ("WHERE " + " AND ".join(where)) if where else ""
    limit = int(args.get("limit", 20))

    base_q = f"MATCH (r:Repo) {where_clause} RETURN r.name, r.domain, r.subdomain, r.health_tier, r.language LIMIT {limit}"
    rows = cypher(base_q, params)

    # Team filter (post-process — JOIN would need a separate query)
    if team_filter := args.get("team"):
        team_repos = {r[0] for r in cypher(
            "MATCH (t:Team)-[:TeamOwns]->(r:Repo) WHERE t.name CONTAINS $t RETURN r.name",
            {"t": team_filter},
        )}
        rows = [r for r in rows if r[0] in team_repos]

    return {
        "repos": [
            {"name": r[0], "domain": r[1], "subdomain": r[2], "health_tier": r[3], "language": r[4]}
            for r in rows
        ],
        "count": len(rows),
    }


def _get_domain_overview(domain_arg: str) -> dict:
    # Resolve: accept "7" or "7. Experience" or "Experience"
    all_domains = [r[0] for r in cypher("MATCH (d:Domain) RETURN d.name")]
    domain = next(
        (d for d in all_domains
         if d == domain_arg
         or d.startswith(domain_arg + ".")
         or domain_arg in d),
        None,
    )
    if not domain:
        return {"error": f"Domain not found: {domain_arg}", "available": all_domains}

    # Repos by subdomain
    by_sub = {}
    for row in cypher(
        "MATCH (r:Repo) WHERE r.domain = $d RETURN r.subdomain, count(r)",
        {"d": domain},
    ):
        by_sub[row[0] or "Unknown"] = row[1]

    # Health breakdown
    health = {}
    for row in cypher(
        "MATCH (r:Repo) WHERE r.domain = $d RETURN r.health_tier, count(r)",
        {"d": domain},
    ):
        health[row[0] or "unknown"] = row[1]

    # Teams in this domain
    teams = [r[0] for r in cypher(
        "MATCH (t:Team)-[:TeamOwns]->(r:Repo) WHERE r.domain = $d RETURN DISTINCT t.name ORDER BY t.name",
        {"d": domain},
    )]

    # Cross-domain deps leaving this domain
    deps_out = [{"to": r[0], "count": r[1]} for r in cypher(
        """MATCH (a:Repo)-[:DependsOn]->(b:Repo)
           WHERE a.domain = $d AND b.domain <> $d
           RETURN b.domain, count(*) AS n ORDER BY n DESC""",
        {"d": domain},
    )]

    # Cross-domain deps entering this domain
    deps_in = [{"from": r[0], "count": r[1]} for r in cypher(
        """MATCH (a:Repo)-[:DependsOn]->(b:Repo)
           WHERE b.domain = $d AND a.domain <> $d
           RETURN a.domain, count(*) AS n ORDER BY n DESC""",
        {"d": domain},
    )]

    total = sum(by_sub.values())
    unowned = cypher(
        """MATCH (r:Repo) WHERE r.domain = $d
           AND NOT EXISTS { MATCH (:Team)-[:TeamOwns]->(r) }
           RETURN count(r)""",
        {"d": domain},
    )[0][0]

    return {
        "domain":      domain,
        "total_repos": total,
        "unowned_repos": unowned,
        "repos_by_subdomain": by_sub,
        "health_breakdown": health,
        "teams": teams,
        "depends_on_domains": deps_out,
        "depended_on_by_domains": deps_in,
    }


def _get_ungoverned(args: dict) -> dict:
    where, params = [], {}
    if d := args.get("domain"):
        where.append("r.domain = $domain"); params["domain"] = d
    if ht := args.get("health_tier"):
        where.append("r.health_tier = $tier"); params["tier"] = ht
    else:
        where.append("r.health_tier <> 'dormant'")

    wc    = ("AND " + " AND ".join(where)) if where else ""
    limit = int(args.get("limit", 20))
    q = f"""
        MATCH (r:Repo) WHERE NOT EXISTS {{ MATCH (:Team)-[:TeamOwns]->(r) }}
        {wc}
        RETURN r.name, r.domain, r.subdomain, r.health_tier LIMIT {limit}
    """
    rows = cypher(q, params)
    return {
        "ungoverned_repos": [
            {"name": r[0], "domain": r[1], "subdomain": r[2], "health_tier": r[3]}
            for r in rows
        ],
        "count": len(rows),
    }


def _get_cross_domain_deps() -> dict:
    rows = cypher("""
        MATCH (a:Repo)-[e:DependsOn]->(b:Repo)
        WHERE a.domain <> b.domain
        RETURN a.name, a.domain, b.name, b.domain, e.confidence, e.detail
        ORDER BY a.domain, b.domain
    """)
    # Aggregate by domain pair
    pairs: dict[str, dict] = {}
    edges = []
    for row in rows:
        a_name, a_dom, b_name, b_dom, conf, detail = row
        key = f"{a_dom} → {b_dom}"
        if key not in pairs:
            pairs[key] = {"from": a_dom, "to": b_dom, "count": 0, "examples": []}
        pairs[key]["count"] += 1
        if len(pairs[key]["examples"]) < 3:
            pairs[key]["examples"].append(f"{a_name} → {b_name}")
        edges.append({"from_repo": a_name, "from_domain": a_dom,
                      "to_repo": b_name, "to_domain": b_dom,
                      "confidence": conf, "detail": detail})

    return {
        "summary": sorted(pairs.values(), key=lambda x: -x["count"]),
        "total_cross_domain_edges": len(edges),
        "edges": edges,
    }


# ── Entry point ───────────────────────────────────────────────────────────────
async def main() -> None:
    async with mcp.server.stdio.stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
