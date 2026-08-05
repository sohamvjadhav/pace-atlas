"""
PACE Atlas — Disk Metrics Collector

Collects disk usage and I/O metrics from Linux.

Metrics Collected:
- Disk usage per mount point (%)
- Inode usage
- Disk I/O statistics
- Mount point list

Author: PACE Atlas
Version: 0.1.0
"""

import os
import re
from datetime import datetime
from typing import Optional

from .base import TelemetryCollector, TelemetrySnapshot, CollectionError


class DiskCollector(TelemetryCollector):
    """
    Collects disk usage and I/O metrics.

    Uses df and /proc/diskstats for comprehensive disk monitoring.
    """

    @property
    def name(self) -> str:
        return "disk"

    @property
    def interval(self) -> int:
        return 60  # Collect every 60 seconds

    def collect(self) -> TelemetrySnapshot:
        """
        Collect disk metrics.

        Returns:
            TelemetrySnapshot with:
            - mount_points: List of mount points with usage
            - total_gb: Total disk space in GB
            - used_gb: Used disk space in GB
            - available_gb: Available disk space in GB
            - usage_percent: Overall usage %
            - inode_usage: Inode usage per filesystem
            - io_stats: I/O statistics (if available)
        """
        try:
            data = {}

            # Get disk usage by mount point
            mount_points = self._get_disk_usage()
            data["mount_points"] = mount_points

            # Calculate totals
            total_bytes = sum(m["total_bytes"] for m in mount_points)
            used_bytes = sum(m["used_bytes"] for m in mount_points)
            available_bytes = sum(m["available_bytes"] for m in mount_points)

            data["total_gb"] = round(total_bytes / (1024**3), 2)
            data["used_gb"] = round(used_bytes / (1024**3), 2)
            data["available_gb"] = round(available_bytes / (1024**3), 2)
            data["usage_percent"] = round(
                (used_bytes / total_bytes * 100) if total_bytes > 0 else 0, 1
            )

            # Get inode usage
            inode_usage = self._get_inode_usage()
            if inode_usage:
                data["inode_usage"] = inode_usage

            # Get I/O stats
            io_stats = self._get_io_stats()
            if io_stats:
                data["io_stats"] = io_stats

            # Check for disk pressure
            disk_pressure = self._get_disk_pressure()
            if disk_pressure:
                data["disk_pressure"] = disk_pressure

            return TelemetrySnapshot(
                timestamp=datetime.now(),
                collector_name=self.name,
                data=data,
                metadata=self.get_metadata(),
            )

        except Exception as e:
            raise CollectionError(self.name, str(e))

    def _get_disk_usage(self) -> list[dict]:
        """Get disk usage per mount point using df"""
        mount_points = []

        try:
            # Use df -TB1 to get exact bytes
            output = self._run_command("df -TB1 2>/dev/null | tail -n +2")
            if not output:
                return mount_points

            for line in output.split("\n"):
                parts = line.split()
                if len(parts) >= 7:
                    filesystem = parts[0]
                    mount = parts[6]

                    # Skip pseudo filesystems
                    if any(
                        x in filesystem
                        for x in ["tmpfs", "devtmpfs", "overlay", "squashfs", "loop"]
                    ):
                        if not mount.startswith("/"):
                            continue

                    try:
                        total = int(parts[2])
                        used = int(parts[3])
                        available = int(parts[4])
                        use_percent = int(parts[5].rstrip("%"))

                        mount_points.append(
                            {
                                "filesystem": filesystem,
                                "mount": mount,
                                "total_bytes": total,
                                "used_bytes": used,
                                "available_bytes": available,
                                "usage_percent": use_percent,
                                "total_gb": round(total / (1024**3), 2),
                                "used_gb": round(used / (1024**3), 2),
                                "available_gb": round(available / (1024**3), 2),
                            }
                        )
                    except (ValueError, IndexError):
                        continue

        except Exception:
            pass

        return mount_points

    def _get_inode_usage(self) -> list[dict]:
        """Get inode usage per mount point"""
        inode_usage = []

        try:
            output = self._run_command("df -i 2>/dev/null | tail -n +2")
            if not output:
                return inode_usage

            for line in output.split("\n"):
                parts = line.split()
                if len(parts) >= 6:
                    try:
                        inode_usage.append(
                            {
                                "filesystem": parts[0],
                                "mount": parts[5] if len(parts) > 5 else parts[0],
                                "inodes_used": int(parts[2]),
                                "inodes_available": int(parts[3]),
                                "inodes_percent": int(parts[4].rstrip("%")),
                            }
                        )
                    except (ValueError, IndexError):
                        continue

        except Exception:
            pass

        return inode_usage

    def _get_io_stats(self) -> Optional[dict]:
        """Get I/O statistics from /proc/diskstats"""
        try:
            stats = self._read_file("/proc/diskstats")
            if not stats:
                return None

            total_reads = 0
            total_writes = 0
            total_read_bytes = 0
            total_write_bytes = 0

            for line in stats.split("\n"):
                parts = line.split()
                if len(parts) < 14:
                    continue

                # Skip loop devices
                if parts[2].startswith("loop"):
                    continue

                try:
                    # Fields: reads completed, reads merged, sectors read, time reading...
                    # ... writes completed, writes merged, sectors written, time writing
                    reads = int(parts[3])
                    sectors_read = int(parts[5])
                    writes = int(parts[7])
                    sectors_written = int(parts[9])

                    total_reads += reads
                    total_writes += writes
                    total_read_bytes += sectors_read * 512
                    total_write_bytes += sectors_written * 512
                except (ValueError, IndexError):
                    continue

            return {
                "total_reads": total_reads,
                "total_writes": total_writes,
                "read_mb": round(total_read_bytes / (1024**2), 2),
                "write_mb": round(total_write_bytes / (1024**2), 2),
            }

        except Exception:
            return None

    def _get_disk_pressure(self) -> Optional[dict]:
        """Get disk pressure stats if available"""
        try:
            pressure = self._read_file("/proc/pressure/io")
            if not pressure:
                return None

            result = {}
            match = re.search(r"avg10=([0-9.]+)", pressure)
            if match:
                result["avg10sec"] = round(float(match.group(1)), 2)

            match = re.search(r"avg60=([0-9.]+)", pressure)
            if match:
                result["avg60sec"] = round(float(match.group(1)), 2)

            return result if result else None

        except Exception:
            return None


__all__ = ["DiskCollector"]
