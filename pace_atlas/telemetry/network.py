"""
PACE Atlas — Network Metrics Collector

Collects network connection and bandwidth metrics from Linux.

Metrics Collected:
- Active connections (TCP, UDP)
- Connection states (established, time_wait, etc.)
- Network interfaces and stats
- Failed connection attempts

Author: PACE Atlas
Version: 0.1.0
"""

import os
import re
from datetime import datetime
from typing import Optional

from .base import TelemetryCollector, TelemetrySnapshot, CollectionError


class NetworkCollector(TelemetryCollector):
    """
    Collects network connection and traffic metrics.

    Uses ss, netstat, and /proc/net for network data.
    """

    @property
    def name(self) -> str:
        return "network"

    @property
    def interval(self) -> int:
        return 30  # Collect every 30 seconds

    def collect(self) -> TelemetrySnapshot:
        """
        Collect network metrics.

        Returns:
            TelemetrySnapshot with:
            - connections_total: Total active connections
            - connections_by_state: Connection state breakdown
            - connections_by_protocol: TCP/UDP breakdown
            - interfaces: Network interface stats
            - failed_connects: Failed connection attempts
        """
        try:
            data = {}

            # Get connection stats
            conn_stats = self._get_connection_stats()
            if conn_stats:
                data.update(conn_stats)

            # Get network interfaces
            interfaces = self._get_interface_stats()
            if interfaces:
                data["interfaces"] = interfaces

            # Get socket stats
            socket_stats = self._get_socket_stats()
            if socket_stats:
                data["socket_stats"] = socket_stats

            return TelemetrySnapshot(
                timestamp=datetime.now(),
                collector_name=self.name,
                data=data,
                metadata=self.get_metadata(),
            )

        except Exception as e:
            raise CollectionError(self.name, str(e))

    def _get_connection_stats(self) -> Optional[dict]:
        """Get connection statistics using ss"""
        try:
            # Get TCP states
            output = self._run_command("ss -tan state established 2>/dev/null | wc -l")
            established = int(output.strip()) if output else 0

            output = self._run_command("ss -tan state time-wait 2>/dev/null | wc -l")
            time_wait = int(output.strip()) if output else 0

            output = self._run_command("ss -tan state close-wait 2>/dev/null | wc -l")
            close_wait = int(output.strip()) if output else 0

            output = self._run_command("ss -tan state syn-sent 2>/dev/null | wc -l")
            syn_sent = int(output.strip()) if output else 0

            output = self._run_command("ss -tan state syn-recv 2>/dev/null | wc -l")
            syn_recv = int(output.strip()) if output else 0

            output = self._run_command("ss -tan state fin-wait-1 2>/dev/null | wc -l")
            fin_wait1 = int(output.strip()) if output else 0

            output = self._run_command("ss -tan state fin-wait-2 2>/dev/null | wc -l")
            fin_wait2 = int(output.strip()) if output else 0

            output = self._run_command("ss -tan 2>/dev/null | wc -l")
            total = int(output.strip()) if output else 0

            # Subtract header line
            total = max(0, total - 1)

            return {
                "connections_total": total,
                "connections_established": established - 1 if established > 0 else 0,
                "connections_time_wait": time_wait,
                "connections_close_wait": close_wait,
                "connections_syn_sent": syn_sent,
                "connections_syn_recv": syn_recv,
                "connections_fin_wait": fin_wait1 + fin_wait2,
                "tcp_connections": total,
            }

        except Exception:
            return None

    def _get_interface_stats(self) -> list[dict]:
        """Get network interface statistics"""
        interfaces = []

        try:
            output = self._run_command("ip -s link show 2>/dev/null")
            if not output:
                return interfaces

            current_iface = None
            for line in output.split("\n"):
                line = line.strip()

                # New interface
                if ":" in line and not line.startswith(" "):
                    parts = line.split(":")
                    if len(parts) >= 2:
                        current_iface = parts[1].strip()

                # RX stats
                elif "RX:" in line and current_iface:
                    match = re.search(r"bytes (\d+)", line)
                    if match:
                        rx_bytes = int(match.group(1))
                        for iface in interfaces:
                            if iface["name"] == current_iface:
                                iface["rx_bytes"] = rx_bytes
                                break
                        else:
                            interfaces.append(
                                {"name": current_iface, "rx_bytes": rx_bytes}
                            )

                # TX stats
                elif "TX:" in line and current_iface:
                    match = re.search(r"bytes (\d+)", line)
                    if match:
                        tx_bytes = int(match.group(1))
                        for iface in interfaces:
                            if iface["name"] == current_iface:
                                iface["tx_bytes"] = tx_bytes
                                break

        except Exception:
            pass

        # Get more details from /proc/net/dev
        try:
            net_dev = self._read_file("/proc/net/dev")
            if net_dev:
                for line in net_dev.split("\n")[2:]:  # Skip header lines
                    parts = line.split(":")
                    if len(parts) == 2:
                        iface = parts[0].strip()
                        stats = parts[1].split()
                        if len(stats) >= 10:
                            try:
                                rx_bytes = int(stats[0])
                                tx_bytes = int(stats[8])

                                # Update or add
                                found = False
                                for i in interfaces:
                                    if i["name"] == iface:
                                        i["rx_bytes"] = rx_bytes
                                        i["tx_bytes"] = tx_bytes
                                        found = True
                                        break

                                if not found and iface != "lo":
                                    interfaces.append(
                                        {
                                            "name": iface,
                                            "rx_bytes": rx_bytes,
                                            "tx_bytes": tx_bytes,
                                        }
                                    )
                            except (ValueError, IndexError):
                                continue

        except Exception:
            pass

        return interfaces

    def _get_socket_stats(self) -> Optional[dict]:
        """Get socket statistics from /proc/net/sockstat"""
        try:
            sockstat = self._read_file("/proc/net/sockstat")
            if not sockstat:
                return None

            result = {}
            for line in sockstat.split("\n"):
                if line.startswith("TCP:"):
                    parts = line.split()
                    if len(parts) >= 4:
                        try:
                            result["tcp_inuse"] = int(parts[2])
                            result["tcp_orphan"] = (
                                int(parts[4]) if len(parts) > 4 else 0
                            )
                            result["tcp_tw"] = int(parts[6]) if len(parts) > 6 else 0
                        except (ValueError, IndexError):
                            pass

                elif line.startswith("UDP:"):
                    parts = line.split()
                    if len(parts) >= 2:
                        try:
                            result["udp_inuse"] = int(parts[2])
                        except (ValueError, IndexError):
                            pass

                elif line.startswith("UDPLITE:"):
                    parts = line.split()
                    if len(parts) >= 2:
                        try:
                            result["udplite_inuse"] = int(parts[2])
                        except (ValueError, IndexError):
                            pass

            return result

        except Exception:
            return None


__all__ = ["NetworkCollector"]
