"""
Unit Tests for AWS Metrics Collector Service
"""
import unittest
from src.services.aws_collector import AWSMetricsCollector


class TestAWSMetricsCollector(unittest.TestCase):

    def test_mock_rds_telemetry(self):
        collector = AWSMetricsCollector(use_mock=True)
        collector.initialize_session()
        
        telemetry = collector.fetch_resource_telemetry("main_db", "aws_db_instance")
        
        self.assertEqual(telemetry.resource_id, "main_db")
        self.assertEqual(telemetry.resource_type, "aws_db_instance")
        self.assertEqual(telemetry.current_instance_type, "db.r5.2xlarge")
        self.assertEqual(telemetry.monthly_cost_usd, 1400.00)
        self.assertEqual(telemetry.cpu_max_percent, 42.5)
        self.assertEqual(telemetry.memory_min_free_mb, 44032.0)

    def test_mock_ec2_telemetry(self):
        collector = AWSMetricsCollector(use_mock=True)
        collector.initialize_session()
        
        telemetry = collector.fetch_resource_telemetry("app_server", "aws_instance")
        
        self.assertEqual(telemetry.resource_id, "app_server")
        self.assertEqual(telemetry.resource_type, "aws_instance")
        self.assertEqual(telemetry.current_instance_type, "m5.xlarge")
        self.assertEqual(telemetry.monthly_cost_usd, 280.00)
        self.assertEqual(telemetry.cpu_max_percent, 18.0)


if __name__ == "__main__":
    unittest.main()
