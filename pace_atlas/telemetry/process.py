"""
PACE Atlas — Process Metrics Collector

Collects process and service status metrics from Linux.

Metrics Collected:
- Process count by state
- Top CPU-consuming processes
- Top memory-consuming processes
- Systemd services in failed state
- Zombie processes

Author: PACE Atlas
Version: 0.1.0
"""

from datetime import datetime
from typing import Optional

from .base import TelemetryCollector, TelemetrySnapshot, CollectionError


class ProcessCollector(TelemetryCollector):
    """
    Collects process and service metrics.

    Uses ps, systemctl, and /proc for process data.
    """

    @property
    def name(self) -> str:
        return "process"

    @property
    def interval(self) -> int:
        return 30  # Collect every 30 seconds

    def collect(self) -> TelemetrySnapshot:
        """
        Collect process metrics.

        Returns:
            TelemetrySnapshot with:
            - total_processes: Total process count
            - running_processes: Running process count
            - sleeping_processes: Sleeping process count
            - top_cpu: Top 5 CPU-consuming processes
            - top_memory: Top 5 memory-consuming processes
            - failed_services: List of failed systemd services
            - zombie_processes: Count of zombie processes
        """
        try:
            data = {}

            # Get process counts
            proc_counts = self._get_process_counts()
            if proc_counts:
                data.update(proc_counts)

            # Get top processes by CPU
            top_cpu = self._get_top_processes("cpu")
            if top_cpu:
                data["top_cpu"] = top_cpu

            # Get top processes by memory
            top_mem = self._get_top_processes("mem")
            if top_mem:
                data["top_memory"] = top_mem

            # Get systemd services status
            failed_services = self._get_failed_services()
            if failed_services is not None:
                data["failed_services"] = failed_services
                if failed_services:
                    data["failed_services_count"] = len(failed_services)

            # Get zombie processes
            zombies = self._get_zombie_processes()
            if zombies is not None:
                data["zombie_count"] = zombies

            return TelemetrySnapshot(
                timestamp=datetime.now(),
                collector_name=self.name,
                data=data,
                metadata=self.get_metadata(),
            )

        except Exception as e:
            raise CollectionError(self.name, str(e))

    def _get_process_counts(self) -> Optional[dict]:
        """Get process counts by state"""
        try:
            output = self._run_command("ps -eo state= | sort | uniq -c")
            if not output:
                return None

            result = {
                "total_processes": 0,
                "running_processes": 0,
                "sleeping_processes": 0,
                "stopped_processes": 0,
                "zombie_processes": 0,
            }

            state_map = {
                "R": "running",
                "S": "sleeping",
                "D": "sleeping",  # Uninterruptible sleep
                "T": "stopped",
                "t": "stopped",  # Tracing stop
                "Z": "zombie",
                "I": "sleeping",  # Idle
            }

            for line in output.strip().split("\n"):
                parts = line.strip().split()
                if len(parts) >= 2:
                    count = int(parts[0])
                    state = parts[1]
                    result["total_processes"] += count

                    mapped = state_map.get(state, "sleeping")
                    if mapped == "running":
                        result["running_processes"] += count
                    elif mapped == "sleeping":
                        result["sleeping_processes"] += count
                    elif mapped == "stopped":
                        result["stopped_processes"] += count
                    elif mapped == "zombie":
                        result["zombie_processes"] += count

            return result

        except Exception:
            return None

    def _get_top_processes(self, sort_by: str = "cpu", limit: int = 5) -> list[dict]:
        """
        Get top processes by CPU or memory usage.

        Args:
            sort_by: "cpu" or "mem"
            limit: Number of processes to return
        """
        try:
            if sort_by == "cpu":
                # Sort by CPU usage
                output = self._run_command(
                    f"ps -eo pid,pcpu,pmem,user,comm --no-headers | "
                    f'head -n {limit} | awk \'{{print $1","$2","$3","$4","$5}}\''
                )
            else:
                # Sort by memory usage
                output = self._run_command(
                    f"ps -eo pid,pcpu,pmem,user,comm --no-headers -o pmem= | "
                    f"sort -rn | head -n {limit}"
                )
                if output:
                    # Get full info for top memory processes
                    output = self._run_command(
                        f"ps -eo pid,pcpu,pmem,user,comm --no-headers | "
                        f'sort -k3 -rn | head -n {limit} | awk \'{{print $1","$2","$3","$4","$5}}\''
                    )

            if not output:
                return []

            processes = []
            for line in output.strip().split("\n"):
                if not line.strip():
                    continue
                parts = line.strip().split(",")
                if len(parts) >= 5:
                    try:
                        processes.append(
                            {
                                "pid": int(parts[0]),
                                "cpu_percent": float(parts[1]),
                                "mem_percent": float(parts[2]),
                                "user": parts[3],
                                "command": parts[4],
                            }
                        )
                    except (ValueError, IndexError):
                        continue

            return processes

        except Exception:
            return []

    def _get_failed_services(self) -> Optional[list]:
        """Get list of failed systemd services"""
        try:
            output = self._run_command(
                "systemctl --failed --no-pager --no-legend 2>/dev/null"
            )
            if not output:
                return []

            services = []
            for line in output.strip().split("\n"):
                if line.strip():
                    parts = line.strip().split()
                    if parts:
                        services.append(parts[0])

            return services

        except Exception:
            return None  # systemctl not available

    def _get_zombie_processes(self) -> Optional[int]:
        """Count zombie processes"""
        try:
            output = self._run_command("ps -eo state= | grep -c Z")
            if output:
                return int(output.strip())
            return 0
        except Exception:
            return None


__all__ = ["ProcessCollector"]
