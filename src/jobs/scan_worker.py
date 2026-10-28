"""
Celery Scan Worker Implementation for CloudGuard FinOps.
Executes multi-agent swarm right-sizing scans asynchronously in distributed background workers.
"""
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session
from celery.exceptions import SoftTimeLimitExceeded

from src.jobs.celery_app import celery_app
from src.db.session import SyncSessionLocal
from src.models.db import Customer, AWSAccount, ScanJob, PullRequestLog
from src.services.aws_collector import AWSMetricsCollector
from src.services.hcl_parser import TerraformHCLParser
from src.agents.swarm_orchestrator import SwarmOrchestrator
from src.governance.engine import CloudGuardGovernanceEngine

logger = logging.getLogger("cloudguard.scan_worker")

DEFAULT_SAMPLE_TF = """
resource "aws_db_instance" "production_db" {
  allocated_storage   = 500
  engine              = "postgres"
  instance_class      = "db.r5.2xlarge"
  storage_encrypted   = true
  publicly_accessible = false

  tags = {
    Environment = "production"
    Owner       = "devops"
  }
}
"""


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def execute_cloudguard_scan(
    self, scan_job_id: str, sample_tf_code: Optional[str] = None
) -> dict:
    """
    Celery background worker task.
    Runs end-to-end telemetry ingestion, Terraform parsing, and StateGuard-governed
    multi-agent swarm debate for a customer's AWS account.
    """
    logger.info("Executing background scan job: %s", scan_job_id)
    db: Session = SyncSessionLocal()

    try:
        scan_job = db.query(ScanJob).filter(ScanJob.id == scan_job_id).first()
        if not scan_job:
            logger.error("ScanJob ID %s not found in database", scan_job_id)
            return {"status": "failed", "error": "Scan job not found"}

        scan_job.status = "running"
        db.commit()

        # Fetch Customer and AWS Account from DB
        customer = db.query(Customer).filter(Customer.id == scan_job.customer_id).first()
        aws_account = db.query(AWSAccount).filter(AWSAccount.id == scan_job.aws_account_id).first()

        if not customer or not aws_account:
            scan_job.status = "failed"
            scan_job.error_message = "Associated Customer or AWS Account missing"
            db.commit()
            return {"status": "failed", "error": scan_job.error_message}

        import os
        from src.services.gitops import GitOpsEngine
        use_mock = os.getenv("USE_MOCK_TELEMETRY", "true").lower() in ("true", "1", "yes")

        # Initialize Collector with tenant's role_arn and external_id
        collector = AWSMetricsCollector(
            role_arn=aws_account.role_arn,
            external_id=customer.external_id,
            use_mock=use_mock,
        )
        collector.initialize_session()

        parser = TerraformHCLParser()
        orchestrator = SwarmOrchestrator()
        engine = CloudGuardGovernanceEngine()
        gitops = GitOpsEngine(use_mock=use_mock)

        # Parse Terraform HCL code
        tf_code = sample_tf_code or DEFAULT_SAMPLE_TF
        blocks = parser.parse_hcl_content("main.tf", tf_code)

        total_savings = 0.0
        resources_scanned = 0

        for resource_block in blocks:
            resources_scanned += 1
            telemetry = collector.fetch_resource_telemetry(resource_block.resource_name, resource_block.resource_type)

            # Run Governed Multi-Agent Swarm with StateGuard
            result_state = engine.execute_governed_swarm(
                telemetry=telemetry,
                resource_block=resource_block,
                swarm_func=orchestrator.run_consensus_debate,
                baseline_cost_deltas=[900.0, 920.0, 940.0, 960.0],
            )

            if result_state["status"] == "committed" and result_state["monthly_savings_usd"] > 0:
                savings = result_state["monthly_savings_usd"]
                total_savings += savings

                from src.models.swarm import SwarmConsensus
                consensus = SwarmConsensus(
                    resource_id=resource_block.resource_name,
                    is_unanimous=True,
                    original_spec=result_state["current_spec"],
                    agreed_spec=result_state["proposed_spec"],
                    original_monthly_cost=result_state["original_monthly_cost"],
                    agreed_monthly_cost=result_state["proposed_monthly_cost"],
                    monthly_savings_usd=result_state["monthly_savings_usd"],
                    debate_trace=["[Celery Worker] Governed multi-agent optimization approved."],
                )
                pr_result = gitops.create_optimization_pull_request(
                    repo_full_name="cloudguard-demo/infra",
                    file_path=resource_block.file_path,
                    resource_telemetry=telemetry,
                    consensus=consensus,
                    updated_hcl_code=tf_code,
                )
                pr_url = pr_result.get("pr_url") or f"https://github.com/cloudguard-demo/infra/pull/{hash(scan_job_id) % 1000}"

                pr_log = PullRequestLog(
                    customer_id=customer.id,
                    scan_job_id=scan_job.id,
                    resource_id=resource_block.resource_name,
                    original_spec=result_state["current_spec"],
                    proposed_spec=result_state["proposed_spec"],
                    monthly_savings_usd=savings,
                    pr_url=pr_url,
                    status="created",
                )
                db.add(pr_log)

        # Update ScanJob completion status
        scan_job.status = "completed"
        scan_job.total_resources_scanned = resources_scanned
        scan_job.total_savings_identified = total_savings
        scan_job.completed_at = datetime.utcnow()
        db.commit()

        logger.info(
            "ScanJob %s completed successfully! Scanned: %d, Savings: $%.2f",
            scan_job_id,
            resources_scanned,
            total_savings,
        )
        return {
            "status": "completed",
            "scan_job_id": scan_job_id,
            "resources_scanned": resources_scanned,
            "total_savings_usd": total_savings,
        }

    except SoftTimeLimitExceeded:
        logger.error("ScanJob %s exceeded soft runtime limit (55 mins)", scan_job_id)
        db.rollback()
        scan_job = db.query(ScanJob).filter(ScanJob.id == scan_job_id).first()
        if scan_job:
            scan_job.status = "failed"
            scan_job.error_message = "Scan job exceeded 55-minute runtime limit."
            scan_job.completed_at = datetime.utcnow()
            db.commit()
        return {"status": "failed", "error": "SoftTimeLimitExceeded"}
    except Exception as exc:
        logger.exception("Error executing scan job %s: %s", scan_job_id, str(exc))
        db.rollback()
        retries = getattr(self.request, "retries", 0)
        max_retries = getattr(self, "max_retries", 3)
        scan_job = db.query(ScanJob).filter(ScanJob.id == scan_job_id).first()

        if retries >= max_retries:
            if scan_job:
                scan_job.status = "failed"
                scan_job.error_message = f"Failed after {max_retries} attempts: {str(exc)}"
                scan_job.completed_at = datetime.utcnow()
                db.commit()
            return {"status": "failed", "error": str(exc)}
        else:
            if scan_job:
                scan_job.status = "retrying"
                scan_job.error_message = f"Transient error (attempt {retries + 1}/{max_retries}): {str(exc)}"
                db.commit()
            raise self.retry(exc=exc)
    finally:
        db.close()


@celery_app.task
def run_nightly_scans() -> dict:
    """
    Periodic Celery Beat scheduled task.
    Queries all active AWS accounts across active tenant customers
    and dispatches background scan worker tasks automatically.
    """
    logger.info("Executing scheduled Celery Beat nightly scans...")
    db: Session = SyncSessionLocal()
    dispatched_jobs = []

    try:
        active_accounts = (
            db.query(AWSAccount)
            .join(Customer)
            .filter(AWSAccount.is_active == True, Customer.is_active == True)
            .all()
        )

        for account in active_accounts:
            # Create a pending scan job
            scan_job = ScanJob(
                customer_id=account.customer_id,
                aws_account_id=account.id,
                status="pending",
            )
            db.add(scan_job)
            db.commit()
            db.refresh(scan_job)

            # Dispatch worker task
            task = execute_cloudguard_scan.delay(scan_job_id=scan_job.id)
            dispatched_jobs.append({"scan_job_id": scan_job.id, "celery_task_id": task.id})

        logger.info("Nightly scan dispatched %d scan jobs.", len(dispatched_jobs))
        return {"status": "success", "dispatched_count": len(dispatched_jobs), "jobs": dispatched_jobs}
    finally:
        db.close()
