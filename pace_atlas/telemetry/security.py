"""
PACE Atlas — Security Monitor

Collects security events and authentication logs from Linux.

This collector monitors for potential security threats that external
monitors cannot detect since they don't have access to system logs.

Metrics Collected:
- Failed SSH login attempts (brute force detection)
- Failed sudo attempts
- Authentication failures
- Unusual login times
- New user additions
- Sudo commands executed

Author: PACE Atlas
Version: 0.1.0
"""

import re
from datetime import datetime, timedelta
from typing import Optional

from .base import TelemetryCollector, TelemetrySnapshot, CollectionError


class SecurityCollector(TelemetryCollector):
    """
    Collects security-related events from system logs.

    Monitors auth.log, secure, and journalctl for security events.
    """

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        self.ssh_threshold = config.get("ssh_threshold", 10) if config else 10
        self.ssh_window_minutes = config.get("ssh_window_minutes", 10) if config else 10

    @property
    def name(self) -> str:
        return "security"

    @property
    def interval(self) -> int:
        return 60  # Check every 60 seconds

    def collect(self) -> TelemetrySnapshot:
        """
        Collect security metrics.

        Returns:
            TelemetrySnapshot with:
            - ssh_failed_logins: Failed SSH attempts (recent)
            - ssh_failed_list: List of recent failed IPs/usernames
            - sudo_failed: Failed sudo attempts
            - auth_failures: Total authentication failures
            - new_users: New users added (if any)
            - unusual_events: Events at unusual times
        """
        try:
            data = {}

            # Get SSH failed login attempts
            ssh_data = self._get_ssh_failed_logins()
            if ssh_data:
                data["ssh_failed_logins"] = ssh_data["count"]
                data["ssh_failed_list"] = ssh_data.get("details", [])
                if ssh_data["count"] >= self.ssh_threshold:
                    data["ssh_brute_force_warning"] = True
                    data["ssh_attack_detected"] = (
                        ssh_data["count"] >= self.ssh_threshold
                    )

            # Get sudo failures
            sudo_failures = self._get_sudo_failures()
            if sudo_failures is not None:
                data["sudo_failed_count"] = sudo_failures

            # Get authentication failures
            auth_failures = self._get_auth_failures()
            if auth_failures is not None:
                data["auth_failures"] = auth_failures

            # Get last login info
            last_login = self._get_last_login()
            if last_login:
                data["last_login"] = last_login

            # Check for new users
            new_users = self._get_new_users()
            if new_users:
                data["new_users"] = new_users

            # Check for unusual access times
            unusual = self._check_unusual_access()
            if unusual:
                data["unusual_access"] = unusual

            return TelemetrySnapshot(
                timestamp=datetime.now(),
                collector_name=self.name,
                data=data,
                metadata=self.get_metadata(),
            )

        except Exception as e:
            raise CollectionError(self.name, str(e))

    def _get_ssh_failed_logins(self) -> Optional[dict]:
        """Get recent SSH failed login attempts"""
        try:
            window = self.ssh_window_minutes
            result = {"count": 0, "details": []}

            # Try journalctl first (systemd systems)
            output = self._run_command(
                f"journalctl -u sshd --since '{window} minutes ago' 2>/dev/null | "
                f"grep -i 'failed password' | tail -20"
            )

            if not output:
                # Fall back to auth.log
                output = self._run_command(
                    f"grep -i 'failed password' /var/log/auth.log 2>/dev/null | "
                    f"tail -20"
                )

            if not output:
                # Try secure log (RHEL/CentOS)
                output = self._run_command(
                    f"grep -i 'failed password' /var/log/secure 2>/dev/null | tail -20"
                )

            if not output:
                return result

            # Parse the output
            for line in output.split("\n"):
                if not line.strip():
                    continue

                # Extract IP if possible
                ip = None
                user = None

                # Common patterns:
                # "Failed password for root from 192.168.1.100 port 22"
                # "Failed password for invalid user admin from 192.168.1.100 port 22"

                ip_match = re.search(r"from (\d+\.\d+\.\d+\.\d+)", line)
                if ip_match:
                    ip = ip_match.group(1)

                user_match = re.search(r"for (?:invalid user )?(\w+)", line)
                if user_match:
                    user = user_match.group(1)

                result["count"] += 1
                if ip or user:
                    result["details"].append(
                        {
                            "ip": ip or "unknown",
                            "user": user or "unknown",
                            "timestamp": line[:15] if len(line) > 15 else line,
                        }
                    )

            return result

        except Exception:
            return {"count": 0, "details": []}

    def _get_sudo_failures(self) -> Optional[int]:
        """Get sudo failed attempts count"""
        try:
            window = 60  # Last 60 minutes

            output = self._run_command(
                f"journalctl --since '{window} minutes ago' 2>/dev/null | "
                f"grep -i 'sudo.*authentication failure' | wc -l"
            )

            if not output:
                output = self._run_command(
                    f"grep -i 'authentication failure' /var/log/auth.log 2>/dev/null | "
                    f"tail -10 | wc -l"
                )

            if output:
                return int(output.strip())
            return 0

        except Exception:
            return None

    def _get_auth_failures(self) -> Optional[int]:
        """Get total authentication failures"""
        try:
            output = self._run_command(
                "journalctl -p err --since '1 hour ago' 2>/dev/null | "
                "grep -i 'authentication failure' | wc -l"
            )

            if not output:
                output = self._run_command(
                    "grep -i 'authentication failure' /var/log/auth.log 2>/dev/null | "
                    "tail -10 | wc -l"
                )

            if output:
                return int(output.strip())
            return 0

        except Exception:
            return None

    def _get_last_login(self) -> Optional[dict]:
        """Get last login information"""
        try:
            output = self._run_command("last -1 -n 2")
            if not output:
                return None

            lines = output.strip().split("\n")
            for line in lines:
                if "still logged in" in line or "boot" in line:
                    continue
                parts = line.split()
                if len(parts) >= 10:
                    return {
                        "user": parts[0],
                        "terminal": parts[1],
                        "ip": parts[2] if "(" in parts[2] else "local",
                        "time": " ".join(parts[3:7]),
                    }

        except Exception:
            pass

        return None

    def _get_new_users(self) -> list:
        """Check for recently added users"""
        try:
            # Check for users added in last 24 hours
            output = self._run_command(
                "grep -i 'new user' /var/log/auth.log 2>/dev/null | tail -5"
            )

            if not output:
                output = self._run_command(
                    "journalctl --since '24 hours ago' 2>/dev/null | "
                    "grep -i 'new user' | tail -5"
                )

            users = []
            for line in output.split("\n"):
                if line.strip():
                    # Extract username
                    match = re.search(r"new user:.*?(\w+)", line)
                    if match:
                        users.append(match.group(1))

            return users

        except Exception:
            return []

    def _check_unusual_access(self) -> Optional[dict]:
        """Check for access at unusual hours"""
        try:
            current_hour = datetime.now().hour

            # Consider unusual if between 1am and 5am
            if 1 <= current_hour <= 5:
                # Check for logins in this time window
                output = self._run_command(
                    "journalctl --since '1 hour ago' 2>/dev/null | "
                    "grep -i 'session opened' | tail -5"
                )

                if output and output.strip():
                    return {
                        "detected": True,
                        "reason": f"Login detected at {current_hour}:00 (unusual hour)",
                        "sessions": output.strip().split("\n"),
                    }

            return None

        except Exception:
            return None


__all__ = ["SecurityCollector"]
