"""
CloudGuard FinOps End-to-End Execution Pipeline
Runs a complete governed optimization run for a production database.
"""
import logging
from src.services.aws_collector import AWSMetricsCollector
from src.services.hcl_parser import TerraformHCLParser
from src.agents.swarm_orchestrator import SwarmOrchestrator
from src.governance.engine import CloudGuardGovernanceEngine

# Configure clean logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("cloudguard.main")

SAMPLE_TERRAFORM_CODE = """
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


def run_pipeline():
    logger.info("=== Starting CloudGuard FinOps Governed Optimization Pipeline ===")

    # Step 1: Initialize Components
    collector = AWSMetricsCollector(use_mock=True)
    collector.initialize_session()
    
    parser = TerraformHCLParser()
    orchestrator = SwarmOrchestrator()
    engine = CloudGuardGovernanceEngine()

    # Step 2: Data Ingestion
    logger.info("Step 1: Fetching 90-day Telemetry from AWS CloudWatch...")
    telemetry = collector.fetch_resource_telemetry("production_db", "aws_db_instance")
    logger.info("Fetched Telemetry: Current Spec=%s, Monthly Cost=$%.2f, Peak CPU=%.1f%%, Free RAM=%.1f GB",
                telemetry.current_instance_type, telemetry.monthly_cost_usd, telemetry.cpu_max_percent, telemetry.memory_min_free_mb / 1024.0)

    logger.info("Step 2: Parsing Terraform HCL Code...")
    blocks = parser.parse_hcl_content("main.tf", SAMPLE_TERRAFORM_CODE)
    resource_block = blocks[0]
    logger.info("Parsed Resource Block: %s.%s", resource_block.resource_type, resource_block.resource_name)

    # Step 3: Governed Swarm Execution
    logger.info("Step 3: Executing Governed Multi-Agent Swarm with StateGuard Governance...")
    result_state = engine.execute_governed_swarm(
        telemetry=telemetry,
        resource_block=resource_block,
        swarm_func=orchestrator.run_consensus_debate,
        baseline_cost_deltas=[900.0, 920.0, 940.0, 960.0]
    )

    logger.info("Step 4: Swarm Governance Final Outcome:")
    logger.info("  - Status: %s", result_state["status"])
    logger.info("  - Original Spec: %s ($%.2f/mo)", result_state["current_spec"], result_state["original_monthly_cost"])
    logger.info("  - Agreed Spec:   %s ($%.2f/mo)", result_state["proposed_spec"], result_state["proposed_monthly_cost"])
    logger.info("  - Net Savings:   $%.2f / month", result_state["monthly_savings_usd"])

    # Step 4: Generate Mutated HCL Code
    if result_state["status"] == "committed" and result_state["monthly_savings_usd"] > 0:
        mutation = parser.mutate_instance_spec(
            file_path="main.tf",
            content=SAMPLE_TERRAFORM_CODE,
            resource_type=resource_block.resource_type,
            resource_name=resource_block.resource_name,
            attribute_name="instance_class",
            new_value=result_state["proposed_spec"]
        )
        logger.info("Step 5: Mutated HCL Code Generated Successfully:\n%s", mutation.updated_code)

    logger.info("=== CloudGuard FinOps Pipeline Execution Completed Successfully ===")


if __name__ == "__main__":
    run_pipeline()
