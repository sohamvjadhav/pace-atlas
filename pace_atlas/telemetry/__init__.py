"""
PACE Atlas — Telemetry Collection Module

This module provides the core telemetry collection functionality for PACE Atlas.
Each collector class gathers specific metrics from the server and returns them
in a standardized format for the Alert Engine.

All collectors run as a "resident agent" inside the server, giving them full
visibility into system internals that external monitors cannot access.

Module Structure:
- base.py: Abstract base class for all collectors
- system.py: CPU and load average metrics
- memory.py: RAM and swap metrics
- disk.py: Disk usage and I/O metrics
- network.py: Network connections and bandwidth
- process.py: Process list and service status
- security.py: Security events and auth logs
- logs.py: Log aggregation
- cloud.py: Cloud provider APIs (AWS, GCP, Azure)

Usage:
    from pace_atlas.telemetry import CompositeCollector, get_default_collectors

    # Get all default collectors
    collectors = get_default_collectors()

    # Or build manually
    composite = CompositeCollector()
    composite.add_collector(SystemCollector())
    composite.add_collector(MemoryCollector())

    # Collect all metrics
    snapshots = composite.collect_all()

    # Convert to string for LLM
    telemetry_str = composite.to_telemetry_string(snapshots)
"""

from .base import (
    TelemetryCollector,
    TelemetrySnapshot,
    CompositeCollector,
    CollectionError,
    get_default_collectors,
)

# Import all collectors for convenience
from .system import SystemCollector
from .memory import MemoryCollector
from .disk import DiskCollector
from .network import NetworkCollector
from .process import ProcessCollector
from .security import SecurityCollector
from .cloud import CloudCollector
from .logs import LogAggregator

__all__ = [
    # Base classes
    "TelemetryCollector",
    "TelemetrySnapshot",
    "CompositeCollector",
    "CollectionError",
    "get_default_collectors",
    # Collectors
    "SystemCollector",
    "MemoryCollector",
    "DiskCollector",
    "NetworkCollector",
    "ProcessCollector",
    "SecurityCollector",
    "CloudCollector",
    "LogAggregator",
]
