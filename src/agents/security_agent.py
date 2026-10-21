"""
Security & Compliance Agent (Hardened for Enterprise Audit)
Audits proposed Terraform configurations for SOC 2 tags, storage encryption, and security policies.
"""
import logging
from typing import Dict, Any, List

from src.models.telemetry import TerraformResourceBlock
from src.models.swarm import SecurityReview

logger = logging.getLogger("cloudguard.security_agent")

TRUTHY_VALUES = {True, "true", "True", "TRUE", "1", 1, "yes", "YES"}
FALSY_VALUES = {False, "false", "False", "FALSE", "0", 0, "no", "NO"}


class SecurityAgent:
    """
    Agent responsible for enforcing SOC 2 compliance and security rules on infrastructure code.
    """

    def audit_resource_block(self, block: TerraformResourceBlock) -> SecurityReview:
        """
        Audits a Terraform resource block for security attributes and compliance tags.
        """
        violations: List[str] = []
        attrs = block.current_attributes if isinstance(block.current_attributes, dict) else {}

        # Check 1: Encryption Flags
        encryption_valid = True
        if block.resource_type in ("aws_db_instance", "aws_ebs_volume", "aws_s3_bucket"):
            raw_encrypted = attrs.get("storage_encrypted", False)
            if raw_encrypted not in TRUTHY_VALUES:
                encryption_valid = False
                violations.append("Storage encryption ('storage_encrypted') is missing or disabled.")
        elif block.resource_type in ("aws_instance", "ec2"):
            root_device = attrs.get("root_block_device", {})
            root_encrypted = root_device.get("encrypted") if isinstance(root_device, dict) else None
            top_encrypted = attrs.get("storage_encrypted") or attrs.get("encrypted")
            if root_encrypted in FALSY_VALUES or top_encrypted in FALSY_VALUES:
                encryption_valid = False
                violations.append("EC2 EBS root volume encryption is explicitly disabled.")

        # Check 2: Public Exposure Prevention
        public_accessible = attrs.get("publicly_accessible", False)
        if public_accessible in TRUTHY_VALUES:
            violations.append("Resource is configured with 'publicly_accessible = true'.")

        # Check 3: Mandatory Compliance Tags
        tags_valid = True
        tags = attrs.get("tags", {})
        if isinstance(tags, dict):
            env_tag = tags.get("Environment") or tags.get("environment") or tags.get("ENV")
            if not env_tag:
                tags_valid = False
                violations.append("Missing mandatory compliance tag: 'Environment'.")
        else:
            tags_valid = False
            violations.append("Resource tags must be defined as a valid dictionary.")

        # Check 4: Automated Backup Retention & Deletion Protection (RDS)
        if block.resource_type == "aws_db_instance":
            if attrs.get("backup_retention_period") in (0, "0"):
                violations.append("Database automated backup retention ('backup_retention_period') is disabled (0 days).")
            is_prod = isinstance(tags, dict) and any(
                str(tags.get(k, "")).lower() == "production" for k in ("Environment", "environment", "ENV")
            )
            if is_prod and attrs.get("deletion_protection") in FALSY_VALUES:
                violations.append("Production database has 'deletion_protection = false'.")

        is_approved = (len(violations) == 0)
        rationale = (
            "Security Review Approved: All compliance tags and encryption rules satisfied."
            if is_approved
            else f"Security Review Failed: {'; '.join(violations)}"
        )

        return SecurityReview(
            is_approved=is_approved,
            violations=violations,
            compliance_tags_valid=tags_valid,
            encryption_valid=encryption_valid,
            rationale=rationale,
        )
