"""
PACE Atlas — System Metrics Collector

Collects CPU and load average metrics from Linux /proc filesystem.

This collector provides the core system metrics that form the baseline
of server monitoring. It reads directly from /proc which external
monitors cannot access.

Metrics Collected:
- CPU usage (overall and per-core)
- Load averages (1, 5, 15 minute)
- CPU context switches
- Interrupts
- CPU steal time (for virtualized environments)

Author: PACE Atlas
Version: 0.1.0
"""

import os
import time
from datetime import datetime
from typing import Optional

from .base import TelemetryCollector, TelemetrySnapshot, CollectionError


class SystemCollector(TelemetryCollector):
    """
    Collects CPU and system load metrics.

    Reads from /proc for metrics that external monitors cannot access.
    """

    @property
    def name(self) -> str:
        return "system"

    @property
    def interval(self) -> int:
        return 30  # Collect every 30 seconds

    def validate(self) -> bool:
        """Check if we can read /proc."""
        return os.path.exists("/proc/stat")

    def collect(self) -> TelemetrySnapshot:
        """
        Collect CPU and load metrics.

        Returns:
            TelemetrySnapshot with:
            - cpu_percent: Overall CPU usage %
            - cpu_cores: Per-core usage (if available)
            - load_avg: (1min, 5min, 15min) load averages
            - context_switches: Number of context switches
            - interrupts: Number of interrupts
            - uptime: System uptime in seconds
        """
        try:
            data = {}

            # Get CPU usage
            cpu_data = self._get_cpu_usage()
            if cpu_data:
                data["cpu_percent"] = cpu_data["percent"]
                data["cpu_cores"] = cpu_data.get("per_core", {})
                data["cpu_model"] = cpu_data.get("model", "unknown")

            # Get load averages
            load_avg = self._get_load_average()
            if load_avg:
                data["load_avg"] = load_avg

            # Get uptime
            uptime = self._get_uptime()
            if uptime:
                data["uptime_seconds"] = uptime
                data["uptime_formatted"] = self._format_uptime(uptime)

            # Get context switches and interrupts
            stats = self._get_stat()
            if stats:
                data["context_switches"] = stats.get("ctxt", 0)
                data["interrupts"] = stats.get("intr", 0)

            # Get CPU steal (for virtualized environments)
            cpu_stat = self._read_file("/proc/stat")
            if cpu_stat:
                for line in cpu_stat.split("\n"):
                    if line.startswith("cpu ") or line.startswith("cpu"):
                        parts = line.split()
                        if len(parts) >= 8:
                            # steal is the 8th field (index 7)
                            try:
                                steal_time = int(parts[7])
                                # Convert to percentage (steal / total * 100)
                                total = sum(int(p) for p in parts[1:8])
                                if total > 0:
                                    data["cpu_steal_percent"] = round(
                                        steal_time / total * 100, 2
                                    )
                            except (IndexError, ValueError):
                                pass

            return TelemetrySnapshot(
                timestamp=datetime.now(),
                collector_name=self.name,
                data=data,
                metadata=self.get_metadata(),
            )

        except Exception as e:
            raise CollectionError(self.name, str(e))

    def _get_cpu_usage(self) -> dict:
        """Calculate CPU usage from /proc/stat"""
        try:
            # Read first line of /proc/stat for overall CPU
            stat_content = self._read_file("/proc/stat")
            if not stat_content:
                return {}

            lines = stat_content.split("\n")
            cpu_line = lines[0]  # "cpu  user nice system idle iowait irq softirq..."

            # Get first snapshot
            fields = cpu_line.split()
            if len(fields) < 5:
                return {}

            # Parse first line (cpu aggregate)
            user1 = int(fields[1])
            nice1 = int(fields[2])
            system1 = int(fields[3])
            idle1 = int(fields[4])
            iowait1 = int(fields[5]) if len(fields) > 5 else 0
            irq1 = int(fields[6]) if len(fields) > 6 else 0
            softirq1 = int(fields[7]) if len(fields) > 7 else 0

            total1 = user1 + nice1 + system1 + idle1 + iowait1 + irq1 + softirq1
            idle1_total = idle1 + iowait1

            # Wait a tiny bit and get second snapshot
            time.sleep(0.1)

            stat_content = self._read_file("/proc/stat")
            lines = stat_content.split("\n")
            cpu_line = lines[0]
            fields = cpu_line.split()

            user2 = int(fields[1])
            nice2 = int(fields[2])
            system2 = int(fields[3])
            idle2 = int(fields[4])
            iowait2 = int(fields[5]) if len(fields) > 5 else 0
            irq2 = int(fields[6]) if len(fields) > 6 else 0
            softirq2 = int(fields[7]) if len(fields) > 7 else 0

            total2 = user2 + nice2 + system2 + idle2 + iowait2 + irq2 + softirq2
            idle2_total = idle2 + iowait2

            # Calculate percentage
            total_diff = total2 - total1
            idle_diff = idle2_total - idle1_total

            if total_diff > 0:
                cpu_percent = round((total_diff - idle_diff) / total_diff * 100, 1)
            else:
                cpu_percent = 0.0

            # Get per-core data
            per_core = {}
            for line in lines[1:]:
                if line.startswith("cpu") and line[3:].isdigit():
                    parts = line.split()
                    if len(parts) >= 5:
                        core_id = int(parts[0][3:])
                        core_user = int(parts[1])
                        core_nice = int(parts[2])
                        core_system = int(parts[3])
                        core_idle = int(parts[4])
                        core_total = core_user + core_nice + core_system + core_idle
                        if core_total > 0:
                            core_usage = round(
                                (core_total - core_idle) / core_total * 100, 1
                            )
                            per_core[core_id] = core_usage

            # Get CPU model name
            model = "unknown"
            cpuinfo = self._read_file("/proc/cpuinfo")
            if cpuinfo:
                for line in cpuinfo.split("\n"):
                    if "model name" in line:
                        model = line.split(":", 1)[1].strip()
                        break

            return {"percent": cpu_percent, "per_core": per_core, "model": model}

        except Exception as e:
            return {"percent": 0.0, "error": str(e)}

    def _get_load_average(self) -> Optional[dict]:
        """Get load averages from /proc/loadavg"""
        try:
            content = self._read_file("/proc/loadavg")
            if not content:
                return None

            parts = content.split()
            if len(parts) < 3:
                return None

            return {
                "1min": round(float(parts[0]), 2),
                "5min": round(float(parts[1]), 2),
                "15min": round(float(parts[2]), 2),
            }
        except Exception:
            return None

    def _get_uptime(self) -> Optional[int]:
        """Get system uptime in seconds from /proc/uptime"""
        try:
            content = self._read_file("/proc/uptime")
            if not content:
                return None

            uptime_seconds = float(content.split()[0])
            return int(uptime_seconds)
        except Exception:
            return None

    def _get_stat(self) -> Optional[dict]:
        """Get context switches and interrupts from /proc/stat"""
        try:
            content = self._read_file("/proc/stat")
            if not content:
                return None

            result = {}
            for line in content.split("\n"):
                if line.startswith("ctxt "):
                    result["ctxt"] = int(line.split()[1])
                elif line.startswith("intr "):
                    result["intr"] = int(line.split()[1])

            return result if result else None
        except Exception:
            return None

    def _format_uptime(self, seconds: int) -> str:
        """Format uptime seconds to human readable string."""
        days = seconds // 86400
        hours = (seconds % 86400) // 3600
        minutes = (seconds % 3600) // 60

        parts = []
        if days > 0:
            parts.append(f"{days}d")
        if hours > 0:
            parts.append(f"{hours}h")
        if minutes > 0:
            parts.append(f"{minutes}m")

        return " ".join(parts) if parts else "0m"


# Export for easy import
__all__ = ["SystemCollector"]
