"""
PACE Atlas — Base Telemetry Classes

Defines the abstract base classes and common utilities for all telemetry collectors.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional
import os
import subprocess
import logging

logger = logging.getLogger(__name__)


@dataclass
class TelemetrySnapshot:
    """
    Standardized telemetry data structure.

    All collectors return their data in this format for consistent processing.

    Attributes:
        timestamp: When the data was collected
        collector_name: Name of the collector that generated this
        data: The actual telemetry data
        metadata: Additional metadata about the collection
    """

    timestamp: datetime
    collector_name: str
    data: dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "collector": self.collector_name,
            "data": self.data,
            "metadata": self.metadata,
        }


class TelemetryCollector(ABC):
    """
    Abstract base class for all telemetry collectors.

    Each collector gathers a specific type of metric from the server.
    All collectors have access to internal system files (/proc, /var/log, etc.)
    that external monitoring tools cannot access.

    Example:
        class MyCollector(TelemetryCollector):
            @property
            def name(self) -> str:
                return "my_collector"

            def collect(self) -> TelemetrySnapshot:
                # Collect and return data
                return TelemetrySnapshot(
                    timestamp=datetime.now(),
                    collector_name=self.name,
                    data={"key": "value"}
                )
    """

    def __init__(self, config: dict | None = None):
        """
        Initialize the collector with optional configuration.

        Args:
            config: Optional configuration dict for this collector
        """
        self.config = config or {}
        self._last_collection: Optional[datetime] = None

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier for this collector."""
        pass

    @property
    def interval(self) -> int:
        """Collection interval in seconds. Override in subclass if needed."""
        return 30

    @property
    def enabled(self) -> bool:
        """Whether this collector is active. Override if needed."""
        return True

    @abstractmethod
    def collect(self) -> TelemetrySnapshot:
        """
        Collect metrics and return as TelemetrySnapshot.

        This is the main method that each collector implements.
        It should gather data from internal system sources.

        Returns:
            TelemetrySnapshot with collected data

        Raises:
            CollectionError: If collection fails
        """
        pass

    def validate(self) -> bool:
        """
        Validate that this collector can run on the current system.

        Override this to check for required binaries, permissions, etc.

        Returns:
            True if collector can run, False otherwise
        """
        return True

    def get_metadata(self) -> dict:
        """Get collector metadata for logging/debugging."""
        return {
            "name": self.name,
            "interval": self.interval,
            "enabled": self.enabled,
            "last_collection": self._last_collection.isoformat()
            if self._last_collection
            else None,
        }

    def _run_command(self, cmd: str, timeout: int = 5) -> Optional[str]:
        """
        Safely run a shell command and return output.

        Args:
            cmd: Command to run
            timeout: Timeout in seconds

        Returns:
            Command output or None if failed
        """
        try:
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, timeout=timeout
            )
            return result.stdout if result.returncode == 0 else None
        except (subprocess.TimeoutExpired, subprocess.SubprocessError) as e:
            logger.debug(f"Command failed: {cmd} - {e}")
            return None

    def _read_file(self, path: str, max_lines: int = 100) -> Optional[str]:
        """
        Safely read a file and return contents.

        Args:
            path: File path to read
            max_lines: Maximum lines to read

        Returns:
            File contents or None if failed
        """
        try:
            with open(path, "r", encoding="utf-8") as f:
                lines = []
                for i, line in enumerate(f):
                    if i >= max_lines:
                        break
                    lines.append(line.rstrip())
                return "\n".join(lines)
        except (IOError, PermissionError) as e:
            logger.debug(f"Failed to read {path}: {e}")
            return None


class CollectionError(Exception):
    """Raised when telemetry collection fails."""

    def __init__(self, collector: str, message: str):
        self.collector = collector
        self.message = message
        super().__init__(f"{collector}: {message}")


class CompositeCollector:
    """
    Runs multiple collectors and aggregates their results.

    This is the main interface for gathering all telemetry data.

    Example:
        collector = CompositeCollector()
        collector.add_collector(SystemCollector())
        collector.add_collector(MemoryCollector())

        snapshots = collector.collect_all()
        print(collector.to_telemetry_string(snapshots))
    """

    def __init__(self):
        self.collectors: list[TelemetryCollector] = []
        self._history: list[list[TelemetrySnapshot]] = []
        self._max_history = 10  # Keep last 10 collections

    def add_collector(self, collector: TelemetryCollector) -> None:
        """
        Add a collector to the collection list.

        Args:
            collector: TelemetryCollector instance
        """
        if collector.validate():
            self.collectors.append(collector)
            logger.info(f"Added collector: {collector.name}")
        else:
            logger.warning(f"Collector {collector.name} failed validation, skipping")

    def collect_all(self) -> list[TelemetrySnapshot]:
        """
        Run all collectors and return aggregated results.

        Returns:
            List of TelemetrySnapshot from each collector
        """
        results = []

        for collector in self.collectors:
            if not collector.enabled:
                continue

            try:
                snapshot = collector.collect()
                results.append(snapshot)
                collector._last_collection = datetime.now()
            except CollectionError as e:
                logger.error(f"Collection error in {collector.name}: {e}")
            except Exception as e:
                logger.error(f"Unexpected error in {collector.name}: {e}")

        # Store in history
        self._history.append(results)
        if len(self._history) > self._max_history:
            self._history.pop(0)

        return results

    def get_history(self) -> list[list[TelemetrySnapshot]]:
        """Get collection history."""
        return self._history

    def to_telemetry_string(self, snapshots: list[TelemetrySnapshot]) -> str:
        """
        Convert snapshots to a formatted string for LLM consumption.

        This formats all collected data into a readable string
        that can be sent to the LLM for decision making.

        Args:
            snapshots: List of telemetry snapshots

        Returns:
            Formatted string of all telemetry data
        """
        lines = ["=== SERVER TELEMETRY ==="]
        lines.append(f"Collection time: {datetime.now().isoformat()}")
        lines.append(f"Collectors run: {len(snapshots)}")

        for snapshot in snapshots:
            lines.append(f"\n--- {snapshot.collector_name} ---")
            lines.append(self._format_data(snapshot.data))

        return "\n".join(lines)

    def to_compact_string(self, snapshots: list[TelemetrySnapshot]) -> str:
        """
        Convert snapshots to compact key=value format for LLM.

        Use this for quick decisions where full detail isn't needed.

        Args:
            snapshots: List of telemetry snapshots

        Returns:
            Compact formatted string
        """
        parts = []

        for snapshot in snapshots:
            for key, value in snapshot.data.items():
                if isinstance(value, (int, float, str)):
                    parts.append(f"{snapshot.collector_name}.{key}={value}")
                elif isinstance(value, list) and len(value) <= 3:
                    parts.append(f"{snapshot.collector_name}.{key}={value}")

        return " | ".join(parts)

    def _format_data(self, data: dict, indent: int = 0) -> str:
        """Format data dict into readable string."""
        lines = []
        prefix = "  " * indent

        for key, value in data.items():
            if isinstance(value, dict):
                lines.append(f"{prefix}{key}:")
                lines.append(self._format_data(value, indent + 1))
            elif isinstance(value, list):
                if len(value) <= 5:
                    lines.append(f"{prefix}{key}: {value}")
                else:
                    lines.append(f"{prefix}{key}: [{len(value)} items]")
            else:
                lines.append(f"{prefix}{key}: {value}")

        return "\n".join(lines)


# Convenience function to get all default collectors
def get_default_collectors(config: dict | None = None) -> list[TelemetryCollector]:
    """
    Return list of all default PACE Atlas collectors.

    Args:
        config: Optional configuration dict for collectors

    Returns:
        List of TelemetryCollector instances
    """
    collectors = []

    # Import collectors lazily to avoid import errors on missing deps
    collectors_map = {
        "system": "PACEAtlas.telemetry.system.SystemCollector",
        "memory": "PACEAtlas.telemetry.memory.MemoryCollector",
        "disk": "PACEAtlas.telemetry.disk.DiskCollector",
        "network": "PACEAtlas.telemetry.network.NetworkCollector",
        "process": "PACEAtlas.telemetry.process.ProcessCollector",
        "security": "PACEAtlas.telemetry.security.SecurityCollector",
        "cloud": "PACEAtlas.telemetry.cloud.CloudCollector",
    }

    for name, class_path in collectors_map.items():
        # Check if disabled in config
        if config and not config.get(f"enable_{name}", True):
            continue

        try:
            module_path, class_name = class_path.rsplit(".", 1)
            module = __import__(module_path, fromlist=[class_name])
            collector_class = getattr(module, class_name)
            collectors.append(collector_class(config))
        except ImportError:
            logger.debug(f"Collector {name} not available (missing dependency)")
        except Exception as e:
            logger.warning(f"Failed to load collector {name}: {e}")

    return collectors
