"""
PACE Atlas — Proactive Autonomous Cloud Environment

The resident monitoring agent that watches your server and alerts you when it matters.

Version: 0.1.0

Quick Start:
    python -m pace_atlas.runner --daemon

Or run once:
    python -m pace_atlas.runner

Configuration:
    Edit ~/.pace/config.yaml for settings

Modules:
    - telemetry: Collects server metrics (CPU, memory, disk, network, etc.)
    - alert_engine: Decides when to alert (hard rules + LLM)
    - feedback: Learns from user feedback to improve alerts

Documentation:
    See docs/architecture.md for full architecture
"""

from .runner import PACEAtlas, main
from .telemetry import (
    TelemetryCollector,
    TelemetrySnapshot,
    CompositeCollector,
    get_default_collectors,
)
from .alert_engine import AlertEngine, HardRules, AlertDecision
from .feedback import FeedbackLearning

__version__ = "0.1.0"

__all__ = [
    # Runner
    "PACEAtlas",
    "main",
    # Telemetry
    "TelemetryCollector",
    "TelemetrySnapshot",
    "CompositeCollector",
    "get_default_collectors",
    # Alert Engine
    "AlertEngine",
    "HardRules",
    "AlertDecision",
    # Feedback
    "FeedbackLearning",
]
