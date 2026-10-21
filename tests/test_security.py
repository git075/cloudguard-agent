"""
Security and Input Validation Unit Tests for CloudGuard FinOps
"""
import unittest
from src.utils.security import validate_iam_role_arn, sanitize_resource_id, sanitize_file_path
from src.models.telemetry import ResourceTelemetry
from src.services.aws_collector import AWSMetricsCollector


class TestSecurityAndValidation(unittest.TestCase):

    def test_valid_iam_role_arns(self):
        valid_arn = "arn:aws:iam::123456789012:role/CloudGuardReadOnlyRole"
        self.assertTrue(validate_iam_role_arn(valid_arn))

        valid_govcloud_arn = "arn:aws-us-gov:iam::987654321098:role/Security-Role_v1"
        self.assertTrue(validate_iam_role_arn(valid_govcloud_arn))

    def test_invalid_iam_role_arns(self):
        invalid_arns = [
            "arn:aws:s3:::my-bucket",                       # Wrong service
            "arn:aws:iam::12345:role/ShortAccountId",       # Invalid account ID length
            "arn:aws:iam::123456789012:user/Bob",          # User instead of Role
            "'; DROP TABLE users; --",                     # SQL Injection attempt
            "https://malicious-site.com",                   # URL injection
            "", None
        ]
        for arn in invalid_arns:
            self.assertFalse(validate_iam_role_arn(arn))

    def test_aws_collector_rejects_invalid_arn(self):
        with self.assertRaises(ValueError):
            AWSMetricsCollector(role_arn="invalid-role-arn", use_mock=True)

    def test_sanitize_resource_id(self):
        self.assertEqual(sanitize_resource_id("main_db"), "main_db")
        self.assertEqual(sanitize_resource_id("app-server-101.v2"), "app-server-101.v2")

        invalid_ids = [
            "main_db; rm -rf /",
            "db_id<script>",
            "../etc/passwd"
        ]
        for bad_id in invalid_ids:
            with self.assertRaises(ValueError):
                sanitize_resource_id(bad_id)

    def test_path_traversal_prevention(self):
        self.assertEqual(sanitize_file_path("terraform/main.tf"), "terraform/main.tf")

        with self.assertRaises(ValueError):
            sanitize_file_path("../../etc/passwd")

        with self.assertRaises(ValueError):
            sanitize_file_path("/etc/passwd", base_dir="/tmp/app")

    def test_telemetry_boundary_validation(self):
        # Valid telemetry
        t = ResourceTelemetry(
            resource_id="db_1",
            resource_type="aws_db_instance",
            current_instance_type="db.r5.2xlarge",
            monthly_cost_usd=100.0,
            cpu_max_percent=50.0
        )
        self.assertEqual(t.monthly_cost_usd, 100.0)

        # Invalid negative cost
        with self.assertRaises(ValueError):
            ResourceTelemetry(
                resource_id="db_1",
                resource_type="aws_db_instance",
                current_instance_type="db.r5.2xlarge",
                monthly_cost_usd=-50.0
            )

        # Invalid CPU > 100%
        with self.assertRaises(ValueError):
            ResourceTelemetry(
                resource_id="db_1",
                resource_type="aws_db_instance",
                current_instance_type="db.r5.2xlarge",
                monthly_cost_usd=100.0,
                cpu_max_percent=150.0
            )


    def test_path_prefix_bypass_prevention(self):
        # Prefix bypass attack: /tmp/app vs /tmp/application_evil/secret.txt
        with self.assertRaises(ValueError):
            sanitize_file_path("/tmp/application_evil/secret.txt", base_dir="/tmp/app")

    def test_empty_inputs(self):
        with self.assertRaises(ValueError):
            sanitize_resource_id("")
        with self.assertRaises(ValueError):
            sanitize_file_path("")


if __name__ == "__main__":
    unittest.main()
