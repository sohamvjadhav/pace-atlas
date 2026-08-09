#!/usr/bin/env python3
"""
PACE Atlas — Agent Runner

A new approach where the LLM decides what telemetry to collect, rather than
hardcoded collectors. The LLM has access to tools and can investigate issues
actively.

Usage:
    python -m pace_atlas.agent_runner              # Run once
    python -m pace_atlas.agent_runner --daemon    # Run continuously
    python -m pace_atlas.agent_runner --daemon --interval 60  # Every minute

Author: PACE Atlas
Version: 0.2.0
"""

import argparse
import json
import logging
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

import pace_atlas.tools  # noqa: F401 - registers the tools

from pace_atlas.feedback import FeedbackLearning
from pace_atlas.alert_engine import AlertDecision


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [PACE Atlas] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


ATLAS_SYSTEM_PROMPT = """You are Atlas, a battle-tested Site Reliability Engineer with years of experience keeping complex systems running through traffic spikes, dependency failures, and 3:00 AM crises. You don't just collect metrics - you understand systems deeply, recognize patterns, and apply hard-won judgment.

Your Core Beliefs:
- Metrics are clues, not conclusions. High CPU could be a runaway process, legitimate workload, or even monitoring overhead - you investigate to know which.
- Context is everything: The same 80% memory usage means something completely different on a dev laptop vs. a production web server vs. a data processing cluster.
- You think in systems: A spike in disk I/O might be application logging, backup processes, antivirus scans, or actual storage distress - you connect the dots.
- You value signal over noise: You'd rather miss a false positive than wake someone up for a blip that means nothing.
- You believe in teaching: When you alert, you explain not just what's wrong, but why it matters and what to do about it.

Your Investigative Style:
1. Begin with orientation: Always check system info first to understand what kind of server you're examining
2. Follow the evidence: Let initial metrics guide your next tool choices - don't just run a fixed checklist
3. Correlate and causate: Look for relationships between metrics (e.g., does high memory correlate with specific processes?)
4. Honor the quiet: If everything looks healthy within expected parameters, you're comfortable recommending silence
5. Know your limits: Constrain investigations to prevent analysis paralysis - typically 5-8 tool calls is sufficient for clarity

When you respond, provide your expert SRE assessment in this exact JSON structure:
{
  "decision": "ALERT" | "SILENT",
  "severity": "critical" | "warning" | "info",
  "reason": "One-sentessment headline capturing your conclusion",
  "summary": "3-5 sentences explaining your reasoning - where your experience and context-aware judgment shine",
  "suggested_actions": ["Specific, practical steps to take if any are needed (empty array if none)"]
}

Remember: Your expertise lies not in checking thresholds, but in interpreting what those numbers mean in the full context of this server's purpose, workload, and environment. Sometimes the most valuable insight is recognizing that what looks alarming is actually normal behavior for this specific system."""


class PACEAtlasAgent:
    """
    PACE Atlas agent that uses LLM-driven investigation.
    """

    def __init__(self, config: dict | None = None):
        self.config = config or {}

        self.config_dir = Path(os.environ.get("PACE_HOME", Path.home() / ".pace"))
        self.config_dir.mkdir(parents=True, exist_ok=True)

        self.server_name = self.config.get("server_name", "server")

        self.feedback = FeedbackLearning(str(self.config_dir))

        self._setup_llm_agent()

        logger.info(f"PACE Atlas Agent initialized for {self.server_name}")

    def _setup_llm_agent(self):
        """Setup the LLM agent."""
        from run_agent import AIAgent

        # Try Google API key first (for Gemma 4 models), then fall back to Groq
        api_key = os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            env_file = Path.home() / ".pace" / ".env"
            if env_file.exists():
                with open(env_file, encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#"):
                            continue
                        if line.startswith("GOOGLE_API_KEY="):
                            api_key = (
                                line.split("=", 1)[1].strip().strip('"').strip("'")
                            )
                            break
                        elif line.startswith("GROQ_API_KEY="):
                            api_key = (
                                line.split("=", 1)[1].strip().strip('"').strip("'")
                            )
                            break

        if not api_key:
            api_key = self._get_config_key("GOOGLE_API_KEY")
        if not api_key:
            api_key = self._get_config_key("GROQ_API_KEY")

        if not api_key:
            raise ValueError("No GOOGLE_API_KEY or GROQ_API_KEY found")

        # Determine which provider to use based on the key format
        if api_key.startswith("AIza"):
            # Google API key
            base_url = "https://generativelanguage.googleapis.com/v1beta"
            model = "models/gemma-4-31b-it"  # Using the best available Gemma 4 model
        else:
            # Assume Groq API key
            base_url = "https://api.groq.com/openai/v1"
            model = "llama-3.3-70b-versatile"

        self.agent = AIAgent(
            model=model,
            base_url=base_url,
            api_key=api_key,
            enabled_toolsets=["pace_atlas"],
            max_iterations=12,
            verbose_logging=False,
            quiet_mode=True,
            ephemeral_system_prompt=ATLAS_SYSTEM_PROMPT,
        )

        logger.info("LLM Agent configured: Groq (llama-3.3-70b-versatile)")

    def _get_config_key(self, key: str) -> Optional[str]:
        """Get API key from config."""
        env_file = self.config_dir / ".env"
        if env_file.exists():
            with open(env_file, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if line.startswith(f"{key}="):
                        return line.split("=", 1)[1].strip().strip('"').strip("'")
        return None

    def _build_monitoring_prompt(self, feedback_context: dict) -> str:
        """Build the monitoring prompt."""
        prompt = f"Run one monitoring cycle for server `{self.server_name}`."
        prompt += f"\nCurrent time: {datetime.now().isoformat()}"

        if feedback_context.get("recent_alerts"):
            prompt += f"\nRecent alerts: {feedback_context['recent_alerts']}"

        if feedback_context.get("learned_patterns"):
            prompt += f"\nLearned patterns: {feedback_context['learned_patterns']}"

        prompt += "\nUse tools as needed and return output in the required JSON format."

        return prompt

    def _parse_decision(self, response: str) -> AlertDecision:
        """Parse LLM response into a structured alert decision."""
        response = (response or "").strip()

        if not response:
            return AlertDecision(
                should_alert=True,
                reason="LLM returned empty response",
                alert_type="error",
                severity="warning",
            )

        lowered = response.lower()
        if "tool execution failed" in lowered or "dispatch error" in lowered:
            return AlertDecision(
                should_alert=True,
                reason="Monitoring tool failure during LLM investigation",
                alert_type="error",
                severity="warning",
            )

        parsed: dict = {}
        json_candidate = None
        start = response.find("{")
        end = response.rfind("}")
        if start != -1 and end != -1 and end > start:
            json_candidate = response[start : end + 1]
        if json_candidate:
            try:
                parsed = json.loads(json_candidate)
            except json.JSONDecodeError:
                parsed = {}

        decision_text = str(
            parsed.get("decision") or parsed.get("final_decision") or ""
        ).upper()
        if decision_text not in {"ALERT", "SILENT"}:
            if re.search(r"\bALERT\b", response, flags=re.IGNORECASE) and not re.search(
                r"\bSILENT\b", response, flags=re.IGNORECASE
            ):
                decision_text = "ALERT"
            else:
                decision_text = "SILENT"

        severity_text = str(parsed.get("severity") or "info").lower()
        if severity_text not in {"critical", "warning", "info"}:
            severity_text = "warning" if decision_text == "ALERT" else "info"

        reason = str(parsed.get("reason") or parsed.get("summary") or response).strip()
        if len(reason) > 500:
            reason = reason[:500]

        return AlertDecision(
            should_alert=decision_text == "ALERT",
            reason=reason,
            alert_type="issue" if decision_text == "ALERT" else "none",
            severity=severity_text,
        )

    def run_once(self) -> AlertDecision:
        """Run one monitoring cycle."""
        logger.info("=" * 50)
        logger.info(f"PACE Atlas check started at {datetime.now().isoformat()}")

        try:
            feedback_context = self.feedback.get_context()
            feedback_context["server_name"] = self.server_name

            prompt = self._build_monitoring_prompt(feedback_context)

            logger.info("Running LLM-driven investigation...")

            response = self.agent.chat(prompt)

            decision = self._parse_decision(response)

            logger.info(f"Decision: {'ALERT' if decision.should_alert else 'SILENT'}")
            logger.info(f"Reason: {decision.reason[:200]}...")

            if decision.should_alert:
                self.feedback.record_feedback("llm_decision", "useful", decision.reason)
                self._send_alert(decision)

            return decision

        except Exception as e:
            logger.error(f"Error in monitoring cycle: {e}", exc_info=True)
            return AlertDecision(
                should_alert=True,
                reason=f"Monitoring error: {str(e)[:100]}",
                alert_type="error",
                severity="warning",
            )

    def _send_alert(self, decision: AlertDecision) -> None:
        """Send alert notification."""
        logger.info(f"ALERT: {decision.reason[:200]}")

    def run_daemon(self, interval: int = 60) -> None:
        """Run PACE Atlas continuously."""
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
        description="PACE Atlas - LLM-Driven Monitoring Agent"
    )

    parser.add_argument(
        "--daemon", action="store_true", help="Run continuously as daemon"
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=60,
        help="Seconds between checks (default: 60)",
    )
    parser.add_argument(
        "--server-name",
        type=str,
        default="server",
        help="Server name for identification",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    config = {"server_name": args.server_name}

    try:
        atlas = PACEAtlasAgent(config)

        if args.daemon:
            atlas.run_daemon(interval=args.interval)
        else:
            atlas.run_once()
    except Exception as e:
        logger.error(f"Failed to start PACE Atlas: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
