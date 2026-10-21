# 📘 Software Requirements Specification (SRS)
## Project: CloudGuard FinOps Engine (IEEE 830 Standard Format)

---

## 1. Introduction

### 1.1 Purpose
This document details the functional, non-functional, interface, and safety requirements for the **CloudGuard FinOps Engine**. It serves as the authoritative technical specification for software developers, QA engineers, and system architects.

### 1.2 System Overview
CloudGuard is a microservice-based Python application that interfaces with AWS SDK (`boto3`), GitHub REST/GraphQL API (`PyGithub`), and the **StateGuard** determinism framework to automate infrastructure cost optimization.

---

## 2. System Interfaces & External Integrations

### 2.1 AWS API Interface (`boto3`)
- **STS (`sts:AssumeRole`):** Assume customer cross-account Read-Only IAM role.
- **Cost Explorer (`ce:GetCostAndUsage`):** Fetch historical daily cost per resource tag/ARN.
- **CloudWatch (`cloudwatch:GetMetricData`):** Query 90-day time-series telemetry (`CPUUtilization`, `FreeableMemory`, `WriteIOPS`, `ReadIOPS`).
- **EC2 / RDS SDK (`ec2:Describe*`, `rds:Describe*`):** Fetch active instance metadata and specs.

### 2.2 GitHub / GitLab Interface
- **Repository Read:** Fetch HCL code tree (`.tf` files) via Git Blob API.
- **Branch Creation:** `POST /repos/{owner}/{repo}/git/refs`
- **File Update:** `PUT /repos/{owner}/{repo}/contents/{path}`
- **Pull Request Creation:** `POST /repos/{owner}/{repo}/pulls`

### 2.3 StateGuard Governance Framework
- **State Proxy:** `GuardedState` wrapping standard JSON execution state.
- **Invariant Engine:** `InvariantRegistry` evaluating boolean assertions before state commit.
- **Drift Engine:** `DriftDetector` computing running Z-Scores on cost deltas.
- **Saga Engine:** `SagaCoordinator` handling LIFO compensation execution.

---

## 3. Functional Requirements

### FR-1: Telemetry & Metric Ingestion
- **FR-1.1:** The system MUST query 90 days of CloudWatch telemetry for candidate resources.
- **FR-1.2:** The system MUST calculate the 50th, 95th, and 99th percentiles for CPU, RAM, and Disk IOPS.
- **FR-1.3:** If CloudWatch memory metrics are missing (e.g., CloudWatch Agent not installed), the system MUST default to conservative memory safety bounds (+50% buffer).

### FR-2: HCL Parsing & Resource Mapping
- **FR-2.1:** The system MUST parse `.tf` files using AST-based HCL parsing.
- **FR-2.2:** The system MUST map AWS Resource ARNs (from CloudWatch/Cost Explorer) to specific Terraform code block line numbers in GitHub files.
- **FR-2.3:** The parser MUST preserve code formatting, comments, and non-target blocks without corruption.

### FR-3: Multi-Agent Optimization Logic
- **FR-3.1 (FinOps Agent):** Propose smallest instance family matching 50th percentile load.
- **FR-3.2 (Architecture Agent):** Evaluate 99th percentile load. Reject proposals where:
  $$\text{Proposed RAM} < \text{Peak Historical Memory} \times 1.25$$
- **FR-3.3 (Security Agent):** Reject proposals where encryption flags (`storage_encrypted`, `kms_key_id`) or security tags are omitted.

### FR-4: StateGuard Safety Enforcement
- **FR-4.1 (Pre-Commit Invariant):**
  ```python
  @registry.invariant(name="cpu_headroom_check", mode="block")
  def check_cpu_headroom(state):
      return state["peak_cpu_percent"] <= 80.0
  ```
- **FR-4.2 (Drift Detection):**
  ```python
  detector.watch("estimated_cost_delta", z_threshold=3.5, mode="block")
  ```
  If Z-score $> 3.5$, raise `DriftAnomalyViolation` and abort execution.
- **FR-4.3 (Saga Rollback):** If GitHub PR creation fails on step $N$, execute compensation handlers for steps $1 \dots N-1$ in LIFO order (closing open PRs).

---

## 4. Performance & Scalability Requirements

- **Concurrency:** Process up to 50 AWS accounts in parallel using Python `asyncio` and worker pool queues.
- **API Rate Limiting:** Implement exponential backoff for GitHub REST API (5,000 req/hr limit) and AWS API throttles (`RequestLimitExceeded`).
- **Memory Footprint:** Keep memory consumption under 512 MB per worker instance.

---

## 5. Security & Compliance Requirements

- **Credential Storage:** Store zero AWS secret keys. Store only Customer Role ARNs.
- **Encryption:** All database records (OAuth tokens, Role ARNs) encrypted with AES-256-GCM.
- **Transport Security:** TLS 1.3 enforced for all outbound API requests.
