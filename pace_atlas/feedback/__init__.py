"""
PACE Atlas — Feedback Learning System

The feedback learning system enables PACE Atlas to learn from user feedback
and improve alert relevance over time.

Key Features:
- Record user feedback on alerts
- Track alert types and their usefulness
- Suppress muted alert types
- Adjust thresholds based on feedback
- Build user preference model

Author: PACE Atlas
Version: 0.1.0
"""

import json
import os
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional


@dataclass
class FeedbackEntry:
    """Represents a single feedback entry from the user."""

    timestamp: datetime
    alert_type: str
    feedback: str  # "useful", "not_needed", "ignore", "too_frequent", "thanks"
    alert_content: str  # What the alert said
    user_comment: Optional[str] = None


@dataclass
class AlertTypeStats:
    """Statistics for a specific alert type."""

    total_alerts: int = 0
    useful_count: int = 0
    not_needed_count: int = 0
    ignored_count: int = 0
    last_alert: Optional[datetime] = None
    suppression_until: Optional[datetime] = None


class FeedbackLearning:
    """
    Feedback learning system for PACE Atlas.

    Records user feedback and uses it to improve alert decisions.
    """

    def __init__(self, config_dir: str | None = None):
        """
        Initialize the feedback learning system.

        Args:
            config_dir: Directory to store feedback data (default: ~/.pace/)
        """
        if config_dir:
            self.config_dir = Path(config_dir)
        else:
            self.config_dir = Path(os.path.expanduser("~/.pace"))

        # Ensure directory exists
        self.config_dir.mkdir(parents=True, exist_ok=True)

        self.feedback_file = self.config_dir / "feedback.json"
        self.stats_file = self.config_dir / "alert_stats.json"

        # Load existing data
        self.feedback_history = self._load_feedback()
        self.alert_stats = self._load_stats()

        # Configuration
        self.suppression_hours = 24  # Mute alerts for 24 hours by default
        self.cooldown_minutes = 30  # Minimum between similar alerts

    def record_feedback(
        self,
        alert_type: str,
        feedback: str,
        alert_content: str = "",
        user_comment: Optional[str] = None,
    ) -> None:
        """
        Record user feedback on an alert.

        Args:
            alert_type: Type of alert (e.g., "cpu_high", "disk_full")
            feedback: Feedback type ("useful", "not_needed", "ignore", "too_frequent", "thanks")
            alert_content: What the alert contained
            user_comment: Optional user comment
        """
        entry = FeedbackEntry(
            timestamp=datetime.now(),
            alert_type=alert_type,
            feedback=feedback,
            alert_content=alert_content,
            user_comment=user_comment,
        )

        # Add to history
        self.feedback_history.append(entry)

        # Update stats
        self._update_stats(alert_type, feedback)

        # Handle special feedback types
        if feedback == "ignore" or feedback == "mute":
            self._suppress_alert_type(alert_type)
        elif feedback == "too_frequent":
            self._increase_cooldown(alert_type)

        # Save to disk
        self._save_feedback()
        self._save_stats()

    def get_context(self) -> dict:
        """
        Get context information for LLM decision making.

        Returns:
            Dict with feedback context for the LLM
        """
        context = {
            "suppressed_types": self._get_suppressed_types(),
            "recent_feedback": self._get_recent_feedback_summary(),
            "alert_preferences": self._get_alert_preferences(),
        }

        return context

    def should_suppress(self, alert_type: str) -> bool:
        """
        Check if an alert type should be suppressed.

        Args:
            alert_type: Type of alert to check

        Returns:
            True if alert should be suppressed
        """
        stats = self.alert_stats.get(alert_type)
        if not stats:
            return False

        # Check suppression time
        if stats.suppression_until:
            if datetime.now() < stats.suppression_until:
                return True
            else:
                # Suppression expired, clear it
                stats.suppression_until = None
                self._save_stats()

        return False

    def get_cooldown(self, alert_type: str) -> int:
        """
        Get cooldown time for an alert type.

        Args:
            alert_type: Type of alert

        Returns:
            Cooldown in minutes
        """
        # Check recent alerts of this type
        recent_alerts = [
            f
            for f in self.feedback_history
            if f.alert_type == alert_type
            and f.timestamp > datetime.now() - timedelta(minutes=self.cooldown_minutes)
        ]

        if recent_alerts:
            # Check if user marked as "too frequent"
            for f in recent_alerts:
                if f.feedback == "too_frequent":
                    return self.cooldown_minutes * 2  # Double the cooldown

        return 0

    def get_utility_score(self, alert_type: str) -> float:
        """
        Get utility score for an alert type (0-1).

        Higher score = more useful to user.

        Args:
            alert_type: Type of alert

        Returns:
            Score between 0 and 1
        """
        stats = self.alert_stats.get(alert_type)
        if not stats or stats.total_alerts == 0:
            return 0.5  # Default neutral

        # Calculate score: useful / total
        score = stats.useful_count / stats.total_alerts

        # Also factor in ignored/not_needed
        negative = stats.not_needed_count + stats.ignored_count
        if negative > 0:
            score -= (negative / stats.total_alerts) * 0.3

        return max(0.0, min(1.0, score))

    def _load_feedback(self) -> list:
        """Load feedback history from disk."""
        if not self.feedback_file.exists():
            return []

        try:
            with open(self.feedback_file, "r") as f:
                data = json.load(f)
                return [
                    FeedbackEntry(
                        timestamp=datetime.fromisoformat(e["timestamp"]),
                        alert_type=e["alert_type"],
                        feedback=e["feedback"],
                        alert_content=e.get("alert_content", ""),
                        user_comment=e.get("user_comment"),
                    )
                    for e in data
                ]
        except Exception:
            return []

    def _save_feedback(self) -> None:
        """Save feedback history to disk."""
        try:
            data = [
                {
                    "timestamp": e.timestamp.isoformat(),
                    "alert_type": e.alert_type,
                    "feedback": e.feedback,
                    "alert_content": e.alert_content,
                    "user_comment": e.user_comment,
                }
                for e in self.feedback_history[-1000:]  # Keep last 1000
            ]

            with open(self.feedback_file, "w") as f:
                json.dump(data, f)
        except Exception:
            pass

    def _load_stats(self) -> dict:
        """Load alert stats from disk."""
        if not self.stats_file.exists():
            return {}

        try:
            with open(self.stats_file, "r") as f:
                data = json.load(f)
                return {
                    k: AlertTypeStats(**v) if isinstance(v, dict) else v
                    for k, v in data.items()
                }
        except Exception:
            return {}

    def _save_stats(self) -> None:
        """Save alert stats to disk."""
        try:
            data = {
                k: asdict(v) if isinstance(v, AlertTypeStats) else v
                for k, v in self.alert_stats.items()
            }

            with open(self.stats_file, "w") as f:
                json.dump(data, f)
        except Exception:
            pass

    def _update_stats(self, alert_type: str, feedback: str) -> None:
        """Update statistics for an alert type."""
        if alert_type not in self.alert_stats:
            self.alert_stats[alert_type] = AlertTypeStats()

        stats = self.alert_stats[alert_type]
        stats.total_alerts += 1
        stats.last_alert = datetime.now()

        if feedback == "useful" or feedback == "thanks":
            stats.useful_count += 1
        elif feedback == "not_needed":
            stats.not_needed_count += 1
        elif feedback == "ignore" or feedback == "mute":
            stats.ignored_count += 1

    def _suppress_alert_type(self, alert_type: str) -> None:
        """Suppress an alert type for a period."""
        if alert_type not in self.alert_stats:
            self.alert_stats[alert_type] = AlertTypeStats()

        self.alert_stats[alert_type].suppression_until = datetime.now() + timedelta(
            hours=self.suppression_hours
        )

    def _increase_cooldown(self, alert_type: str) -> None:
        """Increase cooldown for an alert type."""
        # This would be used to adjust the cooldown period
        # In a full implementation, this would persist
        pass

    def _get_suppressed_types(self) -> list:
        """Get list of currently suppressed alert types."""
        suppressed = []

        for alert_type, stats in self.alert_stats.items():
            if stats.suppression_until and datetime.now() < stats.suppression_until:
                suppressed.append(alert_type)

        return suppressed

    def _get_recent_feedback_summary(self) -> str:
        """Get summary of recent feedback for context."""
        recent = [
            f
            for f in self.feedback_history
            if f.timestamp > datetime.now() - timedelta(hours=24)
        ]

        if not recent:
            return "No recent feedback"

        # Summarize
        useful = sum(1 for f in recent if f.feedback in ["useful", "thanks"])
        not_needed = sum(1 for f in recent if f.feedback in ["not_needed", "ignore"])

        return f"{useful} useful, {not_needed} not needed (last 24h)"

    def _get_alert_preferences(self) -> dict:
        """Get alert preferences based on feedback."""
        prefs = {}

        for alert_type, stats in self.alert_stats.items():
            if stats.total_alerts > 0:
                prefs[alert_type] = {
                    "score": self.get_utility_score(alert_type),
                    "total": stats.total_alerts,
                    "useful": stats.useful_count,
                }

        return prefs


__all__ = ["FeedbackLearning", "FeedbackEntry", "AlertTypeStats"]
