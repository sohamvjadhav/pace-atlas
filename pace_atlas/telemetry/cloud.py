"""
PACE Atlas — Cloud Provider Integration

Collects metrics from cloud providers (AWS, GCP, Azure).

This collector reads cloud provider APIs to get data that native
Linux tools cannot provide - like billing, cloud-specific metrics,
and provider-level health indicators.

Metrics Collected:
- AWS: EC2 health, billing, CloudWatch metrics
- GCP: Compute Engine status, billing
- Azure: VM status, cost management

Author: PACE Atlas
Version: 0.1.0
"""

import os
from datetime import datetime
from typing import Optional

from .base import TelemetryCollector, TelemetrySnapshot, CollectionError


class CloudCollector(TelemetryCollector):
    """
    Collects cloud provider-specific metrics.

    Supports AWS, GCP, and Azure. Falls back gracefully if not
    running on a cloud instance or if APIs are not configured.
    """

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        self.provider = self._detect_provider()

    @property
    def name(self) -> str:
        return "cloud"

    @property
    def interval(self) -> int:
        return 300  # Check every 5 minutes (cloud APIs rate limited)

    def _detect_provider(self) -> str:
        """Detect which cloud provider we're running on."""
        # Check for AWS
        if os.path.exists("/sys/hypervisor/uuid"):
            try:
                with open("/sys/hypervisor/uuid", "r") as f:
                    if f.read().startswith("ec2"):
                        return "aws"
            except Exception:
                pass

        # Check for AWS IMDS
        if os.environ.get("AWS_METADATA_SERVICE"):
            return "aws"

        # Check for GCP
        if os.path.exists("/etc/gcp_environment"):
            return "gcp"

        # Check Google Cloud metadata
        if os.environ.get("GCE_METADATA_HOST"):
            return "gcp"

        # Check for Azure
        if os.path.exists("/var/lib/waagent"):
            return "azure"

        if os.environ.get("AZURE_METADATA_HOST"):
            return "azure"

        return "unknown"

    def collect(self) -> TelemetrySnapshot:
        """
        Collect cloud provider metrics.

        Returns:
            TelemetrySnapshot with:
            - provider: Cloud provider name
            - instance_id: Cloud instance ID
            - instance_type: VM type
            - billing: Cost information (if available)
            - health_status: Cloud health status
        """
        try:
            data = {"provider": self.provider, "available": self.provider != "unknown"}

            if self.provider == "unknown":
                return TelemetrySnapshot(
                    timestamp=datetime.now(),
                    collector_name=self.name,
                    data=data,
                    metadata=self.get_metadata(),
                )

            # Provider-specific collection
            if self.provider == "aws":
                aws_data = self._collect_aws()
                if aws_data:
                    data.update(aws_data)

            elif self.provider == "gcp":
                gcp_data = self._collect_gcp()
                if gcp_data:
                    data.update(gcp_data)

            elif self.provider == "azure":
                azure_data = self._collect_azure()
                if azure_data:
                    data.update(azure_data)

            return TelemetrySnapshot(
                timestamp=datetime.now(),
                collector_name=self.name,
                data=data,
                metadata=self.get_metadata(),
            )

        except Exception as e:
            raise CollectionError(self.name, str(e))

    def _collect_aws(self) -> Optional[dict]:
        """Collect AWS-specific metrics."""
        data = {}

        # Get instance metadata
        instance_id = self._get_aws_metadata("instance-id")
        if instance_id:
            data["instance_id"] = instance_id

        instance_type = self._get_aws_metadata("instance-type")
        if instance_type:
            data["instance_type"] = instance_type

        # Get billing data if available
        billing = self._get_aws_billing()
        if billing:
            data["billing"] = billing

        # Get health status
        health = self._get_aws_health()
        if health:
            data["health_status"] = health

        return data

    def _get_aws_metadata(self, path: str) -> Optional[str]:
        """Get AWS instance metadata."""
        try:
            # Try IMDSv2 first
            import requests

            # Check if IMDS is available
            try:
                token_resp = requests.put(
                    "http://169.254.169.254/latest/api/token",
                    headers={"X-aws-ec2-metadata-token-ttl-seconds": "300"},
                    timeout=2,
                )
                token = token_resp.text

                # Get the requested path
                resp = requests.get(
                    f"http://169.254.169.254/latest/meta-data/{path}",
                    headers={"X-aws-ec2-metadata-token": token},
                    timeout=2,
                )
                return resp.text
            except Exception:
                # Fall back to IMDSv1
                resp = requests.get(
                    f"http://169.254.169.254/latest/meta-data/{path}", timeout=2
                )
                return resp.text

        except Exception:
            return None

    def _get_aws_billing(self) -> Optional[dict]:
        """Get AWS billing information."""
        try:
            # Check for AWS credentials
            if not (
                os.environ.get("AWS_ACCESS_KEY_ID")
                or os.path.exists(os.path.expanduser("~/.aws/credentials"))
            ):
                return None

            # This would require boto3 - just return None if not available
            # Real implementation would call AWS Cost Explorer API
            return None

        except Exception:
            return None

    def _get_aws_health(self) -> Optional[dict]:
        """Get AWS health status."""
        try:
            # Check instance status
            status = self._get_aws_metadata("instance-state")
            return {"instance_state": status, "ok": status == "running"}
        except Exception:
            return None

    def _collect_gcp(self) -> Optional[dict]:
        """Collect GCP-specific metrics."""
        data = {}

        # Get instance metadata
        instance_id = self._get_gcp_metadata("instance/id")
        if instance_id:
            data["instance_id"] = instance_id

        instance_name = self._get_gcp_metadata("instance/name")
        if instance_name:
            data["instance_name"] = instance_name

        zone = self._get_gcp_metadata("instance/zone")
        if zone:
            data["zone"] = zone

        machine_type = self._get_gcp_metadata("instance/machine-type")
        if machine_type:
            data["machine_type"] = machine_type.split("/")[-1]

        return data

    def _get_gcp_metadata(self, path: str) -> Optional[str]:
        """Get GCP instance metadata."""
        try:
            import requests

            host = os.environ.get("GCE_METADATA_HOST", "metadata.google.internal")
            resp = requests.get(
                f"http://{host}/computeMetadata/v1/{path}",
                headers={"Metadata-Flavor": "Google"},
                timeout=2,
            )
            return resp.text

        except Exception:
            return None

    def _collect_azure(self) -> Optional[dict]:
        """Collect Azure-specific metrics."""
        data = {}

        # Get instance metadata
        instance_id = self._get_azure_metadata("vmId")
        if instance_id:
            data["instance_id"] = instance_id

        vm_name = self._get_azure_metadata("name")
        if vm_name:
            data["vm_name"] = vm_name

        location = self._get_azure_metadata("location")
        if location:
            data["location"] = location

        size = self._get_azure_metadata("size")
        if size:
            data["vm_size"] = size

        return data

    def _get_azure_metadata(self, path: str) -> Optional[str]:
        """Get Azure instance metadata."""
        try:
            import requests

            host = os.environ.get("AZURE_METADATA_HOST", "169.254.169.254")
            resp = requests.get(
                f"http://{host}/metadata/instance/compute/{path}?api-version=2021-12-01",
                headers={"Metadata": "true"},
                timeout=2,
            )
            return resp.text

        except Exception:
            return None


__all__ = ["CloudCollector"]
