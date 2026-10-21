"""
Telemetry and Resource Models for CloudGuard FinOps
Includes runtime data validation and boundary safety checks.

PRODUCTION EXPANSION (Phase 1):
  Added IOPS, network bandwidth, database connections, and storage fields
  needed for production-accurate instance right-sizing decisions.
"""
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional


@dataclass
class ResourceTelemetry:
    """
    Holds 90-day historical performance metrics and spend for an AWS Resource.

    Fields added in Phase 1 production expansion:
    - io_read_iops_max / io_write_iops_max: Peak disk I/O throughput (RDS: IOPS)
    - network_in_mb_max / network_out_mb_max: Peak network traffic (EC2)
    - db_connections_max: Maximum simultaneous DB client connections (RDS)
    - storage_gb: Total allocated storage size in GB
    """
    resource_id: str
    resource_type: str              # e.g., 'aws_db_instance' or 'aws_instance'
    current_instance_type: str      # e.g., 'db.r5.2xlarge'
    monthly_cost_usd: float

    # CloudWatch 90-day CPU telemetry
    cpu_max_percent: float = 0.0
    cpu_avg_percent: float = 0.0

    # CloudWatch 90-day Memory telemetry
    # NOTE: RDS reports FreeableMemory (bytes). We store as MB for calculations.
    memory_min_free_mb: float = 0.0
    total_memory_mb: float = 0.0

    # Phase 1 Production: Disk I/O telemetry (RDS ReadIOPS / WriteIOPS)
    io_read_iops_max: float = 0.0
    io_write_iops_max: float = 0.0

    # Phase 1 Production: Network throughput telemetry (EC2 NetworkIn/Out in MB/s)
    network_in_mb_max: float = 0.0
    network_out_mb_max: float = 0.0

    # Phase 1 Production: RDS-specific — peak simultaneous database connections
    # Critical for sizing: t4g.large supports ~150 max connections; r6g.xlarge ~650
    db_connections_max: int = 0

    # Phase 1 Production: Storage size (needed for RDS IOPS provisioning decisions)
    storage_gb: float = 0.0

    # AWS Region where the resource lives (needed for region-accurate pricing)
    aws_region: str = "us-east-1"

    # Database engine and deployment topology
    engine: Optional[str] = None          # e.g. 'postgres', 'mysql', 'oracle-ee', 'sqlserver-se'
    multi_az: bool = False                # True if RDS Multi-AZ deployed (doubles instance cost)

    # Metadata & Tags
    tags: Dict[str, str] = field(default_factory=dict)


    def __post_init__(self):
        """
        Validates boundaries to ensure safe telemetry data.
        All boundary checks run before the object is used by any agent.
        """
        if self.monthly_cost_usd < 0:
            raise ValueError(f"Monthly cost cannot be negative: {self.monthly_cost_usd}")
        if not (0.0 <= self.cpu_max_percent <= 100.0):
            raise ValueError(f"CPU max percent must be between 0.0 and 100.0, got: {self.cpu_max_percent}")
        if self.memory_min_free_mb < 0:
            raise ValueError(f"Memory min free cannot be negative: {self.memory_min_free_mb}")
        if self.io_read_iops_max < 0 or self.io_write_iops_max < 0:
            raise ValueError("IOPS values cannot be negative")
        if self.db_connections_max < 0:
            raise ValueError(f"DB connections cannot be negative: {self.db_connections_max}")

    @property
    def peak_memory_used_gb(self) -> float:
        """
        Calculates historical peak memory used in GB from 90-day CloudWatch telemetry.

        Formula:  peak_used = total_memory - minimum_free_memory_ever_observed
        The minimum freeable memory over 90 days = the moment of highest memory pressure.
        """
        if self.total_memory_mb <= 0:
            return 0.0
        used_mb = max(0.0, self.total_memory_mb - self.memory_min_free_mb)
        return used_mb / 1024.0

    @property
    def peak_iops(self) -> float:
        """Total peak IOPS (read + write combined) — used to validate storage type requirements."""
        return self.io_read_iops_max + self.io_write_iops_max

    @property
    def is_io_intensive(self) -> bool:
        """
        Returns True if the resource's I/O profile requires provisioned IOPS storage
        rather than general-purpose gp3 storage.
        Threshold: > 3000 IOPS combined peak (gp3 baseline without provisioning).
        """
        return self.peak_iops > 3000.0


@dataclass
class TerraformResourceBlock:
    """
    Represents a parsed resource block from a Terraform .tf file.
    """
    file_path: str
    resource_type: str          # e.g. 'aws_db_instance'
    resource_name: str          # e.g. 'main_db'
    current_attributes: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.file_path or not self.resource_type or not self.resource_name:
            raise ValueError("File path, resource type, and resource name are required")


@dataclass
class HCLMutationResult:
    """
    Result of mutating an HCL file.
    """
    file_path: str
    original_code: str
    updated_code: str
    old_value: str
    new_value: str
    target_attribute: str

    def __post_init__(self):
        if not self.new_value:
            raise ValueError("Replacement spec new_value cannot be empty")
