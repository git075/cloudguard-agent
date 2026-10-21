"""
LocalStack & AWS Integration Tests for CloudGuard FinOps Engine
Validates IAM ARN validation, LocalStack endpoint simulation, and StateGuard governance execution.
"""
import unittest
from unittest.mock import MagicMock, patch

from src.services.aws_collector import AWSMetricsCollector
from src.agents.swarm_orchestrator import SwarmOrchestrator
from src.governance.engine import CloudGuardGovernanceEngine
from src.governance.proxy import GuardedState
from src.models.telemetry import TerraformResourceBlock


class TestLocalStackIntegration(unittest.TestCase):

    def test_iam_role_arn_validation_and_rejection(self):
        """Verify strict security rules reject malformed or dangerous IAM role ARNs."""
        with self.assertRaises(ValueError):
            AWSMetricsCollector(role_arn="arn:aws:iam::123456789012:role/AdminRole; rm -rf /")

    def test_mock_localstack_session_initialization(self):
        """Simulate LocalStack endpoint initialization and sts:AssumeRole."""
        collector = AWSMetricsCollector(
            role_arn="arn:aws:iam::123456789012:role/CloudGuardReadOnly",
            region_name="us-east-1",
            use_mock=False,
        )

        mock_sts = MagicMock()
        mock_sts.assume_role.return_value = {
            "Credentials": {
                "AccessKeyId": "ASIA_LOCALSTACK_KEY",
                "SecretAccessKey": "SECRET_LOCALSTACK_KEY",
                "SessionToken": "TOKEN_LOCALSTACK",
                "Expiration": "2026-10-05T00:00:00Z",  # Phase 1: Expiration field added
            }
        }

        mock_session_obj = MagicMock()
        mock_boto3 = MagicMock()
        mock_boto3.client.return_value = mock_sts
        mock_boto3.Session.return_value = mock_session_obj

        with patch.dict("sys.modules", {"boto3": mock_boto3}):
            collector.initialize_session()
            # Phase 1: AssumeRole is called without ExternalId when external_id=None
            mock_sts.assume_role.assert_called_once_with(
                RoleArn="arn:aws:iam::123456789012:role/CloudGuardReadOnly",
                RoleSessionName="CloudGuardSession",
            )
            self.assertEqual(collector._session, mock_session_obj)

    def test_localstack_live_telemetry_fetch(self):
        """Simulate CloudWatch metric response via boto3 inside LocalStack environment."""
        collector = AWSMetricsCollector(
            role_arn="arn:aws:iam::123456789012:role/CloudGuardReadOnly",
            use_mock=False,
        )

        mock_rds = MagicMock()
        mock_rds.describe_db_instances.return_value = {
            "DBInstances": [{"DBInstanceClass": "db.r5.2xlarge", "DBInstanceStatus": "available"}]
        }

        mock_ce = MagicMock()
        mock_ce.get_cost_and_usage.return_value = {"ResultsByTime": []}

        # Phase 1: CloudWatch mock now needs Id field in MetricDataResults
        mock_cw = MagicMock()
        mock_cw.get_metric_data.return_value = {
            "MetricDataResults": [
                {"Id": "cpu_max",           "Values": [42.5]},
                {"Id": "cpu_avg",           "Values": [8.2]},
                {"Id": "mem_min_free_bytes","Values": [44032.0 * 1024.0 * 1024.0]},
                {"Id": "read_iops_max",     "Values": [1250.0]},
                {"Id": "write_iops_max",    "Values": [890.0]},
                {"Id": "db_connections_max","Values": [124.0]},
            ]
        }

        def mock_client_factory(service, **kwargs):
            if service == "cloudwatch": return mock_cw
            if service == "rds":        return mock_rds
            if service == "ce":         return mock_ce
            return MagicMock()

        mock_session = MagicMock()
        mock_session.client.side_effect = mock_client_factory
        collector._session = mock_session

        telemetry = collector.fetch_resource_telemetry("production_db", "aws_db_instance")
        self.assertEqual(telemetry.resource_id, "production_db")
        self.assertEqual(telemetry.cpu_max_percent, 42.5)
        self.assertAlmostEqual(telemetry.io_read_iops_max, 1250.0, delta=1.0)

    def test_full_governed_swarm_pipeline_with_localstack(self):
        """Verify full end-to-end optimization pipeline using LocalStack telemetry under StateGuard governance."""
        collector = AWSMetricsCollector(use_mock=True)
        collector.initialize_session()
        telemetry = collector.fetch_resource_telemetry("production_db", "aws_db_instance")

        resource_block = TerraformResourceBlock(
            file_path="main.tf",
            resource_type="aws_db_instance",
            resource_name="production_db",
            current_attributes={
                "allocated_storage": 500,
                "engine": "postgres",
                "instance_class": "db.r5.2xlarge",
                "storage_encrypted": True,
                "publicly_accessible": False,
                "tags": {"Environment": "production", "Owner": "devops"},
            },
        )

        orchestrator = SwarmOrchestrator()
        engine = CloudGuardGovernanceEngine()

        result_state = engine.execute_governed_swarm(
            telemetry=telemetry,
            resource_block=resource_block,
            swarm_func=orchestrator.run_consensus_debate,
        )

        self.assertEqual(result_state["status"], "committed")
        self.assertEqual(result_state["proposed_spec"], "db.r6g.xlarge")
        self.assertEqual(result_state["monthly_savings_usd"], 1104.0)  # Phase 1+2: $1400 - $296



if __name__ == "__main__":
    unittest.main()
