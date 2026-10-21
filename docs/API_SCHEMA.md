# 🔌 API Specifications & Database Schema
## Project: CloudGuard FinOps Engine

---

## 1. REST API Specification (FastAPI Backend)

### 1.1 Authentication
All endpoints require a Bearer JWT Token passed in the `Authorization` header:
`Authorization: Bearer <jwt_token>`

---

### 1.2 Account Management Endpoints

#### `POST /api/v1/accounts`
Registers a new AWS account with its cross-account Read-Only IAM Role ARN.

**Request Payload:**
```json
{
  "account_name": "Production AWS Account",
  "aws_account_id": "123456789012",
  "role_arn": "arn:aws:iam::123456789012:role/CloudGuardReadOnlyRole",
  "external_id": "cg_ext_99f8a7d6c5b4"
}
```

**Response (201 Created):**
```json
{
  "account_id": "acc_77a1b2c3",
  "status": "connected",
  "validated_at": "2026-09-26T23:59:00Z"
}
```

---

### 1.3 Repository & Scan Endpoints

#### `POST /api/v1/repos/connect`
Connects a customer's GitHub repository.

**Request Payload:**
```json
{
  "account_id": "acc_77a1b2c3",
  "github_repo_url": "https://github.com/acme/infrastructure",
  "installation_id": 9876543
}
```

#### `POST /api/v1/scans/trigger`
Triggers an immediate scan & PR evaluation.

**Request Payload:**
```json
{
  "account_id": "acc_77a1b2c3",
  "dry_run": false
}
```

**Response (202 Accepted):**
```json
{
  "scan_job_id": "job_88d9e0f1",
  "status": "queued",
  "estimated_completion_seconds": 45
}
```

---

### 1.4 Pull Requests & Audit Endpoints

#### `GET /api/v1/pull-requests`
Returns all generated Pull Requests and their financial impact.

**Response (200 OK):**
```json
{
  "total_monthly_savings_usd": 1850.00,
  "pull_requests": [
    {
      "pr_id": "pr_101",
      "github_pr_url": "https://github.com/acme/infrastructure/pull/42",
      "resource_id": "aws_db_instance.main_db",
      "old_instance_type": "db.r5.2xlarge",
      "new_instance_type": "db.r6g.xlarge",
      "monthly_savings_usd": 950.00,
      "status": "open",
      "stateguard_status": "passed_all_invariants"
    }
  ]
}
```

---

## 2. Database Schema (PostgreSQL)

```sql
-- Customers Table
CREATE TABLE customers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    company_name VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- AWS Accounts Table
CREATE TABLE aws_accounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id UUID REFERENCES customers(id) ON DELETE CASCADE,
    aws_account_id VARCHAR(12) NOT NULL,
    role_arn VARCHAR(255) NOT NULL,
    external_id VARCHAR(255) NOT NULL,
    status VARCHAR(50) DEFAULT 'connected',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Repositories Table
CREATE TABLE repositories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    aws_account_id UUID REFERENCES aws_accounts(id) ON DELETE CASCADE,
    repo_full_name VARCHAR(255) NOT NULL, -- e.g. "acme/infra"
    github_installation_id BIGINT NOT NULL,
    default_branch VARCHAR(50) DEFAULT 'main',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Pull Request Logs Table
CREATE TABLE pull_request_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    repository_id UUID REFERENCES repositories(id) ON DELETE CASCADE,
    github_pr_number INT NOT NULL,
    github_pr_url VARCHAR(500) NOT NULL,
    resource_id VARCHAR(255) NOT NULL,
    old_spec VARCHAR(100) NOT NULL,
    new_spec VARCHAR(100) NOT NULL,
    monthly_savings_usd NUMERIC(10, 2) NOT NULL,
    status VARCHAR(50) DEFAULT 'open', -- 'open', 'merged', 'closed'
    stateguard_trace_id VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```

---

## 3. StateGuard SQLite Audit Log Schema (`stateguard_audit.db`)

Used by the CLI and developer dashboard to view execution traces:

```sql
CREATE TABLE audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trace_id TEXT NOT NULL,
    event_type TEXT NOT NULL, -- 'INVARIANT_PASS', 'INVARIANT_BLOCK', 'DRIFT_DETECTED', 'SAGA_COMPENSATE'
    rule_name TEXT,
    state_before TEXT, -- JSON string of state
    state_after TEXT,  -- JSON string of state
    execution_time_ms REAL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
);
```
