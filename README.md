# ⚡ CloudGuard FinOps
> **Autonomous Multi-Agent GitOps Cloud Cost Optimization Engine — Powered by StateGuard**

[![CI/CD Pipeline](https://github.com/git075/cloudguard-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/git075/cloudguard-agent/actions)
![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)
![Tests](https://img.shields.io/badge/tests-82%2F82%20passing-brightgreen.svg)
![License](https://img.shields.io/badge/license-Apache%202.0-green.svg)
![Security](https://img.shields.io/badge/governance-StateGuard%20Guarded-indigo.svg)

---

## 📌 What is CloudGuard FinOps?

**CloudGuard FinOps** is an autonomous multi-agent platform that connects to enterprise AWS accounts via **Read-Only IAM**, continuously evaluates 90-day utilization metrics (CPU, RAM, IOPS, Network, DB Connections), and opens zero-risk **Terraform Pull Requests** on GitHub to eliminate cloud waste.

Unlike naive scripts or unconstrained LLMs, CloudGuard is guarded by **[StateGuard](https://pypi.org/project/stateguard-core/)**: an ACID-like deterministic governance layer that enforces hard system invariants, detects statistical drift, and guarantees that proposed infrastructure mutations never compromise application reliability, exceed headroom buffers, or violate SOC 2 / ISO 27001 compliance.

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                             MULTI-AGENT SWARM CONSENSUS                          │
│                                                                                  │
│   AWS Telemetry (90d) ──► FinOps Agent (Cost Optimization & Graviton Selector)   │
│                                      │                                           │
│                                      ▼                                           │
│                          Architecture & Reliability Agent                        │
│                   (Evaluates RAM Buffer ≥ 1.25x, Projected CPU ≤ 80%)            │
│                                      │                                           │
│                                      ▼                                           │
│                           Security & Compliance Agent                            │
│                 (Audits EBS/RDS Encryption, Retention, SOC 2 Tags)               │
│                                      │                                           │
│                                      ▼                                           │
│                          StateGuard Governance Engine                            │
│                   (ACID Proxy + Pre-Commit Invariants + Saga LIFO)               │
│                                      │                                           │
│                                      ▼                                           │
│                     GitOps Engine (Pull Request on GitHub)                       │
└──────────────────────────────────────────────────────────────────────────────────┘
```

---

## 🚀 Key Features

* **Multi-Agent Swarm Debate:** Collaborative consensus between FinOps (cost minimizer), Architecture (reliability guard), and Security (compliance auditor) agents with dynamic counter-proposals.
* **StateGuard Governance Layer:** Transactional snapshot isolation (`GuardedState`), 13 business invariant rules, statistical Z-score drift detection (`DriftDetector`), and Saga compensations.
* **Real AWS Ingestion (`boto3`):** Single-call batch metric queries via CloudWatch `get_metric_data()`, STS `AssumeRole` with `ExternalId` Confused Deputy protection, and real Cost Explorer billing extraction.
* **Precise AST Terraform Mutation:** Lexical brace-depth tracking parser accurately updates target resource blocks in complex multi-resource `.tf` files without syntax corruption.
* **Automated GitOps Engine:** Creates isolated Git branches, composes multi-resource batch mutations sequentially, opens rich Markdown Pull Requests, and cleans up branches via Saga compensation if operations fail.
* **Enterprise Asynchronous Architecture:** Scalable Celery worker cluster backed by Redis and multi-tenant PostgreSQL with connection pooling and Celery Beat nightly automated scans.
* **Dark-Mode Glassmorphism Dashboard:** Responsive, zero-build web interface (`/dashboard`) with real-time KPI metrics, active PR inspection, and StateGuard audit lineage visualization.

---

## 🏗️ Architecture & Sizing Dimensions

CloudGuard evaluates cloud resources across **6 exhaustive dimensions** before approving any downsizing proposal:

| Dimension | Telemetry Metrics Evaluated | Invariant Rule / Safety Constraint |
| :--- | :--- | :--- |
| **1. Compute & CPU** | `CPUUtilization` (90d max & avg), CPU Credits | $\text{Projected CPU} \le 80\%$, Burstable exclusion if CPU $> 20\%$ |
| **2. Memory & RAM** | `FreeableMemory` (90d min), CWAgent RAM % | $\text{Proposed RAM} \ge \text{Peak Used} \times 1.25$, Min $4\text{ GB}$ Floor |
| **3. Storage & IOPS** | `ReadIOPS`, `WriteIOPS`, `DiskQueueDepth` | IOPS $\le$ Volume Limit, Disk latency $< 5\text{ms}$ |
| **4. Network Bandwidth** | `NetworkIn`, `NetworkOut`, PPS Limits | Baseline bandwidth $\ge \text{Peak} \times 1.20$ |
| **5. Database Engine** | `DatabaseConnections`, WAL Disk Usage, Lag | Concurrent connections $\le 70\%$ of new instance max |
| **6. Architecture / OS** | AMI CPU Arch, DB Engine Licensing | Blocks Graviton on Oracle / MS SQL; requires flag for x86 AMIs |

---

## ⚡ Quickstart Guide

### Option 1: Docker Compose (Full Stack)

Run the complete multi-tenant platform (PostgreSQL, Redis, Celery Worker, Celery Beat, FastAPI API Gateway, and Flower UI) with a single command:

```bash
# 1. Clone repository
git clone https://github.com/git075/cloudguard-agent.git
cd cloudguard-agent

# 2. Copy and configure environment variables
cp .env.example .env

# 3. Launch stack
docker-compose up --build -d
```

Access the services:
* **Executive Dashboard:** [http://localhost:8000/dashboard](http://localhost:8000/dashboard)
* **REST API Documentation (Swagger):** [http://localhost:8000/docs](http://localhost:8000/docs)
* **Prometheus Metrics:** [http://localhost:8000/metrics](http://localhost:8000/metrics)
* **Celery Flower Dashboard:** [http://localhost:5555](http://localhost:5555) *(Credentials: `admin` / `cloudguard_secret`)*

---

### Option 2: Local Python Development

```bash
# 1. Set up virtual environment
python3 -m venv venv
source venv/bin/activate

# 2. Install dependencies
pip install --upgrade pip
pip install -r requirements.txt
pip install celery redis flower asyncpg email-validator greenlet bcrypt passlib PyJWT

# 3. Run all unit and integration tests
PYTHONPATH=. pytest tests/ -v
```

---

## 🧪 Automated Test Suite

CloudGuard includes **82 comprehensive automated test cases** covering agent negotiations, StateGuard invariants, security validations, and Celery asynchronous dispatch:

```bash
PYTHONPATH=. pytest tests/ -v
```

```text
============================== 82 passed in 2.56s ==============================
- tests/test_agents.py (14 tests)             - Swarm debate & consensus negotiation
- tests/test_governance.py (14 tests)         - StateGuard GuardedState & Invariant Rules
- tests/test_production_hardening.py (5 tests)- EC2 safety floor, brace depth, JWT security
- tests/test_security.py (8 tests)            - IAM Role ARN regex, path traversal prevention
- tests/test_scan_worker.py (4 tests)         - Celery worker execution & Beat scheduler
- tests/test_database.py (4 tests)            - PostgreSQL multi-tenant isolation
- tests/test_auth.py (5 tests)                - Bcrypt hashing & JWT lifecycle
- tests/test_hcl_parser.py (4 tests)          - AST parsing & scoped block mutation
- tests/test_gitops.py (8 tests)              - PR generation & Saga rollback compensation
- tests/test_observability.py (3 tests)       - Prometheus metrics & structured JSON logs
- tests/test_localstack.py (4 tests)          - LocalStack STS AssumeRole & CloudWatch
- tests/test_e2e.py (4 tests)                 - Full pipeline end-to-end optimizations
```

---

## 📁 Repository Structure

```
cloudguard-agent/
├── .github/workflows/ci.yml       # GitHub Actions CI/CD test & Docker build pipeline
├── alembic/                       # PostgreSQL database migrations
├── docs/                          # Complete architectural & engineering guides
│   ├── ARCHITECTURE.md            # Microservice architecture specification
│   ├── SYSTEM_DESIGN.md           # Production system design & capacity planning
│   ├── PRD.md                     # Product requirements document
│   ├── SRS.md                     # Software requirements specification (IEEE 830)
│   ├── API_SCHEMA.md              # REST API & DB schema documentation
│   ├── UI_DESIGN.md               # Glassmorphic UI design tokens
│   ├── LEARNING_GUIDE.md          # 16-chapter engineering guide from zero to prod
│   └── PROGRESS_TRACKER.md        # Comprehensive milestone tracker
├── src/
│   ├── agents/                    # FinOps, Arch, Security & Swarm Orchestrator
│   ├── api/                       # FastAPI route handlers (Auth, Scans, Dependencies)
│   ├── db/                        # SQLAlchemy async & sync session managers
│   ├── governance/                # StateGuard proxy, invariants, drift & Saga engine
│   ├── jobs/                      # Celery application & background scan workers
│   ├── models/                    # Pydantic schemas, SQLAlchemy tables, Swarm models
│   ├── services/                  # AWS Collector, HCL Parser, GitOps, Auth
│   ├── ui/                        # Web dashboard API & static HTML5 glassmorphism SPA
│   └── utils/                     # Logging, Prometheus metrics, and input sanitizers
├── tests/                         # 82 automated unit & integration test files
├── docker-compose.yml             # Local production orchestration
├── Dockerfile                     # Hardened non-root container image
├── requirements.txt               # Pinned Python dependencies
└── README.md
```

---

## 📖 In-Depth Learning Guide

For engineers seeking a deep conceptual understanding of AWS telemetry formulas, Little's Law for disk queues, multi-metric mathematical sizing constraints, and StateGuard governance, read our companion document:
👉 **[The CloudGuard Production Learning Guide](docs/LEARNING_GUIDE.md)**

---

## 📄 License

This project is licensed under the Apache 2.0 License - see the [LICENSE](LICENSE) file for details.
