"""
PACE Atlas — Alert Engine Module

The Alert Engine is the decision layer that determines whether observed
telemetry warrants user notification. It has two passes:

1. Hard Rules Pass: Non-negotiable alert conditions (always alert)
2. LLM Decision Pass: Intelligent decision using the LLM

Author: PACE Atlas
Version: 0.1.0
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class AlertDecision:
    """
    Represents an alert decision from the engine.

    Attributes:
        should_alert: Whether to send alert to user
        reason: Explanation for the decision
        alert_type: Type of alert (hard_rule, llm_decision, etc.)
        severity: Severity level (critical, warning, info)
    """

    should_alert: bool
    reason: str
    alert_type: str  # "hard_rule", "llm_decision"
    severity: str = "info"  # "critical", "warning", "info"
    details: Optional[dict] = None


class HardRules:
    """
    Non-negotiable alert conditions.

    These rules trigger an alert regardless of what the LLM decides.
    They are the safety net that ensures critical events never slip through.

    Hard Rules:
    - Disk >= 95%
    - Memory >= 95%
    - CPU >= 95% sustained > 5 minutes
    - Service in failed state
    - SSH brute force (10+ failed in 10 min)
    - OOM killer triggered
    - Billing spike > 50%
    """

    def __init__(self, config: dict | None = None):
        self.config = config or {}

        # Thresholds (configurable)
        self.disk_threshold = self.config.get("disk_threshold", 95)
        self.memory_threshold = self.config.get("memory_threshold", 95)
        self.cpu_threshold = self.config.get("cpu_threshold", 95)
        self.cpu_duration = self.config.get("cpu_duration_minutes", 5)
        self.ssh_threshold = self.config.get("ssh_threshold", 10)
        self.ssh_window = self.config.get("ssh_window_minutes", 10)
        self.billing_threshold = self.config.get("billing_threshold", 50)  # percent

    def check(self, telemetry_data: dict) -> Optional[AlertDecision]:
        """
        Check all hard rules against telemetry data.

        Args:
            telemetry_data: Dict of telemetry snapshots from collectors

        Returns:
            AlertDecision if any hard rule triggered, None otherwise
        """
        # Check disk usage
        disk_result = self._check_disk(telemetry_data)
        if disk_result:
            return disk_result

        # Check memory usage
        memory_result = self._check_memory(telemetry_data)
        if memory_result:
            return memory_result

        # Check CPU (sustained high)
        cpu_result = self._check_cpu(telemetry_data)
        if cpu_result:
            return cpu_result

        # Check failed services
        service_result = self._check_services(telemetry_data)
        if service_result:
            return service_result

        # Check SSH brute force
        ssh_result = self._check_ssh(telemetry_data)
        if ssh_result:
            return ssh_result

        # Check OOM events
        oom_result = self._check_oom(telemetry_data)
        if oom_result:
            return oom_result

        # Check billing spike
        billing_result = self._check_billing(telemetry_data)
        if billing_result:
            return billing_result

        # No hard rules triggered
        return None

    def _check_disk(self, data: dict) -> Optional[AlertDecision]:
        """Check disk usage threshold."""
        # Check disk collector data
        disk_data = data.get("disk", {})
        mount_points = disk_data.get("mount_points", [])

        for mount in mount_points:
            usage = mount.get("usage_percent", 0)
            if usage >= self.disk_threshold:
                mount_point = mount.get("mount", "unknown")
                return AlertDecision(
                    should_alert=True,
                    reason=f"Disk at {usage}% on {mount_point} (threshold: {self.disk_threshold}%)",
                    alert_type="hard_rule",
                    severity="critical",
                    details={"mount": mount_point, "usage": usage},
                )

        return None

    def _check_memory(self, data: dict) -> Optional[AlertDecision]:
        """Check memory usage threshold."""
        memory_data = data.get("memory", {})
        usage_percent = memory_data.get("usage_percent", 0)

        if usage_percent >= self.memory_threshold:
            return AlertDecision(
                should_alert=True,
                reason=f"Memory at {usage_percent}% (threshold: {self.memory_threshold}%)",
                alert_type="hard_rule",
                severity="critical",
                details={"usage_percent": usage_percent},
            )

        # Also check for OOM events in memory data
        if memory_data.get("oom_events", 0) > 0:
            return AlertDecision(
                should_alert=True,
                reason=f"OOM killer triggered ({memory_data.get('oom_events')} events)",
                alert_type="hard_rule",
                severity="critical",
                details={"oom_events": memory_data.get("oom_events")},
            )

        return None

    def _check_cpu(self, data: dict) -> Optional[AlertDecision]:
        """Check CPU sustained high usage."""
        system_data = data.get("system", {})
        cpu_percent = system_data.get("cpu_percent", 0)

        # If CPU is very high, check if sustained
        if cpu_percent >= self.cpu_threshold:
            # Note: For full implementation, we'd track history
            # For now, any reading at threshold triggers warning
            return AlertDecision(
                should_alert=True,
                reason=f"CPU at {cpu_percent}% (threshold: {self.cpu_threshold}%)",
                alert_type="hard_rule",
                severity="warning",
                details={"cpu_percent": cpu_percent},
            )

        return None

    def _check_services(self, data: dict) -> Optional[AlertDecision]:
        """Check for failed systemd services."""
        process_data = data.get("process", {})
        failed_services = process_data.get("failed_services", [])

        if failed_services and len(failed_services) > 0:
            return AlertDecision(
                should_alert=True,
                reason=f"{len(failed_services)} service(s) in failed state: {', '.join(failed_services[:3])}",
                alert_type="hard_rule",
                severity="critical",
                details={"failed_services": failed_services},
            )

        return None

    def _check_ssh(self, data: dict) -> Optional[AlertDecision]:
        """Check for SSH brute force attempts."""
        security_data = data.get("security", {})
        ssh_failed = security_data.get("ssh_failed_logins", 0)

        if ssh_failed >= self.ssh_threshold:
            return AlertDecision(
                should_alert=True,
                reason=f"SSH brute force detected: {ssh_failed} failed attempts in {self.ssh_window} minutes",
                alert_type="hard_rule",
                severity="critical",
                details={
                    "failed_attempts": ssh_failed,
                    "window_minutes": self.ssh_window,
                },
            )

        return None

    def _check_oom(self, data: dict) -> Optional[AlertDecision]:
        """Check for OOM killer events."""
        # Already handled in memory check, but could add explicit check
        memory_data = data.get("memory", {})
        if memory_data.get("oom_events", 0) > 0:
            return AlertDecision(
                should_alert=True,
                reason=f"OOM killer activated (memory pressure critical)",
                alert_type="hard_rule",
                severity="critical",
            )

        return None

    def _check_billing(self, data: dict) -> Optional[AlertDecision]:
        """Check for billing spike."""
        cloud_data = data.get("cloud", {})
        billing = cloud_data.get("billing", {})

        if billing:
            daily_cost = billing.get("daily_cost", 0)
            baseline = billing.get("baseline_daily", 0)

            if baseline > 0 and daily_cost > 0:
                increase = ((daily_cost - baseline) / baseline) * 100
                if increase >= self.billing_threshold:
                    return AlertDecision(
                        should_alert=True,
                        reason=f"Billing spike: {increase:.0f}% increase (${daily_cost} vs ${baseline} baseline)",
                        alert_type="hard_rule",
                        severity="warning",
                        details={
                            "daily_cost": daily_cost,
                            "baseline": baseline,
                            "increase_percent": increase,
                        },
                    )

        return None


class AlertEngine:
    """
    Main alert engine that orchestrates hard rules and LLM decision.

    Flow:
    1. Check hard rules first (critical events always alert)
    2. If no hard rule, ask LLM for decision
    3. Return final decision with reason
    """

    def __init__(self, config: dict | None = None):
        self.config = config or {}
        self.hard_rules = HardRules(self.config.get("hard_rules", {}))
        self.llm_client = None  # Set by set_llm_client()
        self.feedback = None  # Set by set_feedback()

    def set_llm_client(self, client, model: str = None, max_tokens: int = 500) -> None:
        """Set the LLM client for intelligent decisions."""
        self.llm_client = client
        self.llm_model = model or "llama-3.3-70b-versatile"
        self.llm_max_tokens = max_tokens

    def set_feedback(self, feedback_system) -> None:
        """Set the feedback learning system."""
        self.feedback = feedback_system

    def decide(
        self, telemetry_snapshots: list, context: dict | None = None
    ) -> AlertDecision:
        """
        Decide whether to alert based on telemetry.

        Args:
            telemetry_snapshots: List of TelemetrySnapshot from collectors
            context: Optional context (feedback history, server info)

        Returns:
            AlertDecision with should_alert and reason
        """
        # Convert snapshots to dict for easier access
        telemetry_data = {}
        for snapshot in telemetry_snapshots:
            telemetry_data[snapshot.collector_name] = snapshot.data

        # Step 1: Check hard rules first (always alert on critical)
        hard_rule_result = self.hard_rules.check(telemetry_data)
        if hard_rule_result:
            return hard_rule_result

        # Step 2: If no hard rule, ask LLM (if available)
        if self.llm_client:
            return self._llm_decide(telemetry_data, context or {})

        # No LLM client - default to no alert (silent)
        return AlertDecision(
            should_alert=False,
            reason="No hard rules triggered, no LLM configured",
            alert_type="no_decision",
        )

    def _llm_decide(self, telemetry_data: dict, context: dict) -> AlertDecision:
        """Ask LLM to analyze telemetry using its knowledge."""
        try:
            # Build prompt with telemetry data - now with expertise!
            prompt = self._build_decision_prompt(telemetry_data, context)

            # Get LLM response (OpenAI-style client)
            response = self.llm_client.chat.completions.create(
                model=getattr(self, "llm_model", "llama-3.3-70b-versatile"),
                messages=[{"role": "user", "content": prompt}],
                max_tokens=getattr(self, "llm_max_tokens", 500),
            )
            llm_response = response.choices[0].message.content

            # Parse response - now it comes with personality, insight, recommendations
            return self._parse_llm_response(llm_response)

        except Exception as e:
            # If LLM fails, default to silent (safe)
            return AlertDecision(
                should_alert=False,
                reason=f"LLM analysis failed: {str(e)[:50]}",
                alert_type="llm_error",
            )

    def _build_decision_prompt(self, telemetry_data: dict, context: dict) -> str:
        """Build prompt for LLM decision."""
        # Import the knowledge-powered prompts
        try:
            from prompts.atlas_knowledge import build_quick_prompt

            # Format telemetry data for the prompt
            telemetry_str = self._format_telemetry(telemetry_data)

            # Get feedback context
            feedback = context.get("feedback", "none")
            if isinstance(feedback, dict):
                feedback = feedback.get("recent_feedback", "none")

            # Get server name from context
            server_name = context.get("server_name", "server")

            # Use the knowledge-powered prompt
            return build_quick_prompt(server_name, telemetry_str, feedback)

        except ImportError:
            # Fallback to old format if prompts not available
            return self._build_simple_prompt(telemetry_data, context)

    def _build_simple_prompt(self, telemetry_data: dict, context: dict) -> str:
        """Fallback simple prompt if knowledge prompts not available."""
        # Format telemetry as readable string
        lines = ["Current Server Telemetry:"]

        for collector, data in telemetry_data.items():
            lines.append(f"\n{collector.upper()}:")

            # Extract key metrics
            if collector == "system":
                cpu = data.get("cpu_percent", "N/A")
                load = data.get("load_avg", {})
                lines.append(f"  CPU: {cpu}%")
                if load:
                    lines.append(
                        f"  Load: {load.get('1min', 'N/A')} (1m), {load.get('5min', 'N/A')} (5m)"
                    )

            elif collector == "memory":
                mem = data.get("usage_percent", "N/A")
                lines.append(f"  Memory: {mem}%")

            elif collector == "disk":
                usage = data.get("usage_percent", "N/A")
                lines.append(f"  Disk: {usage}%")

            elif collector == "process":
                total = data.get("total_processes", 0)
                failed = data.get("failed_services_count", 0)
                lines.append(f"  Processes: {total} total, {failed} failed services")

            elif collector == "security":
                ssh_fail = data.get("ssh_failed_logins", 0)
                lines.append(f"  SSH failures: {ssh_fail}")

        # Add feedback context
        if context.get("feedback"):
            lines.append(f"\nUser Feedback Context: {context['feedback']}")

        lines.append("\nShould we alert the user?")
        lines.append("Reply: ALERT: [subject] - [reason]")
        lines.append("  or: SILENT: [reason]")

        return "\n".join(lines)

    def _format_telemetry(self, telemetry_data: dict) -> str:
        """Format telemetry for knowledge-powered LLM analysis."""
        lines = []

        for collector, data in telemetry_data.items():
            lines.append(f"\n{collector.upper()}:")

            if collector == "system":
                cpu = data.get("cpu_percent", "N/A")
                load = data.get("load_avg", {})
                uptime = data.get("uptime_formatted", "N/A")
                lines.append(f"  CPU: {cpu}%")
                if load:
                    lines.append(
                        f"  Load: {load.get('1min', 'N/A')} (1m), {load.get('5min', 'N/A')} (5m)"
                    )
                lines.append(f"  Uptime: {uptime}")

            elif collector == "memory":
                mem = data.get("usage_percent", "N/A")
                swap = data.get("swap_percent", 0)
                lines.append(f"  Memory: {mem}%")
                if swap > 0:
                    lines.append(f"  Swap: {swap}%")

            elif collector == "disk":
                usage = data.get("usage_percent", "N/A")
                mounts = data.get("mount_points", [])
                lines.append(f"  Disk: {usage}%")
                for m in mounts[:2]:  # Top 2 mounts
                    lines.append(f"    {m.get('mount')}: {m.get('usage_percent')}%")

            elif collector == "network":
                total = data.get("connections_total", 0)
                established = data.get("connections_established", 0)
                lines.append(f"  Connections: {total} total, {established} established")

            elif collector == "process":
                total = data.get("total_processes", 0)
                running = data.get("running_processes", 0)
                failed = data.get("failed_services_count", 0)
                lines.append(f"  Processes: {total} total, {running} running")
                if failed:
                    lines.append(f"  ⚠️ Failed services: {failed}")

            elif collector == "security":
                ssh_fail = data.get("ssh_failed_logins", 0)
                if ssh_fail > 0:
                    lines.append(f"  ⚠️ SSH failures: {ssh_fail}")
                else:
                    lines.append(f"  SSH: Clean")

            elif collector == "logs":
                errors = data.get("error_count", 0)
                if errors > 0:
                    lines.append(f"  ⚠️ Errors: {errors}")

            elif collector == "cloud":
                provider = data.get("provider", "unknown")
                if provider != "unknown":
                    lines.append(f"  Provider: {provider}")

        return "\n".join(lines)

    def _parse_llm_response(self, response: str) -> AlertDecision:
        """Parse LLM response to extract decision."""
        response_lower = response.strip().lower()
        response_upper = response.strip().upper()

        # Check for "all quiet" FIRST - this means no alert
        if any(
            x in response_lower
            for x in [
                "all quiet",
                "all good",
                "everything quiet",
                "no issues",
                "✅ all",
            ]
        ):
            reason = response[:150] if len(response) > 150 else response
            return AlertDecision(
                should_alert=False,
                reason=f"All quiet: {reason[:100]}",
                alert_type="llm_decision",
            )

        # Check for alert indicators
        if any(x in response_lower for x in ["alert:", "warning:", "critical:", "🔴"]):
            reason = response[:200] if len(response) > 200 else response
            return AlertDecision(
                should_alert=True,
                reason=reason,
                alert_type="llm_decision",
                severity="warning",
            )

        # Check for minor indicators (insights, not alerts)
        if any(x in response_lower for x in ["🟡", "💡", "insight"]):
            # Insights are not alerts - just informational
            return AlertDecision(
                should_alert=False,
                reason=f"Insight (no alert): {response[:100]}",
                alert_type="llm_insight",
            )

        # Default to silent
        return AlertDecision(
            should_alert=False,
            reason=f"Default silent - response: {response[:80]}",
            alert_type="llm_default",
        )


__all__ = ["AlertEngine", "HardRules", "AlertDecision"]
