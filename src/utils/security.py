"""
Security Utility Module for CloudGuard FinOps
Provides IAM Role ARN validation, path traversal prevention, and input sanitization.
"""
import os
import re
from typing import Optional


# AWS IAM Role ARN Regex: arn:aws:iam::<12-digit-account-id>:role/<role-name-with-path>
IAM_ROLE_ARN_PATTERN = re.compile(
    r"^arn:aws[a-z-]*:iam::\d{12}:role/[a-zA-Z0-9+=,.@_-]+$"
)

# Safe resource identifier pattern (alphanumeric, hyphens, underscores, dots)
SAFE_RESOURCE_ID_PATTERN = re.compile(r"^[a-zA-Z0-9._-]+$")


def validate_iam_role_arn(role_arn: Optional[str]) -> bool:
    """
    Validates whether a string is a secure, well-formed AWS IAM Role ARN.
    """
    if not role_arn:
        return False
    return bool(IAM_ROLE_ARN_PATTERN.match(role_arn))


def sanitize_resource_id(resource_id: str) -> str:
    """
    Sanitizes resource identifiers to prevent metric query injection.
    """
    if not resource_id or not SAFE_RESOURCE_ID_PATTERN.match(resource_id):
        raise ValueError(
            f"Invalid or unsafe resource identifier: '{resource_id}'. Must be alphanumeric with . _ -"
        )
    return resource_id


def sanitize_file_path(file_path: str, base_dir: Optional[str] = None) -> str:
    """
    Prevents path traversal attacks by resolving paths and enforcing base directory confinement.
    """
    if not file_path:
        raise ValueError("File path cannot be empty")
        
    normalized = os.path.normpath(file_path)
    
    if ".." in normalized.split(os.sep):
        raise ValueError(f"Path traversal detected in path: '{file_path}'")
        
    if base_dir:
        abs_base = os.path.abspath(base_dir)
        abs_target = os.path.abspath(file_path if os.path.isabs(file_path) else os.path.join(abs_base, normalized))
        try:
            common = os.path.commonpath([abs_base, abs_target])
            if common != abs_base:
                raise ValueError(f"Path '{file_path}' escapes base directory '{base_dir}'")
        except ValueError:
            raise ValueError(f"Path '{file_path}' escapes base directory '{base_dir}'")
            
    return normalized
