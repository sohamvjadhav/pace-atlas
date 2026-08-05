"""
PACE Atlas — Log Aggregator

Collects and aggregates system logs for analysis.

This collector reads and parses system logs to detect events
that may require attention - errors, warnings, critical messages.

Metrics Collected:
- Recent errors (last N minutes)
- Critical messages
- Service restart events
- Kernel events

Author: PACE Atlas
Version: 0.1.0
"""

import re
from datetime import datetime, timedelta
from typing import Optional

from .base import TelemetryCollector, TelemetrySnapshot, CollectionError


class LogAggregator(TelemetryCollector):
    """
    Aggregates system logs for analysis.

    Reads from journalctl, auth.log, syslog for events.
    """

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        self.error_count = config.get("error_count", 10) if config else 10
        self.time_window_minutes = (
            config.get("time_window_minutes", 30) if config else 30
        )

    @property
    def name(self) -> str:
        return "logs"

    @property
    def interval(self) -> int:
        return 60  # Check every 60 seconds

    def collect(self) -> TelemetrySnapshot:
        """
        Collect and aggregate logs.

        Returns:
            TelemetrySnapshot with:
            - error_count: Number of errors in time window
            - critical_count: Number of critical messages
            - warnings_count: Number of warnings
            - service_restarts: Services that restarted
            - recent_errors: List of recent error messages
            - kernel_events: Recent kernel events
        """
        try:
            data = {}

            # Get error count
            errors = self._get_error_count()
            if errors is not None:
                data["error_count"] = errors
                if errors > self.error_count:
                    data["high_error_rate"] = True

            # Get critical messages
            critical = self._get_critical_count()
            if critical is not None:
                data["critical_count"] = critical
                if critical > 0:
                    data["has_critical"] = True

            # Get warning count
            warnings = self._get_warning_count()
            if warnings is not None:
                data["warnings_count"] = warnings

            # Get service restarts
            restarts = self._get_service_restarts()
            if restarts:
                data["service_restarts"] = restarts
                if len(restarts) > 0:
                    data["has_restarts"] = True

            # Get recent errors
            recent_errors = self._get_recent_errors()
            if recent_errors:
                data["recent_errors"] = recent_errors[:5]  # Limit to 5

            # Get disk/health events
            disk_events = self._get_disk_events()
            if disk_events:
                data["disk_events"] = disk_events

            return TelemetrySnapshot(
                timestamp=datetime.now(),
                collector_name=self.name,
                data=data,
                metadata=self.get_metadata(),
            )

        except Exception as e:
            raise CollectionError(self.name, str(e))

    def _get_error_count(self) -> Optional[int]:
        """Get count of errors in time window."""
        try:
            output = self._run_command(
                f"journalctl --since '{self.time_window_minutes} minutes ago' "
                f"--priority=err --no-pager -q 2>/dev/null | wc -l"
            )

            if not output:
                output = self._run_command(
                    f"grep -i error /var/log/syslog 2>/dev/null | tail -50 | wc -l"
                )

            if output:
                return int(output.strip())
            return 0

        except Exception:
            return None

    def _get_critical_count(self) -> Optional[int]:
        """Get count of critical messages."""
        try:
            output = self._run_command(
                f"journalctl --since '{self.time_window_minutes} minutes ago' "
                f"--priority=crit --no-pager -q 2>/dev/null | wc -l"
            )

            if output:
                return int(output.strip())
            return 0

        except Exception:
            return None

    def _get_warning_count(self) -> Optional[int]:
        """Get count of warnings."""
        try:
            output = self._run_command(
                f"journalctl --since '{self.time_window_minutes} minutes ago' "
                f"--priority=warning --no-pager -q 2>/dev/null | wc -l"
            )

            if output:
                return int(output.strip())
            return 0

        except Exception:
            return None

    def _get_service_restarts(self) -> list:
        """Get services that recently restarted."""
        restarts = []

        try:
            # Check for service restarts in journalctl
            output = self._run_command(
                f"journalctl --since '{self.time_window_minutes} minutes ago' 2>/dev/null | "
                f"grep -i 'started.' | tail -10"
            )

            if output:
                for line in output.split("\n"):
                    if line.strip():
                        # Extract service name
                        match = re.search(r"Started (.+)", line)
                        if match:
                            restarts.append(match.group(1))

                        match = re.search(r"Restarted (.+)", line)
                        if match:
                            restarts.append(f"{match.group(1)} (restart)")

        except Exception:
            pass

        return restarts[:10]  # Limit to 10

    def _get_recent_errors(self) -> list:
        """Get recent error messages."""
        errors = []

        try:
            output = self._run_command(
                f"journalctl --since '{self.time_window_minutes} minutes ago' "
                f"--priority=err --no-pager -q 2>/dev/null | tail -10"
            )

            if not output:
                output = self._run_command(
                    f"grep -i error /var/log/syslog 2>/dev/null | tail -10"
                )

            if output:
                for line in output.split("\n"):
                    if line.strip():
                        # Truncate long lines
                        errors.append(line[:150])

        except Exception:
            pass

        return errors[:5]

    def _get_disk_events(self) -> list:
        """Get disk-related events (I/O errors, etc)."""
        events = []

        try:
            output = self._run_command(
                f"journalctl --since '{self.time_window_minutes} minutes ago' 2>/dev/null | "
                f"grep -i 'disk\\|I/O error\\|EXT4-fs error' | tail -5"
            )

            if output:
                for line in output.split("\n"):
                    if line.strip():
                        events.append(line[:150])

        except Exception:
            pass

        return events


# For backwards compatibility
from .base import TelemetryCollector as BaseCollector

__all__ = ["LogAggregator", "BaseCollector"]
