"""
FastAPI Scan Router Endpoints for CloudGuard FinOps.
Dispatches asynchronous Celery scan jobs and queries job status/audit logs.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.api.dependencies import get_current_customer, get_optional_customer
from src.db.session import get_async_db
from src.models.db import AWSAccount, Customer, PullRequestLog, ScanJob
from src.jobs.scan_worker import execute_cloudguard_scan
from src.services.aws_collector import AWSMetricsCollector
from src.services.hcl_parser import TerraformHCLParser
from src.agents.swarm_orchestrator import SwarmOrchestrator
from src.governance.engine import CloudGuardGovernanceEngine

router = APIRouter(prefix="/api/v1/scans", tags=["Scan Jobs"])


# Pydantic Request & Response Schemas
class TriggerScanRequest(BaseModel):
    aws_account_id: Optional[str] = Field(
        None, json_schema_extra={"example": "aws-acc-uuid-12345"}
    )
    terraform_code: Optional[str] = Field(
        None, json_schema_extra={"example": 'resource "aws_db_instance" "prod" {...}'}
    )


class TriggerScanResponse(BaseModel):
    scan_job_id: str
    celery_task_id: str
    status: str
    message: str


class PullRequestLogResponse(BaseModel):
    id: str
    resource_id: str
    original_spec: str
    proposed_spec: str
    monthly_savings_usd: float
    pr_url: Optional[str]
    status: str


class ScanJobDetailResponse(BaseModel):
    id: str
    customer_id: str
    aws_account_id: str
    status: str
    total_resources_scanned: int
    total_savings_identified: float
    error_message: Optional[str]
    created_at: str
    completed_at: Optional[str]
    pull_request_logs: List[PullRequestLogResponse] = []


@router.post(
    "/trigger",
    response_model=TriggerScanResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def trigger_scan_job(
    req: Optional[TriggerScanRequest] = None,
    current_customer: Optional[Customer] = Depends(get_optional_customer),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Triggers an asynchronous multi-agent right-sizing scan for a customer's AWS Account.
    Dispatches a Celery task in the background and returns HTTP 202 Accepted immediately.
    Falls back to immediate governed execution in demo mode if unauthenticated.
    """
    if current_customer:
        account_id_filter = req.aws_account_id if (req and req.aws_account_id) else None
        if account_id_filter:
            stmt = select(AWSAccount).where(
                AWSAccount.id == account_id_filter,
                AWSAccount.customer_id == current_customer.id,
            )
            result = await db.execute(stmt)
            aws_account = result.scalar_one_or_none()
            if not aws_account:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"AWS Account ID '{account_id_filter}' not found for this customer tenant",
                )
        else:
            stmt = select(AWSAccount).where(AWSAccount.customer_id == current_customer.id)
            result = await db.execute(stmt)
            aws_account = result.scalars().first()
            if not aws_account:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="No active AWS accounts found for this customer tenant",
                )

        # Create pending ScanJob record in DB
        scan_job = ScanJob(
            customer_id=current_customer.id,
            aws_account_id=aws_account.id,
            status="pending",
        )
        db.add(scan_job)
        await db.commit()
        await db.refresh(scan_job)

        tf_code = req.terraform_code if req else None
        try:
            task = execute_cloudguard_scan.delay(
                scan_job_id=scan_job.id, sample_tf_code=tf_code
            )
            celery_task_id = task.id
        except Exception as e:
            scan_job.status = "failed"
            scan_job.error_message = f"Background task queue broker unavailable: {str(e)}"
            await db.commit()
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Background task queue service is currently unavailable. Please retry later.",
            )

        return TriggerScanResponse(
            scan_job_id=scan_job.id,
            celery_task_id=celery_task_id,
            status="pending",
            message="Scan job successfully queued for background execution",
        )

    # Demo / Unauthenticated UI Execution
    collector = AWSMetricsCollector(use_mock=True)
    collector.initialize_session()
    parser = TerraformHCLParser()
    orchestrator = SwarmOrchestrator()
    engine = CloudGuardGovernanceEngine()

    telemetry = collector.fetch_resource_telemetry("production_db", "aws_db_instance")
    sample_hcl = (req.terraform_code if req else None) or 'resource "aws_db_instance" "production_db" { instance_class = "db.r5.2xlarge" storage_encrypted = true publicly_accessible = false tags = { Environment = "production" } }'
    blocks = parser.parse_hcl_content("main.tf", sample_hcl)

    result_state = engine.execute_governed_swarm(
        telemetry=telemetry,
        resource_block=blocks[0],
        swarm_func=orchestrator.run_consensus_debate,
        baseline_cost_deltas=[900.0, 920.0, 940.0, 960.0]
    )

    return TriggerScanResponse(
        scan_job_id="demo-scan-job",
        celery_task_id="demo-sync-task",
        status=result_state.get("status", "completed"),
        message=f"Demo governed scan completed. Spec: {result_state.get('proposed_spec')}, Savings: ${result_state.get('monthly_savings_usd', 0.0):.2f}/mo",
    )


@router.get("/{scan_job_id}", response_model=ScanJobDetailResponse)
async def get_scan_job_status(
    scan_job_id: str,
    current_customer: Customer = Depends(get_current_customer),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Retrieves execution status, metrics, and GitOps PR logs for a specific scan job.
    Enforces strict tenant ownership isolation.
    """
    stmt = (
        select(ScanJob)
        .options(selectinload(ScanJob.pull_request_logs))
        .where(
            ScanJob.id == scan_job_id,
            ScanJob.customer_id == current_customer.id,
        )
    )
    result = await db.execute(stmt)
    scan_job = result.scalar_one_or_none()

    if not scan_job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scan job '{scan_job_id}' not found for this customer tenant",
        )

    pr_logs = [
        PullRequestLogResponse(
            id=log.id,
            resource_id=log.resource_id,
            original_spec=log.original_spec,
            proposed_spec=log.proposed_spec,
            monthly_savings_usd=log.monthly_savings_usd,
            pr_url=log.pr_url,
            status=log.status,
        )
        for log in scan_job.pull_request_logs
    ]

    return ScanJobDetailResponse(
        id=scan_job.id,
        customer_id=scan_job.customer_id,
        aws_account_id=scan_job.aws_account_id,
        status=scan_job.status,
        total_resources_scanned=scan_job.total_resources_scanned,
        total_savings_identified=scan_job.total_savings_identified,
        error_message=scan_job.error_message,
        created_at=scan_job.created_at.isoformat() if scan_job.created_at else "",
        completed_at=scan_job.completed_at.isoformat() if scan_job.completed_at else None,
        pull_request_logs=pr_logs,
    )
