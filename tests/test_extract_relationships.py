"""
Unit tests for extract_relationships.py pure parsing functions.
No GitHub API calls — only pure functions tested here.
"""
import pytest
from scripts.extract_relationships import (
    parse_coord_map_entry,
    extract_maven_deps,
    extract_spring_urls,
    extract_npm_deps,
    deduplicate_edges,
)

INTERNAL_PREFIXES = ("com.agilecontent", "com.agiletv")

# ── parse_coord_map_entry ──────────────────────────────────────────────────────

class TestParseCoordMapEntry:
    def test_returns_coord_for_valid_internal_group(self):
        pom = """
        <project>
          <groupId>com.agilecontent</groupId>
          <artifactId>common-lib</artifactId>
        </project>
        """
        assert parse_coord_map_entry(pom) == "com.agilecontent:common-lib"

    def test_strips_parent_block_before_reading_group(self):
        pom = """
        <project>
          <parent>
            <groupId>com.agilecontent</groupId>
            <artifactId>agile-java-base</artifactId>
          </parent>
          <artifactId>ingest-service</artifactId>
          <groupId>com.agiletv</groupId>
        </project>
        """
        assert parse_coord_map_entry(pom) == "com.agiletv:ingest-service"

    def test_returns_none_for_external_group(self):
        pom = """
        <project>
          <groupId>org.springframework.boot</groupId>
          <artifactId>spring-boot-starter</artifactId>
        </project>
        """
        assert parse_coord_map_entry(pom) is None

    def test_returns_none_for_empty_pom(self):
        assert parse_coord_map_entry("") is None

    def test_returns_none_for_malformed_xml(self):
        assert parse_coord_map_entry("<project><groupId>unclosed") is None

    def test_agiletv_prefix_accepted(self):
        pom = """
        <project>
          <groupId>com.agiletv</groupId>
          <artifactId>player-sdk</artifactId>
        </project>
        """
        assert parse_coord_map_entry(pom) == "com.agiletv:player-sdk"

    def test_handles_namespaced_pom(self):
        pom = """
        <project xmlns="http://maven.apache.org/POM/4.0.0">
          <groupId>com.agilecontent</groupId>
          <artifactId>common-lib</artifactId>
        </project>
        """
        assert parse_coord_map_entry(pom) == "com.agilecontent:common-lib"

    def test_returns_none_for_whitespace_groupid(self):
        pom = """
        <project>
          <groupId>   </groupId>
          <artifactId>common-lib</artifactId>
        </project>
        """
        assert parse_coord_map_entry(pom) is None


# ── extract_maven_deps ─────────────────────────────────────────────────────────

COORD_MAP = {
    "com.agilecontent:common-lib": "repo:agilecontent/common-lib",
    "com.agiletv:player-sdk": "repo:agiletv/player-sdk",
}

class TestExtractMavenDeps:
    def test_extracts_matching_internal_dependency(self):
        pom = """
        <project>
          <groupId>com.agilecontent</groupId>
          <artifactId>ingest-service</artifactId>
          <dependencies>
            <dependency>
              <groupId>com.agilecontent</groupId>
              <artifactId>common-lib</artifactId>
              <version>2.1.0</version>
            </dependency>
          </dependencies>
        </project>
        """
        edges = extract_maven_deps("repo:agilecontent/ingest-service", pom, COORD_MAP)
        assert len(edges) == 1
        e = edges[0]
        assert e["source"] == "repo:agilecontent/ingest-service"
        assert e["target"] == "repo:agilecontent/common-lib"
        assert e["type"] == "depends_on"
        assert e["confidence"] == "high"
        assert "pom.xml" in e["evidence"]

    def test_skips_self_edge(self):
        pom = """
        <project>
          <groupId>com.agilecontent</groupId>
          <artifactId>common-lib</artifactId>
          <dependencies>
            <dependency>
              <groupId>com.agilecontent</groupId>
              <artifactId>common-lib</artifactId>
            </dependency>
          </dependencies>
        </project>
        """
        edges = extract_maven_deps("repo:agilecontent/common-lib", pom, COORD_MAP)
        assert edges == []

    def test_skips_agile_java_base(self):
        base_map = {"com.agilecontent:agile-java-base": "repo:agilecontent/agile-java-base"}
        pom = """
        <project>
          <groupId>com.agilecontent</groupId>
          <artifactId>ingest-service</artifactId>
          <dependencies>
            <dependency>
              <groupId>com.agilecontent</groupId>
              <artifactId>agile-java-base</artifactId>
            </dependency>
          </dependencies>
        </project>
        """
        edges = extract_maven_deps("repo:agilecontent/ingest-service", pom, base_map)
        assert edges == []

    def test_skips_unknown_coord(self):
        pom = """
        <project>
          <dependencies>
            <dependency>
              <groupId>com.agilecontent</groupId>
              <artifactId>nonexistent-lib</artifactId>
            </dependency>
          </dependencies>
        </project>
        """
        edges = extract_maven_deps("repo:agilecontent/ingest-service", pom, COORD_MAP)
        assert edges == []

    def test_returns_empty_for_malformed_xml(self):
        edges = extract_maven_deps("repo:agilecontent/foo", "<broken>", COORD_MAP)
        assert edges == []

    def test_version_stored_in_detail(self):
        pom = """
        <project>
          <dependencies>
            <dependency>
              <groupId>com.agilecontent</groupId>
              <artifactId>common-lib</artifactId>
              <version>3.0.0</version>
            </dependency>
          </dependencies>
        </project>
        """
        edges = extract_maven_deps("repo:agilecontent/ingest-service", pom, COORD_MAP)
        assert edges[0]["detail"] == "com.agilecontent:common-lib:3.0.0"


# ── extract_spring_urls ────────────────────────────────────────────────────────

REPO_NAMES = [
    "agilecontent/cms-api",
    "agiletv/cms-api",
    "agilecontent/user-service",
]

class TestExtractSpringUrls:
    def test_extracts_http_url_hostname(self):
        content = "cms.url: http://cms-api:8080/api/v1\n"
        edges = extract_spring_urls(
            "repo:agilecontent/ingest-service", content, REPO_NAMES, "application.yml"
        )
        assert len(edges) == 1
        assert edges[0]["target"] in ("repo:agilecontent/cms-api", "repo:agiletv/cms-api")
        assert edges[0]["type"] == "calls"
        assert edges[0]["confidence"] == "medium"

    def test_extracts_https_url(self):
        content = "url: https://user-service/api\n"
        edges = extract_spring_urls(
            "repo:agilecontent/ingest-service", content, REPO_NAMES, "application.properties"
        )
        assert any(e["target"] == "repo:agilecontent/user-service" for e in edges)

    def test_handles_spring_placeholder_syntax(self):
        content = "url: ${USER_SERVICE_URL:http://user-service:8080}\n"
        edges = extract_spring_urls(
            "repo:agilecontent/ingest-service", content, REPO_NAMES, "application.yml"
        )
        assert any("user-service" in e["target"] for e in edges)

    def test_skips_self_reference(self):
        content = "url: http://ingest-service:8080/health\n"
        edges = extract_spring_urls(
            "repo:agilecontent/ingest-service", content, REPO_NAMES, "application.yml"
        )
        assert all(e["target"] != "repo:agilecontent/ingest-service" for e in edges)

    def test_ignores_external_urls(self):
        content = "url: https://api.example.com/v2\n"
        edges = extract_spring_urls(
            "repo:agilecontent/ingest-service", content, REPO_NAMES, "application.yml"
        )
        assert edges == []

    def test_detail_contains_full_url(self):
        content = "url: http://cms-api:8080/api\n"
        edges = extract_spring_urls(
            "repo:agilecontent/ingest-service", content, REPO_NAMES, "application.yml"
        )
        assert edges[0]["detail"].startswith("http://cms-api")


# ── extract_npm_deps ───────────────────────────────────────────────────────────

NPM_REPO_NAMES = [
    "agilecontent/player-sdk",
    "agiletv/player-sdk",
    "agilecontent/ui-components",
]

class TestExtractNpmDeps:
    def test_extracts_scoped_agilecontent_dep(self):
        pkg = '{"dependencies": {"@agilecontent/player-sdk": "^1.2.3"}}'
        edges = extract_npm_deps("repo:agilecontent/frontend", pkg, NPM_REPO_NAMES)
        assert len(edges) == 1
        assert edges[0]["target"] in ("repo:agilecontent/player-sdk", "repo:agiletv/player-sdk")
        assert edges[0]["type"] == "depends_on"
        assert edges[0]["confidence"] == "high"
        assert "package.json" in edges[0]["evidence"]

    def test_extracts_scoped_agiletv_dep(self):
        pkg = '{"devDependencies": {"@agiletv/ui-components": "^2.0.0"}}'
        edges = extract_npm_deps("repo:agilecontent/frontend", pkg, NPM_REPO_NAMES)
        assert len(edges) == 1
        assert "ui-components" in edges[0]["target"]

    def test_skips_self_edge(self):
        pkg = '{"dependencies": {"@agilecontent/player-sdk": "1.0.0"}}'
        edges = extract_npm_deps("repo:agilecontent/player-sdk", pkg, NPM_REPO_NAMES)
        assert edges == []

    def test_ignores_non_internal_scopes(self):
        pkg = '{"dependencies": {"@angular/core": "^15.0.0", "lodash": "4.17"}}'
        edges = extract_npm_deps("repo:agilecontent/frontend", pkg, NPM_REPO_NAMES)
        assert edges == []

    def test_returns_empty_for_malformed_json(self):
        edges = extract_npm_deps("repo:agilecontent/frontend", "{broken json", NPM_REPO_NAMES)
        assert edges == []

    def test_includes_both_dependencies_and_dev_dependencies(self):
        pkg = """{
          "dependencies": {"@agilecontent/player-sdk": "1.0.0"},
          "devDependencies": {"@agilecontent/ui-components": "2.0.0"}
        }"""
        edges = extract_npm_deps("repo:agilecontent/frontend", pkg, NPM_REPO_NAMES)
        assert len(edges) == 2


# ── deduplicate_edges ──────────────────────────────────────────────────────────

class TestDeduplicateEdges:
    def test_keeps_single_edge_unchanged(self):
        edges = [{"source": "a", "target": "b", "type": "depends_on",
                  "confidence": "high", "evidence": ["pom.xml"], "detail": "x:y:1.0"}]
        assert len(deduplicate_edges(edges)) == 1

    def test_deduplicates_by_source_target_type(self):
        edges = [
            {"source": "a", "target": "b", "type": "depends_on",
             "confidence": "medium", "evidence": ["application.yml"], "detail": "url"},
            {"source": "a", "target": "b", "type": "depends_on",
             "confidence": "high", "evidence": ["pom.xml"], "detail": "x:y"},
        ]
        result = deduplicate_edges(edges)
        assert len(result) == 1
        assert result[0]["confidence"] == "high"

    def test_merges_evidence_arrays(self):
        edges = [
            {"source": "a", "target": "b", "type": "calls",
             "confidence": "medium", "evidence": ["application.yml"], "detail": "u"},
            {"source": "a", "target": "b", "type": "calls",
             "confidence": "medium", "evidence": ["application.properties"], "detail": "u"},
        ]
        result = deduplicate_edges(edges)
        assert set(result[0]["evidence"]) == {"application.yml", "application.properties"}

    def test_different_types_not_merged(self):
        edges = [
            {"source": "a", "target": "b", "type": "depends_on",
             "confidence": "high", "evidence": ["pom.xml"], "detail": "x"},
            {"source": "a", "target": "b", "type": "calls",
             "confidence": "medium", "evidence": ["application.yml"], "detail": "url"},
        ]
        assert len(deduplicate_edges(edges)) == 2
