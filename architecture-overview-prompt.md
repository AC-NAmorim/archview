# Prompt: build a dynamic, drill-down architecture overview of the TVaaS platform

Copy everything below into Claude Code (or an agent with repo access) from the root folder containing the repository checkouts.

---

## Mission

You are analyzing a legacy streaming platform ("TV as a Service") built over 15 years through multiple acquisitions. Documentation is unreliable; ownership is unclear. Your job is a **top-down architecture inventory**: classify every repository into a fixed domain taxonomy, extract the relations between components, and produce (1) a typed architecture graph and (2) an interactive drill-down viewer. Do not invent facts — every classification and edge must cite the evidence file it came from.

## Domain taxonomy (fixed — do not modify, do classify into it)

Slicing principles: flow vs state (pipelines ≠ systems of record), decision vs enforcement (PDP ≠ PEP), change rate and single-team ownership.

1. **Content supply chain** — VOD and live ingest, transcode, packaging, QC, automated metadata enrichment (process/flow)
2. **Content management** — CMS as system of record: catalog, EPG, rights and licensing windows (state)
3. **Playout & time-shift** — linear scheduling/playout, catchup, startover, nPVR
4. **Delivery** — origin, CDN/multi-CDN steering; enforcement points only: stream tokens, geo-blocking, DRM license delivery (PEP)
5. **Identity & entitlements** — authN/Z, subscriber system of record, entitlement decision engine (PDP)
6. **Monetization (execution)** — subscription lifecycle, purchase flows, billing events, payments, SSAI
7. **Experience** — client apps (STB, mobile, Smart TV, cast, web), player, search, recommendations, content rails
8. **Data & analytics** — QoE/QoS, BI, audience data, per-tenant reporting
9. **B2B tenant operations (control plane)** — tenant onboarding, per-tenant commercial/branding/catalog configuration, care tools, SLA reporting
10. **Platform foundation** — cloud infra, API gateway, service mesh, multi-tenancy layer, observability, CI/CD
11. **Security (cross-cutting)** — DRM strategy, CAS, watermarking, anti-piracy, secrets, compliance

## Phase 1 — repository inventory

List every repo. For each capture: name, primary language(s), last commit date, commit frequency over the past 12 months, and contributor teams (from CODEOWNERS or top committers). Mark repos with no commits in 18+ months as `dormant`.

## Phase 2 — signal extraction (per repo)

Read, in priority order: README and /docs, build manifests (package.json, pom.xml, go.mod, requirements.txt, .csproj), API definitions (OpenAPI/proto/GraphQL schemas, route registrations), DB migrations and schema files, message topic declarations (Kafka/RabbitMQ/SQS producers and consumers), deploy configs (Dockerfile, k8s manifests, helm charts, terraform), env var references to other services. Summarize what the repo actually does in ≤3 sentences, citing the files that support the summary.

## Phase 3 — classification into the tree

Assign each repo to exactly one domain and a capability within it (create capability names as needed; domains are fixed). Record:

- `confidence`: high / medium / low
- `evidence`: file paths that justify the assignment
- Flags:
  - `split-candidate` — repo matches 2+ domains (entangled logic; name both domains)
  - `duplicate` — 2+ repos serve the same capability (acquisition seam; cross-reference them)
  - `orphan` — matches no domain (dead code or unclassified glue)
  - `dormant` — from Phase 1
- Capabilities with **zero** repos are gaps — list them explicitly.

Produce a confirmation list: every medium/low-confidence assignment as a question a human can answer in one line.

## Phase 4 — relation (edge) extraction

Extract typed edges with evidence. Static sources, in order of confidence:

1. **Shared database tables** — two repos whose migrations/queries touch the same schema/table → `reads_writes` edges to a shared `datastore` node (highest-value finding: data-layer coupling)
2. **API calls** — HTTP/gRPC client calls matched against another repo's route definitions → `calls`
3. **Messaging** — producer/consumer pairs on the same topic → `publishes_to` / `consumes_from`
4. **Build dependencies** — internal library imports → `depends_on`
5. **Deploy references** — k8s service names, env var URLs → `calls` (medium confidence)
6. **Ownership** — CODEOWNERS/committers → `owned_by` (team nodes)

If Istio/Kong telemetry exports are provided in `./telemetry/`, ingest them as ground-truth `calls` edges with traffic volume — mark static edges confirmed/contradicted by runtime data.

## Phase 5 — outputs

Write to `./architecture-overview/`:

1. **`architecture-graph.json`** — the typed graph:
   - Node types: `domain`, `capability`, `repo`, `service`, `datastore`, `topic`, `team`. Common fields: `id`, `type`, `name`, `domain`, `flags[]`, `evidence[]`, `summary`
   - Edge types: `belongs_to`, `calls`, `reads_writes`, `publishes_to`, `consumes_from`, `depends_on`, `owned_by`. Fields: `source`, `target`, `type`, `confidence`, `evidence[]`, `traffic` (if telemetry)
2. **`index.html`** — self-contained interactive viewer (single file, no build step, vanilla JS + one CDN graph/diagram lib max):
   - Overview: the four-plane domain map (experience / decision / content-flow / horizontals + dashed cross-cutting security), each domain card showing repo count, health (green = healthy, amber = duplicates or unclear, red = gap), and cross-domain coupling score (count of edges leaving the domain, shared-datastore edges weighted ×3)
   - Drill-down: domain → capabilities → repos/services, with flags, ownership, last-activity, and each node's edges (grouped by type, with evidence paths)
   - A "findings" panel: all duplicates, split-candidates, orphans, gaps, and the top-10 highest-coupling edges
   - Search across all nodes
   - Loads `architecture-graph.json` so the viewer regenerates by re-running the analysis, without touching the HTML
3. **`findings.md`** — executive summary: per-domain inventory table, duplicate map (which acquisition seams), gap list, coupling hotspots (the shared-database analysis first), and the human-confirmation question list from Phase 3

## Rules

- Evidence or it didn't happen: no classification, summary, or edge without cited file paths
- Never modify the analyzed repos; write only inside `./architecture-overview/`
- Prefer fewer, high-confidence edges over exhaustive guesses; record what was *not* analyzable (binary blobs, generated code, unreadable formats)
- Process repos in batches and persist intermediate results after each batch so the run is resumable
- Finish with: total repos classified, % high confidence, edge counts by type, and the 5 questions whose answers would most improve the graph
