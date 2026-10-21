# 📄 Product Requirements Document (PRD)
## Project: CloudGuard FinOps (Powered by StateGuard)

---

## 1. Executive Summary & Market Demand Validation

### 1.1 Problem Statement
Modern engineering teams waste 20%–30% of their cloud budget on over-provisioned databases, idle compute instances, and unattached storage. While existing tools (e.g., AWS Cost Explorer, Vantage, Datadog) generate cost alerts, engineering teams suffer from **"The Action Gap"**—alerts are ignored because manually modifying Infrastructure as Code (Terraform) takes valuable dev hours away from feature development.

### 1.2 The Solution
**CloudGuard FinOps** is an autonomous multi-agent AI engine that connects to AWS via **Read-Only IAM**, analyzes utilization vs. spend, and automatically generates, tests, and opens **Terraform Pull Requests** on GitHub/GitLab to reclaim wasted spend.

### 1.3 Market Demand & Financial Feasibility (2026 Research)
- **Market Size:** The global Cloud FinOps market stands at **$16.57B+ in 2026** (CAGR 10.5%).
- **Shift to Remediation:** 2026 industry research highlights a massive market shift from passive *dashboard reporting* to *agentic remediation* (Shift-Left IaC Cost Governance).
- **Buyer Persona:** VPs of Engineering, CTOs, and DevOps Leads at growth-stage startups (Series A–C, $15k–$150k/mo AWS spend).
- **Willingness to Pay:** High ROI ($10k+/yr saved for $99–$299/mo license). Purchased via corporate credit cards without 6-month enterprise procurement cycles.

---

## 2. Product Goals & Objectives

1. **Zero-Trust Security:** Never request cloud write access. Operate 100% on Read-Only IAM roles and deliver recommendations as Git PRs.
2. **Zero-Risk Infrastructure Changes:** Use **StateGuard** determinism (Invariants, Drift Detection, and Sagas) to ensure AI agents never propose changes that crash production or violate CPU/Memory bounds.
3. **Immediate Developer Friction Reduction:** Reduce the time from "Cost Alert" to "Merged Fix" from 14 days to 30 seconds (one-click PR merge).

---

## 3. Core Feature Requirements

### F-101: 1-Click AWS Onboarding (Read-Only IAM)
- Provide an AWS CloudFormation template that provisions a cross-account IAM role restricted to `Get*`, `Describe*`, and `ce:*` permissions.
- Validate role ARN connectivity via Python `boto3.sts.get_caller_identity`.

### F-102: Infrastructure & Telemetry Ingestion Engine
- Parse GitHub/GitLab repository `.tf` files using AST/HCL parsers (`python-hcl2`).
- Query 90-day CloudWatch metrics (CPU, RAM, IOPS, Network) for every mapped AWS resource.
- Map billing line items from AWS Cost Explorer API (`ce:GetCostAndUsage`) to Terraform resource IDs.

### F-103: Multi-Agent Consensus Swarm
- **FinOps Agent:** Evaluates pricing catalogs to propose the lowest-cost instance tier (e.g., Graviton `t4g`/`r6g` migration).
- **Architecture Agent:** Analyzes 99th-percentile CloudWatch peak metrics to enforce safe performance headroom.
- **Security & Compliance Agent:** Verifies SOC 2 compliance tags, encryption flags, and public exposure risks.

### F-104: StateGuard Safety & Governance Core
- **Invariants:** Pre-commit assertions (`peak_cpu < 0.80`, `proposed_memory >= max_historical_memory`).
- **Drift Detection:** Z-Score monitoring on `estimated_cost_delta` to block statistical hallucinations.
- **Sagas:** LIFO compensation stack to close orphaned GitHub PRs if multi-file workflow fails mid-execution.

### F-105: Autonomous GitOps Engine
- Automatically create Git branches (`cloudguard/opt-<resource>-<id>`).
- Format HCL code modifications cleanly.
- Submit GitHub Pull Requests complete with markdown cost tables, CloudWatch graphs, and safety proofs.

---

## 4. User Personas & Key User Journeys

```
[CTO / VP Eng] ──► Installs AWS CloudFormation (2 mins) ──► Connects GitHub Repo
                                                                  │
                                                                  ▼
[CloudGuard Swarm] ◄── Analyzes AWS & HCL Code ◄── Runs Daily Scan
        │
        ▼ (Finds $1,200/mo waste)
StateGuard Validates Safety (Invariants & Drift Check)
        │
        ▼
Opens GitHub PR #84 ──► [Lead DevOps Engineer] Reviews Cost Diff ──► Clicks MERGE!
```

---

## 5. Non-Functional Requirements (NFRs)

- **Performance:** Complete full account scan & PR generation in < 120 seconds.
- **Security:** Zero storage of customer AWS secret keys; store only IAM Role ARNs and OAuth tokens encrypted at rest with AES-256-GCM.
- **Reliability:** 99.9% uptime for the SaaS control plane.
- **Auditability:** Append-only SQLite/Postgres audit trail of every LLM proposal, invariant evaluation, and Git action.

---

## 6. Success Metrics & KPIs

- **Primary Business KPI:** Total Annualized Dollars Saved for Customers (Target: $1,000,000+ in Year 1).
- **Product KPI:** PR Merge Rate (Target: > 75% of CloudGuard PRs merged by engineers).
- **Safety KPI:** Zero production outages caused by a CloudGuard PR (100% invariant enforcement).
