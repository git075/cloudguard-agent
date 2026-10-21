# 🏗️ System Architecture Specification
## Project: CloudGuard FinOps Engine

---

## 1. High-Level System Architecture

CloudGuard is designed as an event-driven microservice architecture with isolated worker pipelines, stateless agent execution, and an append-only audit trail.

```
                  ┌───────────────────────────────────────────────────┐
                  │                 NEXT.JS DASHBOARD                 │
                  │  (User Onboarding, PR Feeds, Audit Log Viewer)    │
                  └─────────────────────────┬─────────────────────────┘
                                            │ REST API / Webhooks
                                            ▼
                  ┌───────────────────────────────────────────────────┐
                  │                 FASTAPI CONTROL PLANE             │
                  │        (Auth, Job Scheduler, Webhook Receiver)     │
                  └─────────────────────────┬─────────────────────────┘
                                            │ Async Task Queue (Redis / Celery)
                                            ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                               CLOUDGUARD WORKER ENGINE                                 │
│                                                                                        │
│  ┌───────────────────────┐   ┌───────────────────────┐   ┌──────────────────────────┐  │
│  │ AWS Ingestion Engine  │   │  GitHub IaC Parser    │   │ Multi-Agent Swarm        │  │
│  │ (Boto3 / Cost Explorer│──►│  (python-hcl2 / AST)  │──►│ (FinOps, Arch, Security) │  │
│  └───────────────────────┘   └───────────────────────┘   └─────────────┬────────────┘  │
│                                                                        │               │
│                                                                        ▼               │
│                                                          ┌──────────────────────────┐  │
│                                                          │ StateGuard Safety Engine │  │
│                                                          │ (Invariants, Drift, Saga)│  │
│                                                          └─────────────┬────────────┘  │
│                                                                        │               │
│                                                                        ▼               │
│                                                          ┌──────────────────────────┐  │
│                                                          │ PyGithub GitOps Engine   │  │
│                                                          │ (Opens GitHub PRs)       │  │
│                                                          └──────────────────────────┘  │
└───────────────────────────────────────────┬────────────────────────────────────────────┘
                                            │ Writes Audits
                                            ▼
                  ┌───────────────────────────────────────────────────┐
                  │           POSTGRESQL + SQLITE AUDIT STORE         │
                  │      (WAL Mode, Append-Only Compliance Log)       │
                  └───────────────────────────────────────────────────┘
```

---

## 2. Component Specifications

### 2.1 AWS Telemetry Ingestion Component (`services/aws_collector.py`)
- **Responsibility:** Assumes customer IAM Role, queries Cost Explorer for high-spend resources, queries CloudWatch for 90-day 99th percentile metrics.
- **Output:** Clean Python Dataclass `ResourceTelemetry`:
  ```python
  @dataclass
  class ResourceTelemetry:
      resource_id: str
      resource_type: str  # e.g., "aws_db_instance"
      current_instance_type: str  # e.g., "db.r5.2xlarge"
      monthly_cost_usd: float
      cpu_max_percent: float
      memory_min_free_mb: float
      io_read_iops_max: float
      io_write_iops_max: float
  ```

### 2.2 HCL Code Parser Component (`services/hcl_parser.py`)
- **Responsibility:** Connects to GitHub, reads `.tf` files, locates resource blocks, and modifies AST without breaking code style or comments.
- **Output:** Parsed dictionary and string mutation plan.

### 2.3 Multi-Agent Swarm (`agents/`)
- **FinOps Agent:** Calculates pricing options via AWS Pricing API. Returns `FinOpsProposal`.
- **Architecture Agent:** Validates proposal against `ResourceTelemetry`. Returns `ArchitectReview`.
- **Security Agent:** Validates compliance flags (`storage_encrypted = true`, required tags).

### 2.4 StateGuard Integration Layer (`governance/`)
Wraps the agent outputs in transaction memory and validates invariants:
```python
class CloudGuardGovernance:
    def __init__(self, state_dict):
        self.state = GuardedState(state_dict)
        self.registry = InvariantRegistry()
        self.detector = DriftDetector()
        self._register_rules()

    def _register_rules(self):
        @self.registry.invariant(name="ram_buffer_check", mode="block")
        def ram_check(s):
            return s["proposed_ram_gb"] >= (s["historical_peak_ram_gb"] * 1.20)

    def execute_safely(self, fn):
        with Saga(self.state) as tx:
            result = fn(self.state)
            self.registry.check(self.state)
            self.detector.check("estimated_cost_delta", self.state["cost_delta"])
            return result
```

### 2.5 PyGithub GitOps Engine (`services/gitops.py`)
- Creates branch `cloudguard/opt-<resource_id>-<date>`.
- Writes updated `.tf` content.
- Opens Pull Request with Markdown template containing:
  - Estimated Monthly Savings ($ and %)
  - CloudWatch Max Utilization Proof Table
  - StateGuard Invariant Execution Status Badge

---

## 3. Security & IAM Execution Model

```
CloudGuard Control Plane
  └─► boto3.sts.assume_role(
          RoleArn="arn:aws:iam::123456789012:role/CloudGuardReadOnlyRole",
          RoleSessionName="CloudGuardSession"
      )
  └─► Temporary Credentials (AccessKeyId, SecretAccessKey, SessionToken)
  └─► Restricted to Read-Only Calls Only!
```

---

## 4. Failure Recovery & Resiliency

- **AWS Throttling:** Handled by `botocore.config.Config(retries={'max_attempts': 10, 'mode': 'adaptive'})`.
- **GitHub Rate Limits:** Monitored via `x-ratelimit-remaining` headers; worker sleeps until reset time if limit < 100 requests.
- **State Failure:** StateGuard `Saga` handles transaction unwind, closing open PRs if downstream tasks fail.
