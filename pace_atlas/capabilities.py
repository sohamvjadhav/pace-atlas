"""
PACE Atlas — Advanced Capabilities Module

This module implements all the expanded capabilities:
- Root Cause Analysis
- Security Intelligence
- Cost Optimization
- Predictive Analysis
- Interactive Q&A
- Forecasting

Version: 1.0.0

Author: PACE Atlas
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional
import json


# =============================================================================
# DATA STRUCTURES
# =============================================================================


@dataclass
class AnalysisResult:
    """Result from any analysis type."""

    result_type: str  # "alert", "warning", "insight", "forecast", "rca", "qa"
    severity: str  # "critical", "warning", "info"
    title: str
    body: str
    recommendations: list[str] = None
    evidence: dict = None

    def __post_init__(self):
        if self.recommendations is None:
            self.recommendations = []


@dataclass
class Prediction:
    """Predictive analysis result."""

    metric: str
    current_value: float
    predicted_value: float
    timeline: str  # e.g., "4 days until 95%"
    confidence: str  # "high", "medium", "low"
    recommendation: str


# =============================================================================
# HISTORY TRACKING
# =============================================================================


class HistoryTracker:
    """
    Track historical data for pattern recognition and predictions.
    """

    def __init__(self, config_dir: str):
        self.config_dir = config_dir
        self.history_file = f"{config_dir}/history.json"
        self.max_history_days = 30
        self.history = self._load_history()

    def _load_history(self) -> dict:
        """Load history from disk."""
        try:
            with open(self.history_file, "r") as f:
                return json.load(f)
        except:
            return {}

    def save(self):
        """Save history to disk."""
        try:
            with open(self.history_file, "w") as f:
                json.dump(self.history, f)
        except:
            pass

    def record(self, metric: str, value: float, timestamp: datetime = None):
        """Record a metric value."""
        if timestamp is None:
            timestamp = datetime.now()

        if metric not in self.history:
            self.history[metric] = []

        # Add new reading
        self.history[metric].append(
            {"timestamp": timestamp.isoformat(), "value": value}
        )

        # Clean old data
        cutoff = (datetime.now() - timedelta(days=self.max_history_days)).isoformat()
        self.history[metric] = [
            h for h in self.history[metric] if h["timestamp"] > cutoff
        ]

        self.save()

    def get_trend(self, metric: str) -> Optional[str]:
        """Get trend for a metric."""
        if metric not in self.history or len(self.history[metric]) < 3:
            return None

        recent = self.history[metric][-5:]
        values = [h["value"] for h in recent]

        # Simple trend detection
        if all(values[i] < values[i + 1] for i in range(len(values) - 1)):
            return "increasing"
        elif all(values[i] > values[i + 1] for i in range(len(values) - 1)):
            return "decreasing"
        else:
            return "stable"

    def get_rate(self, metric: str) -> Optional[float]:
        """Get rate of change per hour."""
        if metric not in self.history or len(self.history[metric]) < 2:
            return None

        data = self.history[metric]
        if len(data) < 2:
            return 0

        first = data[0]
        last = data[-1]

        first_time = datetime.fromisoformat(first["timestamp"])
        last_time = datetime.fromisoformat(last["timestamp"])

        hours = (last_time - first_time).total_seconds() / 3600
        if hours <= 0:
            return None

        value_change = last["value"] - first["value"]
        return value_change / hours

    def get_projection(self, metric: str, threshold: float) -> Optional[Prediction]:
        """Project when a threshold will be reached."""
        if metric not in self.history:
            return None

        recent = self.history[metric][-10:]
        if len(recent) < 3:
            return None

        # Calculate simple linear projection
        values = [h["value"] for h in recent]
        avg_rate = (values[-1] - values[0]) / len(values)

        if avg_rate <= 0:
            return None  # Not increasing

        remaining = threshold - values[-1]
        if remaining <= 0:
            return Prediction(
                metric=metric,
                current_value=values[-1],
                predicted_value=threshold,
                timeline="Already exceeded",
                confidence="high",
                recommendation=f"Immediate action required",
            )

        hours_remaining = remaining / avg_rate if avg_rate > 0 else float("inf")

        if hours_remaining < 1:
            timeline = f"{int(hours_remaining * 60)} minutes until {threshold}%"
        elif hours_remaining < 24:
            timeline = f"{int(hours_remaining)} hours until {threshold}%"
        else:
            days = hours_remaining / 24
            timeline = f"{int(days)} days until {threshold}%"

        return Prediction(
            metric=metric,
            current_value=values[-1],
            predicted_value=threshold,
            timeline=timeline,
            confidence="medium" if hours_remaining > 24 else "high",
            recommendation=f"Plan to address within {timeline}",
        )


# =============================================================================
# ROOT CAUSE ANALYSIS ENGINE
# =============================================================================


class RootCauseAnalyzer:
    """
    Analyzes incidents to find root cause using LLM knowledge.
    """

    def __init__(self):
        pass

    def analyze(
        self, incident: str, telemetry_before: dict, telemetry_after: dict, logs: str
    ) -> AnalysisResult:
        """
        Perform root cause analysis.

        This would call the LLM with the RCA prompt.
        For now, returns a template.
        """
        # This would integrate with the LLM
        return AnalysisResult(
            result_type="rca",
            severity="info",
            title=f"Root Cause Analysis: {incident}",
            body="Use prompts.atlas_complete.build_rca_prompt() with LLM",
            recommendations=[
                "Check logs around incident time",
                "Review recent changes",
                "Look for correlated failures",
            ],
        )


# =============================================================================
# SECURITY INTELLIGENCE ENGINE
# =============================================================================


class SecurityAnalyzer:
    """
    Analyzes security events using pattern recognition and LLM knowledge.
    """

    # Known attack patterns
    ATTACK_PATTERNS = {
        "ssh_brute_force": {
            "threshold": 10,
            "window_minutes": 10,
            "severity": "critical",
            "description": "Multiple SSH failed attempts",
        },
        "credential_stuffing": {
            "threshold": 20,
            "window_minutes": 30,
            "severity": "critical",
            "description": "Failed attempts across multiple accounts",
        },
        "port_scan": {
            "threshold": 50,
            "window_minutes": 5,
            "severity": "medium",
            "description": "Many connection attempts to different ports",
        },
        "ddos": {
            "threshold": 1000,
            "window_minutes": 1,
            "severity": "critical",
            "description": "Traffic spike from many sources",
        },
    }

    def __init__(self):
        pass

    def analyze_security_event(
        self, security_data: dict, network_data: dict, logs: str
    ) -> list[AnalysisResult]:
        """
        Analyze security events and return threats/insights.
        """
        results = []

        # Check SSH failures
        ssh_failures = security_data.get("ssh_failed_logins", 0)
        if ssh_failures >= 10:
            results.append(
                AnalysisResult(
                    result_type="alert",
                    severity="critical",
                    title="SSH Brute Force Detected",
                    body=f"{ssh_failures} failed SSH login attempts in last 10 minutes. "
                    f"This is a credential stuffing attack. "
                    f"Check logs for successful login from any of these IPs.",
                    recommendations=[
                        "Check: grep 'Accepted' /var/log/auth.log",
                        "Consider: fail2ban or iptables block",
                        "Check: whether any account was compromised",
                    ],
                    evidence={"ssh_failures": ssh_failures},
                )
            )

        # Check for successful login from new IP
        # (would require historical data)

        # Check for unusual network patterns
        if network_data:
            conns = network_data.get("connections_total", 0)
            if conns > 10000:
                results.append(
                    AnalysisResult(
                        result_type="insight",
                        severity="warning",
                        title="High Connection Count",
                        body=f"Server has {conns} active connections. "
                        f"Normal range is typically 500-2000. "
                        f"This could indicate a DoS or compromised service.",
                        recommendations=[
                            "Check: ss -s for connection breakdown",
                            "Check: which process is accepting connections",
                        ],
                    )
                )

        # Check logs for security events
        if logs:
            if "authentication failure" in logs.lower():
                results.append(
                    AnalysisResult(
                        result_type="alert",
                        severity="warning",
                        title="Authentication Failures in Logs",
                        body="Found authentication failures in system logs. "
                        "Could be user forgetting password or attempted intrusion.",
                        recommendations=[
                            "Review: /var/log/auth.log for details",
                            "Check: which accounts are affected",
                        ],
                    )
                )

        # If new user added
        new_users = security_data.get("new_users", [])
        if new_users:
            results.append(
                AnalysisResult(
                    result_type="insight",
                    severity="info",
                    title="New User Account(s)",
                    body=f"New user account(s) created: {', '.join(new_users)}. "
                    "Verify this was intentional.",
                    recommendations=[
                        "Confirm: this is expected",
                        "Review: user permissions",
                    ],
                )
            )

        return results


# =============================================================================
# COST OPTIMIZATION ENGINE
# =============================================================================


class CostAnalyzer:
    """
    Analyzes resources for cost optimization opportunities.
    """

    def __init__(self):
        self.baseline_file = None  # Would track spending

    def analyze_cost(
        self, telemetry: dict, cloud_data: dict, history: HistoryTracker
    ) -> list[AnalysisResult]:
        """Analyze for cost optimization opportunities."""
        results = []

        # Check CPU utilization
        system_data = telemetry.get("system", {})
        cpu = system_data.get("cpu_percent", 0)

        if cpu < 10:
            results.append(
                AnalysisResult(
                    result_type="insight",
                    severity="info",
                    title="Idle Instance",
                    body=f"CPU utilization at {cpu}% — this instance appears idle. "
                    f"Consider: t3.micro instead of t3.large, or terminate if not needed.",
                    recommendations=[
                        "If testing: use spot instances",
                        "If dev: schedule shutdown at night",
                        "If prod: investigate why traffic dropped",
                    ],
                )
            )

        # Check memory utilization
        memory_data = telemetry.get("memory", {})
        mem = memory_data.get("usage_percent", 0)

        if mem < 30:
            results.append(
                AnalysisResult(
                    result_type="insight",
                    severity="info",
                    title="Over-provisioned Memory",
                    body=f"Memory at {mem}% — using less than 1/3 of available. "
                    "Could downsize to smaller instance type.",
                    recommendations=[
                        "Check: typical memory usage patterns",
                        "Consider: smaller instance with same vCPU",
                    ],
                )
            )

        # Check disk
        disk_data = telemetry.get("disk", {})
        disk_usage = disk_data.get("usage_percent", 0)

        if disk_usage > 85:
            results.append(
                AnalysisResult(
                    result_type="insight",
                    severity="warning",
                    title="High Disk Usage",
                    body=f"Disk at {disk_usage}%. High usage can impact performance "
                    "and increase costs (some providers charge for high usage).",
                    recommendations=[
                        "Run: du -sh /* | sort -h to find large dirs",
                        "Check: old logs that can be archived",
                        "Consider: lifecycle policies for S3 etc",
                    ],
                )
            )

        # Check for unused volumes (would require cloud API)
        if cloud_data:
            # Would check for unattached EBS volumes, unused EIPs, etc.
            pass

        # Check for old snapshots
        # Check for reserved instance opportunities

        return results


# =============================================================================
# PREDICTIVE ANALYSIS ENGINE
# =============================================================================


class PredictiveAnalyzer:
    """
    Predicts future issues based on trends.
    """

    def __init__(self, history: HistoryTracker):
        self.history = history

    def analyze_trends(self, telemetry: dict) -> list[AnalysisResult]:
        """Analyze metrics for predictive insights."""
        results = []

        # Check disk growth trend
        disk_data = telemetry.get("disk", {})
        if disk_data.get("usage_percent", 0) > 50:
            proj = self.history.get_projection("disk_usage", 95)
            if proj:
                results.append(
                    AnalysisResult(
                        result_type="forecast",
                        severity="warning" if "hours" in proj.timeline else "info",
                        title=f"Disk: {proj.timeline}",
                        body=f"Current: {proj.current_value:.1f}%, threshold: 95%. "
                        f"At current rate, disk will reach 95% in {proj.timeline.split(' until ')[0] if 'until' in proj.timeline else proj.timeline}.",
                        recommendations=[proj.recommendation],
                    )
                )

        # Check memory growth trend
        memory_data = telemetry.get("memory", {})
        if memory_data.get("usage_percent", 0) > 50:
            proj = self.history.get_projection("memory_usage", 95)
            if proj:
                results.append(
                    AnalysisResult(
                        result_type="forecast",
                        severity="warning" if "hours" in proj.timeline else "info",
                        title=f"Memory: {proj.timeline}",
                        body=f"Current: {proj.current_value:.1f}%, threshold: 95%.",
                        recommendations=[proj.recommendation],
                    )
                )

        # Check CPU pattern (if consistently high)
        cpu = telemetry.get("system", {}).get("cpu_percent", 0)
        if cpu > 80:
            trend = self.history.get_trend("cpu_percent")
            if trend == "increasing":
                results.append(
                    AnalysisResult(
                        result_type="forecast",
                        severity="warning",
                        title="CPU Trending Upward",
                        body=f"CPU at {cpu}% and climbing. This typically indicates "
                        "either increasing load or a runaway process.",
                        recommendations=[
                            "Check: which process started recently",
                            "Investigate: application logs for errors",
                        ],
                    )
                )

        return results


# =============================================================================
# INTERACTIVE Q&A ENGINE
# =============================================================================


class InteractiveQA:
    """
    Handles user questions about infrastructure.
    """

    def __init__(self):
        pass

    def answer(self, question: str, telemetry: dict, logs: str) -> AnalysisResult:
        """
        Answer a user question.

        This would call the LLM with the Q&A prompt.
        """
        # This would integrate with the LLM
        return AnalysisResult(
            result_type="qa",
            severity="info",
            title="Answer",
            body=f"Question: {question}\n\n"
            f"Use prompts.atlas_complete.build_qa_prompt() with LLM",
            recommendations=[],
        )


# =============================================================================
# ORCHESTRATOR - Combine All Capabilities
# =============================================================================


class AtlasCapabilities:
    """
    Main orchestrator for all Atlas advanced capabilities.
    """

    def __init__(self, config_dir: str):
        self.history = HistoryTracker(config_dir)
        self.rca = RootCauseAnalyzer()
        self.security = SecurityAnalyzer()
        self.cost = CostAnalyzer()
        self.predictive = PredictiveAnalyzer(self.history)
        self.qa = InteractiveQA()

    def run_full_analysis(
        self, telemetry: dict, logs: str = "", feedback_context: dict = None
    ) -> list[AnalysisResult]:
        """
        Run comprehensive analysis combining all capabilities.
        """
        results = []

        # Record telemetry for history
        for key, value in [
            ("cpu", telemetry.get("system", {}).get("cpu_percent")),
            ("memory", telemetry.get("memory", {}).get("usage_percent")),
            ("disk", telemetry.get("disk", {}).get("usage_percent")),
        ]:
            if value is not None:
                self.history.record(key, value)

        # Run security analysis
        security_results = self.security.analyze_security_event(
            telemetry.get("security", {}), telemetry.get("network", {}), logs
        )
        results.extend(security_results)

        # Run cost analysis
        cost_results = self.cost.analyze_cost(
            telemetry, telemetry.get("cloud", {}), self.history
        )
        results.extend(cost_results)

        # Run predictive analysis
        predictive_results = self.predictive.analyze_trends(telemetry)
        results.extend(predictive_results)

        return results

    def answer_question(
        self, question: str, telemetry: dict, logs: str
    ) -> AnalysisResult:
        """Answer a user question."""
        return self.qa.answer(question, telemetry, logs)

    def perform_rca(
        self, incident: str, before: dict, after: dict, logs: str
    ) -> AnalysisResult:
        """Perform root cause analysis."""
        return self.rca.analyze(incident, before, after, logs)


__all__ = [
    "AnalysisResult",
    "Prediction",
    "HistoryTracker",
    "RootCauseAnalyzer",
    "SecurityAnalyzer",
    "CostAnalyzer",
    "PredictiveAnalyzer",
    "InteractiveQA",
    "AtlasCapabilities",
]
