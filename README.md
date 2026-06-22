# archView

Platform architecture knowledge base for a TV-as-a-Service (TVaaS) organisation. Two tools in one repo:

1. **Repo Health Dashboard** — scans all GitHub/GitLab repos, scores governance health, surfaces CVEs, and generates an interactive HTML dashboard.
2. **Architecture Viewer** — classifies every repo into a fixed domain/subdomain taxonomy using AI, maps GitHub team ownership, and produces a drill-down architecture map.

---

## Prerequisites

| Tool | Purpose |
|---|---|
| Python 3.12+ | Runtime |
| [uv](https://docs.astral.sh/uv/) | Fast dependency management |
| [gh CLI](https://cli.github.com/) | GitHub auth (no token setup needed if already logged in) |
| [gcloud CLI](https://cloud.google.com/sdk) | Vertex AI auth for classification |
| Docker + Docker Compose | Container deployment (optional) |

---

## Setup

```bash
git clone <this-repo> && cd archView

# Create virtualenv and install dependencies
uv venv
uv pip install -r requirements.txt

# Activate (or prefix every command with `.venv/bin/python`)
source .venv/bin/activate

# Copy and fill in your config
cp .env.example .env
```

### `.env` minimum config

```dotenv
# GitHub org(s) to scan — token picked up automatically from gh CLI
GITHUB_ORGS=your-org

# GitLab (self-hosted) — generate token at:
# https://gitlab.agilecontent.com/-/profile/personal_access_tokens  (scope: read_api)
GITLAB_TOKEN=glpat_...
GITLAB_URL=https://gitlab.agilecontent.com
GITLAB_GROUPS=your-group,your-group/subgroup   # run discover_gitlab_groups to find these

# Vertex AI — picked up from gcloud CLI if not set here
# GOOGLE_CLOUD_PROJECT=your-gcp-project
# ANTHROPIC_VERTEX_REGION=europe-west1
```

Auth is resolved automatically:
- **GitHub token**: reads from `GITHUB_TOKEN` env var, or falls back to `gh auth token`
- **GitLab token**: reads from `GITLAB_TOKEN` env var (no CLI fallback — generate a Personal Access Token)
- **Vertex AI**: reads from `GOOGLE_CLOUD_PROJECT` env var, or falls back to `gcloud config get-value project`

### Discover GitLab groups

After setting `GITLAB_TOKEN`, find the right group paths to add to `GITLAB_GROUPS`:

```bash
python -m scripts.discover_gitlab_groups
```

---

## Phase 1 — Repo Health Dashboard + CVE Report

Scans all repos in the configured GitHub org(s), scores each one on staleness, ownership, CI health, and security alerts, then generates an interactive dashboard.

### Run

```bash
python -m discovery.main
```

This produces in `output/`:

| File | Contents |
|---|---|
| `repo_health.json` | Full repo data with health scores and CVE details |
| `repo_health.csv` | Spreadsheet-friendly version |
| `report.md` | Executive summary: archival candidates, governance coverage, security alerts |

### Generate the dashboard

```bash
python -m scripts.generate_dashboard --input output/repo_health.json
open output/dashboard.html
```

### Dashboard features

- **KPI strip**: Dormant / Ungoverned / Needs Work / Governed repo counts
- **Governance bars**: CODEOWNERS, README, and CI pipeline coverage %
- **Sortable, filterable table**: click column headers, use tier/source/language dropdowns, click any tag chip to filter
- **CVE panel** (below the table): every open security alert with repo, package, ecosystem, severity, CVSS score, CVE ID linked to NVD, and summary

### CVE report details

CVE data is fetched automatically during the scan for any repo that has open Dependabot alerts. The dashboard CVE panel shows:

- Repo name (linked to its Dependabot page)
- Package name and ecosystem (Maven, npm, pip…)
- Severity badge: **CRITICAL** / **HIGH** / **MODERATE** / **LOW**
- CVSS score (colour-coded)
- CVE ID linked directly to [nvd.nist.gov](https://nvd.nist.gov)
- Advisory summary

Filter by severity using the dropdown in the panel header. Sort any column by clicking its header.

> **Token scope required for CVE data**: the GitHub token must have `security_events: read` (fine-grained) or the `repo` scope (classic). The `gh` CLI token typically includes this — run `gh auth status` to confirm.

---

## Phase 2 — Architecture Classification Viewer

Classifies every repo into the TVaaS domain/subdomain taxonomy using Claude on Vertex AI, maps GitHub team ownership, and generates a drill-down architecture map.

### Domain taxonomy

11 fixed domains (defined in `discovery/taxonomy.json`):

| # | Domain | Subdomains |
|---|---|---|
| 1 | Content supply chain | VOD Ingest · Live Ingest · Transcode & Packaging · QC & Enrichment |
| 2 | Content management | Catalog · EPG · Rights & Licensing · Editorial Tools |
| 3 | Playout & time-shift | Linear Playout · Catchup & Startover · nPVR |
| 4 | Delivery | Origin · CDN Steering · DRM & Stream Protection · Geo-blocking |
| 5 | Identity & entitlements | Authentication · Subscriber Management · Entitlement Engine |
| 6 | Monetization | Subscription Lifecycle · Billing & Payments · Ads & SSAI |
| 7 | Experience | Apps · Player · Discovery & Search · Recommendations · Content Rails |
| 8 | Data & analytics | QoE / QoS · BI & Reporting · Audience Data |
| 9 | B2B tenant operations | Tenant Onboarding · Configuration & Branding · Care Tools · SLA Reporting |
| 10 | Platform foundation | Cloud Infra · API Gateway · Service Mesh · Observability · CI/CD |
| 11 | Security | DRM Strategy · CAS · Watermarking · Anti-piracy |

### Run

```bash
# Classify all repos (uses cached results — safe to re-run)
python -m scripts.pilot --all

# Or start with a faster pilot of the 25 most recently active repos
python -m scripts.pilot --top 25
```

Opens `architecture-overview/index.html` automatically. On subsequent runs, already-classified repos are served from `.cache/` instantly — only new repos hit the API.

### Viewer features

- **Domain map** (left): architecture planes from the draw.io diagram, colour-coded by ownership model (purple = core, beige = hybrid, green = delegatable); proportional confidence bar per domain
- **Subdomain + team panel** (middle): all subdomains always visible — empty ones marked as **gap**; GitHub teams section below
- **Repo detail** (right): sorted by confidence, expandable cards with capability, summary, and evidence files
- **Breadcrumb navigation**: Architecture / Domain / Subdomain — each segment clickable
- **Global search**: searches all 784 repos across all domains
- **Resizable panels**: drag the handles between panels

### Confidence labels

Classification confidence reflects how many readable files were found per repo:

| Label | Meaning |
|---|---|
| **Verified** | Strong signal — README, pom.xml, package.json, or API specs found |
| **Inferred** | Partial signal — some files found but ambiguous |
| **Name only** | No readable files — classified from repo name alone |

---

## Container Deployment

### Serve the viewer (static snapshot)

```bash
# Build image with current index.html baked in
docker build -f Dockerfile.viewer -t archview-viewer:latest .

# Run on port 8080
docker run -p 8080:80 archview-viewer:latest
```

### Run the full pipeline in a container

```bash
# Scan + score repos → output/
docker compose --profile pipeline run pipeline python -m discovery.main

# Generate dashboard
docker compose --profile pipeline run pipeline \
  python -m scripts.generate_dashboard --input output/repo_health.json

# Classify all repos → architecture-overview/
docker compose --profile pipeline run pipeline python -m scripts.pilot --all
```

GCP credentials are mounted from `~/.config/gcloud` automatically (set by `gcloud auth application-default login`).

### Serve live output (volume-mounted)

```bash
# Starts nginx serving whatever is in architecture-overview/ on the host
docker compose up viewer
# → http://localhost:8080
```

---

## Project structure

```
archView/
├── discovery/
│   ├── config.py          # Auth resolution (GitHub token, GCP project/region)
│   ├── taxonomy.json      # Fixed domain/subdomain definitions
│   ├── models.py          # RepoSnapshot, HealthScore, CVEAlert
│   ├── health.py          # Health scoring (staleness, ownership, risk, activity)
│   ├── file_fetcher.py    # GitHub file content via tree API
│   ├── classifier.py      # Vertex AI classification (AnthropicVertex)
│   ├── exporters.py       # CSV, JSON, Markdown report
│   └── scanners/
│       ├── github.py      # GitHub GraphQL + REST scanner, CVE enrichment, team fetch
│       └── gitlab.py      # GitLab REST scanner
├── scripts/
│   ├── demo.py            # Runs health pipeline on mock data
│   ├── generate_dashboard.py  # Generates output/dashboard.html from JSON
│   └── pilot.py           # Classification pipeline + architecture viewer
├── output/                # Repo health outputs (gitignored)
├── architecture-overview/ # Architecture viewer outputs (gitignored)
│   └── .cache/            # Per-repo classification cache
├── tvaas-domain-split.drawio  # Domain architecture diagram
├── Dockerfile             # Pipeline container
├── Dockerfile.viewer      # Viewer snapshot container
├── docker-compose.yml     # Local orchestration
└── .env.example           # Config reference
```
