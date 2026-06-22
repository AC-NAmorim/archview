"""
Load architecture-graph.json into LadybugDB for queryable graph storage.

Run:
    .venv/bin/python -m scripts.load_graph
    .venv/bin/python -m scripts.load_graph --query   # run validation queries after load
"""

import json
import sys
import shutil
from pathlib import Path

import ladybug

GRAPH_JSON = Path("architecture-overview/architecture-graph.json")
DB_PATH    = Path("architecture-overview/graph.db")


def create_schema(conn: ladybug.Connection) -> None:
    stmts = [
        # ── Node tables ───────────────────────────────────────────────────────
        """CREATE NODE TABLE Domain(
            id       STRING,
            name     STRING,
            PRIMARY KEY(id)
        )""",
        """CREATE NODE TABLE Subdomain(
            id       STRING,
            name     STRING,
            domain   STRING,
            PRIMARY KEY(id)
        )""",
        """CREATE NODE TABLE Repo(
            id           STRING,
            name         STRING,
            url          STRING,
            domain       STRING,
            subdomain    STRING,
            language     STRING,
            health_tier  STRING,
            health_score INT64,
            confidence   STRING,
            last_commit  STRING,
            PRIMARY KEY(id)
        )""",
        """CREATE NODE TABLE Team(
            id   STRING,
            name STRING,
            PRIMARY KEY(id)
        )""",

        # ── Relationship tables ───────────────────────────────────────────────
        "CREATE REL TABLE SubToDomain(FROM Subdomain TO Domain)",
        "CREATE REL TABLE RepoToSub(FROM Repo TO Subdomain, confidence STRING)",
        "CREATE REL TABLE TeamOwns(FROM Team TO Repo)",
        "CREATE REL TABLE DependsOn(FROM Repo TO Repo, confidence STRING, evidence STRING, detail STRING)",
        "CREATE REL TABLE Calls(FROM Repo TO Repo, confidence STRING, evidence STRING, detail STRING)",
        "CREATE REL TABLE ReadsWrites(FROM Repo TO Repo, confidence STRING, evidence STRING, detail STRING)",
    ]
    for s in stmts:
        conn.execute(s)


def load_nodes(conn: ladybug.Connection, nodes: list[dict]) -> dict[str, str]:
    """Insert all nodes, return {graph_id → ladybug_id} mapping."""
    id_map: dict[str, str] = {}

    for n in nodes:
        ntype = n.get("type")
        nid   = n.get("id", "")

        if ntype == "domain":
            conn.execute(
                "CREATE (:Domain {id: $id, name: $name})",
                {"id": nid, "name": str(n.get("name", ""))},
            )
            id_map[nid] = nid

        elif ntype == "subdomain":
            conn.execute(
                "CREATE (:Subdomain {id: $id, name: $name, domain: $domain})",
                {"id": nid, "name": str(n.get("name", "")),
                 "domain": str(n.get("domain", ""))},
            )
            id_map[nid] = nid

        elif ntype == "repo":
            conn.execute(
                """CREATE (:Repo {
                    id: $id, name: $name, url: $url,
                    domain: $domain, subdomain: $subdomain,
                    language: $language, health_tier: $health_tier,
                    health_score: $health_score, confidence: $confidence,
                    last_commit: $last_commit
                })""",
                {
                    "id":           nid,
                    "name":         str(n.get("name", "")),
                    "url":          str(n.get("url", "")),
                    "domain":       str(n.get("domain", "")),
                    "subdomain":    str(n.get("subdomain", "")),
                    "language":     str(n.get("language", "") or ""),
                    "health_tier":  str(n.get("health_tier", "") or ""),
                    "health_score": int(n.get("health_score") or 0),
                    "confidence":   str(n.get("confidence", "") or ""),
                    "last_commit":  str(n.get("last_commit", "") or ""),
                },
            )
            id_map[nid] = nid

        elif ntype == "team":
            conn.execute(
                "CREATE (:Team {id: $id, name: $name})",
                {"id": nid, "name": str(n.get("name", ""))},
            )
            id_map[nid] = nid

    return id_map


def load_edges(conn: ladybug.Connection, edges: list[dict]) -> None:
    for e in edges:
        etype  = e.get("type", "")
        src    = e.get("source", "")
        tgt    = e.get("target", "")
        conf   = str(e.get("confidence", "") or "")
        evid   = str(e.get("evidence", []))
        detail = str(e.get("detail", "") or "")

        try:
            if etype == "belongs_to":
                # Subdomain → Domain  OR  Repo → Subdomain
                if src.startswith("sub:") and tgt.startswith("domain:"):
                    conn.execute(
                        "MATCH (a:Subdomain {id:$s}), (b:Domain {id:$t}) CREATE (a)-[:SubToDomain]->(b)",
                        {"s": src, "t": tgt},
                    )
                elif src.startswith("repo:") and src.find("::") == -1:
                    conn.execute(
                        "MATCH (a:Repo {id:$s}), (b:Subdomain {id:$t}) CREATE (a)-[:RepoToSub {confidence:$c}]->(b)",
                        {"s": src, "t": tgt, "c": conf},
                    )

            elif etype == "owns":
                conn.execute(
                    "MATCH (a:Team {id:$s}), (b:Repo {id:$t}) CREATE (a)-[:TeamOwns]->(b)",
                    {"s": src, "t": tgt},
                )

            elif etype == "depends_on":
                conn.execute(
                    "MATCH (a:Repo {id:$s}), (b:Repo {id:$t}) CREATE (a)-[:DependsOn {confidence:$c,evidence:$e,detail:$d}]->(b)",
                    {"s": src, "t": tgt, "c": conf, "e": evid, "d": detail},
                )

            elif etype == "calls":
                conn.execute(
                    "MATCH (a:Repo {id:$s}), (b:Repo {id:$t}) CREATE (a)-[:Calls {confidence:$c,evidence:$e,detail:$d}]->(b)",
                    {"s": src, "t": tgt, "c": conf, "e": evid, "d": detail},
                )

            elif etype == "reads_writes":
                conn.execute(
                    "MATCH (a:Repo {id:$s}), (b:Repo {id:$t}) CREATE (a)-[:ReadsWrites {confidence:$c,evidence:$e,detail:$d}]->(b)",
                    {"s": src, "t": tgt, "c": conf, "e": evid, "d": detail},
                )
        except Exception as ex:
            # Skip edges where one endpoint node wasn't loaded (e.g. off-taxonomy domain)
            pass


def validate(conn: ladybug.Connection) -> None:
    queries = [
        ("Domains",           "MATCH (d:Domain) RETURN d.name, d.id ORDER BY d.name LIMIT 5"),
        ("Total repos",       "MATCH (r:Repo) RETURN count(r)"),
        ("Teams",             "MATCH (t:Team) RETURN count(t)"),
        ("Repos per domain",  "MATCH (r:Repo) RETURN r.domain, count(r) as n ORDER BY n DESC LIMIT 5"),
        ("Dependency edges",  "MATCH ()-[e:DependsOn]->() RETURN count(e)"),
        ("Team→Repo sample",  "MATCH (t:Team)-[:TeamOwns]->(r:Repo) RETURN t.name, r.name LIMIT 3"),
        ("Cross-domain deps", """
            MATCH (a:Repo)-[:DependsOn]->(b:Repo)
            WHERE a.domain <> b.domain
            RETURN a.domain AS from, b.domain AS to, count(*) AS n
            ORDER BY n DESC LIMIT 5
        """),
    ]

    print("\n── Validation queries ───────────────────────────────────")
    for label, q in queries:
        result = conn.execute(q)
        rows = []
        while result.has_next():
            rows.append(result.get_next())
        print(f"\n{label}:")
        for row in rows[:5]:
            print(f"  {row}")


def main() -> None:
    run_queries = "--query" in sys.argv

    if not GRAPH_JSON.exists():
        print(f"ERROR: {GRAPH_JSON} not found. Run scripts.pilot first.")
        sys.exit(1)

    # Always recreate the DB for idempotency (LadybugDB uses a file, not a directory)
    if DB_PATH.exists():
        if DB_PATH.is_dir():
            shutil.rmtree(DB_PATH)
        else:
            DB_PATH.unlink()

    print(f"Loading {GRAPH_JSON} → {DB_PATH}")
    graph = json.loads(GRAPH_JSON.read_text())
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    print(f"  {len(nodes)} nodes, {len(edges)} edges")

    db   = ladybug.Database(str(DB_PATH))
    conn = ladybug.Connection(db)

    print("Creating schema …")
    create_schema(conn)

    print("Loading nodes …")
    id_map = load_nodes(conn, nodes)
    print(f"  {len(id_map)} nodes inserted")

    print("Loading edges …")
    load_edges(conn, edges)
    print("  Edges loaded")

    if run_queries:
        validate(conn)

    # Summary
    result = conn.execute("MATCH (r:Repo) RETURN count(r)")
    repo_count = result.get_next()[0] if result.has_next() else 0
    result = conn.execute("MATCH ()-[e:DependsOn|Calls|ReadsWrites]->() RETURN count(e)")
    rel_count = result.get_next()[0] if result.has_next() else 0

    print(f"\n✓ Graph loaded to {DB_PATH}")
    print(f"  {repo_count} repos  |  {rel_count} relationship edges")
    print(f"\nQuery it:")
    print(f"  python -m scripts.load_graph --query")


if __name__ == "__main__":
    main()
