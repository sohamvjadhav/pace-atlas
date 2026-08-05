"""
PACE Atlas — Memory Metrics Collector

Collects RAM and swap memory metrics from Linux /proc filesystem.

This collector reads /proc/meminfo to get memory statistics that
external monitors cannot access directly.

Metrics Collected:
- Total, used, available memory
- Swap usage (total, used, cached)
- Memory available for applications
- Memory pressure indicators

Author: PACE Atlas
Version: 0.1.0
"""

import re
from datetime import datetime
from typing import Optional

from .base import TelemetryCollector, TelemetrySnapshot, CollectionError


class MemoryCollector(TelemetryCollector):
    """
    Collects memory and swap metrics.

    Reads from /proc/meminfo for internal memory data.
    """

    @property
    def name(self) -> str:
        return "memory"

    @property
    def interval(self) -> int:
        return 30  # Collect every 30 seconds

    def validate(self) -> bool:
        """Check if we can read /proc/meminfo."""
        import os

        return os.path.exists("/proc/meminfo")

    def collect(self) -> TelemetrySnapshot:
        """
        Collect memory metrics.

        Returns:
            TelemetrySnapshot with:
            - total_mb: Total memory in MB
            - used_mb: Used memory in MB
            - available_mb: Available memory in MB
            - usage_percent: Usage percentage
            - swap_total_mb: Total swap in MB
            - swap_used_mb: Used swap in MB
            - swap_percent: Swap usage percentage
            - buffers_mb: Buffers in MB
            - cached_mb: Cached memory in MB
        """
        try:
            data = {}

            # Read /proc/meminfo
            meminfo = self._read_file("/proc/meminfo")
            if not meminfo:
                raise CollectionError(self.name, "Cannot read /proc/meminfo")

            # Parse meminfo
            mem_values = {}
            for line in meminfo.split("\n"):
                if ":" in line:
                    key, value = line.split(":", 1)
                    key = key.strip()
                    value = value.strip().split()[0]  # Get number, ignore unit
                    try:
                        mem_values[key] = int(value)  # Values are in KB
                    except ValueError:
                        pass

            # Calculate memory in MB
            total_kb = mem_values.get("MemTotal", 0)
            free_kb = mem_values.get("MemFree", 0)
            available_kb = mem_values.get("MemAvailable", 0)
            buffers_kb = mem_values.get("Buffers", 0)
            cached_kb = mem_values.get("Cached", 0)
            sreclaimable_kb = mem_values.get("SReclaimable", 0)

            # Used = total - available (more accurate than total - free)
            used_kb = total_kb - available_kb

            data["total_mb"] = round(total_kb / 1024)
            data["used_mb"] = round(used_kb / 1024)
            data["available_mb"] = round(available_kb / 1024)
            data["free_mb"] = round(free_kb / 1024)
            data["usage_percent"] = round(
                (used_kb / total_kb * 100) if total_kb > 0 else 0, 1
            )

            # Buffers and cache
            data["buffers_mb"] = round(buffers_kb / 1024)
            data["cached_mb"] = round((cached_kb + sreclaimable_kb) / 1024)

            # Swap metrics
            swap_total_kb = mem_values.get("SwapTotal", 0)
            swap_free_kb = mem_values.get("SwapFree", 0)
            swap_used_kb = swap_total_kb - swap_free_kb

            data["swap_total_mb"] = round(swap_total_kb / 1024)
            data["swap_used_mb"] = round(swap_used_kb / 1024)
            data["swap_free_mb"] = round(swap_free_kb / 1024)
            data["swap_percent"] = round(
                (swap_used_kb / swap_total_kb * 100) if swap_total_kb > 0 else 0, 1
            )

            # Detect memory pressure (if available)
            pressure = self._get_memory_pressure()
            if pressure:
                data["memory_pressure"] = pressure

            # Detect OOM killer activity
            oom_events = self._check_oom()
            if oom_events > 0:
                data["oom_events"] = oom_events

            return TelemetrySnapshot(
                timestamp=datetime.now(),
                collector_name=self.name,
                data=data,
                metadata=self.get_metadata(),
            )

        except Exception as e:
            raise CollectionError(self.name, str(e))

    def _get_memory_pressure(self) -> Optional[dict]:
        """Read memory pressure from /proc/pressure (if available)"""
        try:
            # Try to read pressure stats (kernel 5.14+)
            pressure_io = self._read_file("/proc/pressure/io")
            pressure_memory = self._read_file("/proc/pressure/memory")

            result = {}

            if pressure_memory:
                # Parse: avg10=0.00 avg60=0.00 avg300=0.00 total=0
                match = re.search(r"avg10=([0-9.]+)", pressure_memory)
                if match:
                    result["avg10sec"] = round(float(match.group(1)), 2)

                match = re.search(r"avg60=([0-9.]+)", pressure_memory)
                if match:
                    result["avg60sec"] = round(float(match.group(1)), 2)

            if pressure_io:
                match = re.search(r"avg10=([0-9.]+)", pressure_io)
                if match:
                    result["io_avg10sec"] = round(float(match.group(1)), 2)

            return result if result else None

        except Exception:
            return None

    def _check_oom(self) -> int:
        """Check for recent OOM killer events in dmesg"""
        try:
            # Check kernel logs for OOM killer
            dmesg_output = self._run_command(
                "dmesg | grep -i 'Out of memory' | tail -5"
            )
            if dmesg_output:
                lines = dmesg_output.strip().split("\n")
                return len([l for l in lines if l])
            return 0
        except Exception:
            return 0


__all__ = ["MemoryCollector"]
