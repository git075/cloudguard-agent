# CloudGuard Production Readiness — Task Tracker

## Phase 1: Real AWS Telemetry Integration ✅ COMPLETE
- [x] Phase 1.1 — Expand ResourceTelemetry model (IOPS, Network, DB Connections fields)
- [x] Phase 1.2 — Full CloudWatch metric fetching (Memory, IOPS, Network, DB Connections)
- [x] Phase 1.3 — Real AWS Cost Explorer integration (live monthly_cost_usd)
- [x] Phase 1.4 — AWS Pricing API note added (quarterly update process documented)
- [x] Phase 1.5 — Multi-resource auto-discovery (RDS + EC2 enumerate all instances)
- [x] Phase 1.6 — ExternalId Confused Deputy protection in AssumeRole
- [x] Phase 1.7 — botocore adaptive retry config (handles AWS throttling)

## Phase 2: Intelligent Agent Logic (Smart Instance Selector) ✅ COMPLETE
- [x] Phase 2.1 — Constraint-based optimal instance selector (_select_optimal_spec)
- [x] Phase 2.2 — 25+ instance catalog (r5, r6g, m6g, t4g, m5, m6g families)
- [x] Phase 2.3 — Graviton upgrade preference (r6g/m6g preferred over r5/m5)
- [x] Phase 2.4 — DB connection limit enforcement (max_conn_rds per instance type)
- [x] Phase 2.5 — Burstable exclusion logic (t4g excluded if avg CPU > 20% or IOPS > 3000)
- [x] Phase 2.6 — All 43 tests pass (3 skipped: FastAPI client tests)

## Phase 3: Multi-Tenant PostgreSQL Database & Auth ✅ COMPLETE
- [x] Phase 3.1 — SQLAlchemy models (customers, aws_accounts, pull_request_logs, scan_jobs)
- [x] Phase 3.2 — Alembic DB migrations
- [x] Phase 3.3 — JWT Authentication middleware
- [x] Phase 3.4 — ExternalId per-customer generation


## Phase 4: Async Job Queue & Distributed Workers ✅ COMPLETE
- [x] Phase 4.1 — Celery task definition (scan_worker.py)
- [x] Phase 4.2 — FastAPI trigger endpoint using .delay()
- [x] Phase 4.3 — Celery Beat nightly scheduled scans
- [x] Phase 4.4 — Docker Compose (api + worker + redis + postgres)


## Phase 5: GitHub App + Multi-File PRs ✅ COMPLETE
- [x] Phase 5.1 — GitHub App installation token flow
- [x] Phase 5.2 — Multi-resource batch PR generation


## Phase 6: Observability ✅ COMPLETE
- [x] Phase 6.1 — Prometheus metrics
- [x] Phase 6.2 — Structured JSON logging
- [x] Phase 6.3 — Sentry error tracking


## Phase 7: Deployment ✅ COMPLETE
- [x] Phase 7.1 — Dockerfile
- [x] Phase 7.2 — docker-compose.yml
- [x] Phase 7.3 — GitHub Actions CI/CD

## Phase 8: Interactive Web UI Dashboard ✅ COMPLETE
- [x] Phase 8.1 — Interactive Glassmorphic Dark-Mode Web Dashboard (`src/ui/static/index.html`)
- [x] Phase 8.2 — Zero-dependency frontend (Tailwind CSS, SVG icons, pure ES6/Alpine UI)
- [x] Phase 8.3 — Integrated FastAPI dashboard endpoints (`/`, `/dashboard`, `/api/v1/auth`, `/api/v1/scans`)
- [x] Phase 8.4 — Live StateGuard lineage inspector, active GitOps PR diff viewer, and autonomous scan trigger
- [x] Phase 8.5 — 66/66 test cases passing (including UI HTML serving test)

## Phase 9: Joint Multi-Metric Constraints & Zero-Error Swarm Architecture ✅ COMPLETE
- [x] Phase 9.1 — Core Collapse Prevention in FinOpsAgent (vCPU capacity scaling with Graviton IPC factor)
- [x] Phase 9.2 — Network Bandwidth (Mbps) and Storage EBS IOPS (MB/s) constraints added to catalog & selection
- [x] Phase 9.3 — Joint multi-metric verification in ArchitectureAgent (projected CPU <= 80%, RAM buffer >= 1.25x, RDS max connections <= 70%)
- [x] Phase 9.4 — Dynamic catalog counter-proposer replacing legacy 4-tier static if/else stub
- [x] Phase 9.5 — Two-way swarm consensus negotiation loop in SwarmOrchestrator
- [x] Phase 9.6 — Comprehensive test suite expanded to 69/69 passing tests
- [x] Phase 9.7 — LEARNING_GUIDE.md Section 13 added explaining multi-metric hazards and mathematical solutions

## Phase 10: StateGuard Governance Hard Invariants & Exhaustive Metric Engine ✅ COMPLETE
- [x] Phase 10.1 — Enforce Engine Architecture Compatibility in FinOps & StateGuard Rule 12 (Block Graviton on Oracle / SQL Server)
- [x] Phase 10.2 — Enforce EC2 Architecture Lock in FinOps & StateGuard Rule 13 (x86 AMI lock prevents ARM migration without explicit flag)
- [x] Phase 10.3 — Enforce Multi-AZ 2.0x cost multiplier across FinOps proposal and StateGuard state
- [x] Phase 10.4 — Add StateGuard Rule 9 (Projected CPU headroom check <= 80%)
- [x] Phase 10.5 — Add StateGuard Rule 10 (RDS Max DB connections limit check <= 70%)
- [x] Phase 10.6 — Add StateGuard Rule 11 (Verified catalog instance check)
- [x] Phase 10.7 — Add unit tests in test_governance.py and test_agents.py (77/77 tests passing)
- [x] Phase 10.8 — Update LEARNING_GUIDE.md with Sections 14 and 15 (Exhaustive Encyclopedia of all EC2 & RDS Sizing Metrics)

## Phase 11: Production Hardening, Security Audits & Gap Remediation ✅ COMPLETE
- [x] Phase 11.1 — AWS Telemetry FreeableMemory aggregation fix (_min_val across 90-day daily minimums)
- [x] Phase 11.2 — EC2 Physical RAM Catalog & 75% unmonitored safety floor
- [x] Phase 11.3 — HCL Parser brace-depth tracking isolating mutations to target block in multi-resource files
- [x] Phase 11.4 — GitOps dynamic default branch resolution (main/master/develop)
- [x] Phase 11.5 — GitOps batch PR sequential file state & SHA tracking preventing mutation overwrites
- [x] Phase 11.6 — StateGuard governance engine rejection status preservation (rejected state retained)
- [x] Phase 11.7 — SecurityAgent enterprise audits (EC2 root EBS encryption, RDS backup retention, deletion protection)
- [x] Phase 11.8 — FinOps pricing catalog expansion (c5, c6g, r5, r6g) & dynamic vCPU inference
- [x] Phase 11.9 — Production JWT secret key mandatory enforcement (fails fast on startup)
- [x] Phase 11.10 — SQLAlchemy connection pooling (pool_pre_ping, pool_size, recycle, timeout)
- [x] Phase 11.11 — Scan router unified demo/tenant pipeline and removed shadowed route
- [x] Phase 11.12 — Container hardening (non-root appuser UID 10001, Uvicorn 4 workers, Flower basic auth)
- [x] Phase 11.13 — Comprehensive test suite expanded to 82/82 passing tests (test_production_hardening.py)
- [x] Phase 11.14 — LEARNING_GUIDE.md Section 16 added documenting all 12 pre-production fixes



