"""
PACE Atlas — Main Runner

The main entry point for PACE Atlas monitoring agent.

Usage:
    python -m pace_atlas.runner              # Run once
    python -m pace_atlas.runner --daemon    # Run continuously
    python -m pace_atlas.runner --daemon --interval 300  # Every 5 minutes

Author: PACE Atlas
Version: 0.1.0
"""

import argparse
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

# Setup path
sys.path.insert(0, str(Path(__file__).parent.parent))

from pace_atlas.telemetry import (
    CompositeCollector,
    SystemCollector,
    MemoryCollector,
    DiskCollector,
    NetworkCollector,
    ProcessCollector,
    SecurityCollector,
    CloudCollector,
    LogAggregator,
)
from pace_atlas.alert_engine import AlertEngine, AlertDecision
from pace_atlas.feedback import FeedbackLearning


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [PACE Atlas] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


class PACEAtlas:
    """
    Main PACE Atlas agent class.

    Orchestrates telemetry collection, alert decisions, and notifications.
    """

    def __init__(self, config: dict | None = None):
        """
        Initialize PACE Atlas.

        Args:
            config: Optional configuration dict
        """
        self.config = config or {}

        # Setup directories
        self.config_dir = Path(os.environ.get("PACE_HOME", Path.home() / ".pace"))
        self.config_dir.mkdir(parents=True, exist_ok=True)

        # Initialize components
        self.collector = self._setup_collector()
        self.alert_engine = AlertEngine(self.config.get("alert_config", {}))
        self.feedback = FeedbackLearning(str(self.config_dir))

        # Connect feedback to alert engine
        self.alert_engine.set_feedback(self.feedback)

        # Setup LLM client if configured
        self.llm_client = self._setup_llm_client()
        if self.llm_client:
            self.alert_engine.set_llm_client(self.llm_client)

        # Notification channels
        self.notification_handler = self._setup_notifications()

        # State
        self.last_alert_time: Optional[datetime] = None
        self.server_name = self.config.get("server_name", "server")

        logger.info(f"PACE Atlas initialized for {self.server_name}")

    def _setup_collector(self) -> CompositeCollector:
        """Setup the telemetry collector."""
        collector = CompositeCollector()

        # Add all collectors
        collectors = [
            SystemCollector,
            MemoryCollector,
            DiskCollector,
            NetworkCollector,
            ProcessCollector,
            SecurityCollector,
            CloudCollector,
            LogAggregator,
        ]

        for collector_class in collectors:
            try:
                c = collector_class(
                    self.config.get("telemetry", {}).get(
                        collector_class.__name__.replace("Collector", "").lower(), {}
                    )
                )
                collector.add_collector(c)
            except Exception as e:
                logger.warning(f"Failed to add {collector_class.__name__}: {e}")

        logger.info(f"Added {len(collector.collectors)} telemetry collectors")
        return collector

    def _setup_llm_client(self):
        """Setup LLM client for intelligent decisions."""
        # Try to setup client - don't require config to be set first
        # Check environment variable first
        try:
            from openai import OpenAI

            api_key = os.environ.get("GROQ_API_KEY")
            if not api_key:
                api_key = self._get_config_key("GROQ_API_KEY")

            if api_key:
                client = OpenAI(
                    api_key=api_key, base_url="https://api.groq.com/openai/v1"
                )
                logger.info(f"LLM client configured: Groq (llama-3.3-70b-versatile)")
                return client

        except ImportError:
            pass

        try:
            # Try OpenAI
            from openai import OpenAI

            api_key = os.environ.get("OPENAI_API_KEY")
            if not api_key:
                api_key = self._get_config_key("openai_api_key")

            if api_key:
                client = OpenAI(api_key=api_key)
                logger.info(f"LLM client configured: {model}")
                return client

        except ImportError:
            pass

        try:
            # Try Anthropic
            import anthropic

            api_key = os.environ.get("ANTHROPIC_API_KEY")
            if not api_key:
                api_key = self._get_config_key("anthropic_api_key")

            if api_key:
                client = anthropic.Anthropic(api_key=api_key)
                logger.info(f"LLM client configured: {model}")
                return client

        except ImportError:
            pass

        logger.warning("No LLM client available")
        return None

    def _get_config_key(self, key: str) -> Optional[str]:
        """Get API key from config."""
        env_file = self.config_dir / ".env"
        if env_file.exists():
            with open(env_file) as f:
                for line in f:
                    if line.startswith(f"{key}="):
                        return line.split("=", 1)[1].strip()
        return None

    def _setup_notifications(self):
        """Setup notification handler."""
        # Import from parent gateway
        try:
            from gateway.run import Gateway

            # Check if gateway is running
            channel = self.config.get("notification_channel", "telegram")
            logger.info(f"Notifications will be sent via {channel}")
            return None  # Will use gateway when available

        except ImportError:
            logger.warning("Gateway not available for notifications")
            return None

    def run_once(self) -> AlertDecision:
        """
        Run one monitoring cycle.

        Returns:
            AlertDecision from this cycle
        """
        logger.info("=" * 50)
        logger.info(f"PACE Atlas check started at {datetime.now().isoformat()}")

        try:
            # Step 1: Collect telemetry
            logger.info("Collecting telemetry...")
            snapshots = self.collector.collect_all()

            if not snapshots:
                logger.warning("No telemetry collected")
                return AlertDecision(
                    should_alert=False,
                    reason="No telemetry data collected",
                    alert_type="error",
                )

            logger.info(f"Collected {len(snapshots)} telemetry snapshots")

            # Step 2: Make alert decision
            logger.info("Evaluating alert decision...")

            # Get feedback context
            feedback_context = self.feedback.get_context()
            feedback_context["server_name"] = self.server_name

            decision = self.alert_engine.decide(snapshots, feedback_context)

            logger.info(f"Decision: {'ALERT' if decision.should_alert else 'SILENT'}")
            logger.info(f"Reason: {decision.reason}")

            # Step 3: Handle alert
            if decision.should_alert:
                self._send_alert(decision, snapshots)
                self.last_alert_time = datetime.now()

            return decision

        except Exception as e:
            logger.error(f"Error in monitoring cycle: {e}", exc_info=True)
            return AlertDecision(
                should_alert=True,
                reason=f"Monitoring error: {str(e)[:100]}",
                alert_type="error",
                severity="warning",
            )

    def _send_alert(self, decision: AlertDecision, snapshots: list) -> None:
        """Send alert notification to user."""
        logger.info(f"Sending alert: {decision.reason}")

        # Build message
        message = self._format_alert_message(decision, snapshots)

        # Try to send via gateway
        try:
            # This would integrate with the gateway
            logger.info(f"Alert message: {message[:200]}...")
        except Exception as e:
            logger.error(f"Failed to send notification: {e}")

    def _format_alert_message(self, decision: AlertDecision, snapshots: list) -> str:
        """Format alert message for user notification."""
        lines = []

        # Header with severity
        if decision.severity == "critical":
            lines.append("🔴 CRITICAL ALERT")
        elif decision.severity == "warning":
            lines.append("🟡 WARNING")
        else:
            lines.append("ℹ️ INFO")

        # Server name
        lines.append(f"Server: {self.server_name}")

        # Main message
        lines.append(f"\n{decision.reason}")

        # Add relevant metrics
        lines.append("\n--- Current Metrics ---")

        for snapshot in snapshots:
            if snapshot.collector_name == "system":
                cpu = snapshot.data.get("cpu_percent", "N/A")
                lines.append(f"CPU: {cpu}%")
            elif snapshot.collector_name == "memory":
                mem = snapshot.data.get("usage_percent", "N/A")
                lines.append(f"Memory: {mem}%")
            elif snapshot.collector_name == "disk":
                disk = snapshot.data.get("usage_percent", "N/A")
                lines.append(f"Disk: {disk}%")

        # Footer
        lines.append(f"\n— PACE Atlas ({datetime.now().strftime('%H:%M')})")

        return "\n".join(lines)

    def run_daemon(self, interval: int = 300) -> None:
        """
        Run PACE Atlas continuously.

        Args:
            interval: Seconds between checks (default: 300 = 5 minutes)
        """
        logger.info(f"Starting PACE Atlas daemon (interval: {interval}s)")

        while True:
            try:
                self.run_once()
            except Exception as e:
                logger.error(f"Daemon error: {e}")

            logger.info(f"Next check in {interval} seconds...")
            time.sleep(interval)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="PACE Atlas - Proactive Autonomous Cloud Environment"
    )

    parser.add_argument(
        "--daemon", action="store_true", help="Run continuously as daemon"
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=300,
        help="Seconds between checks (default: 300)",
    )
    parser.add_argument(
        "--server-name",
        type=str,
        default="server",
        help="Server name for identification",
    )
    parser.add_argument("--config", type=str, help="Path to config file")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    args = parser.parse_args()

    # Set logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Load config if provided
    config = {}
    if args.config:
        import yaml

        with open(args.config) as f:
            config = yaml.safe_load(f)

    # Add server name to config
    config["server_name"] = args.server_name

    # Create and run PACE Atlas
    atlas = PACEAtlas(config)

    if args.daemon:
        atlas.run_daemon(interval=args.interval)
    else:
        atlas.run_once()


if __name__ == "__main__":
    main()
