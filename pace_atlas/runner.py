"""
PACE Atlas — Main Runner

The resident monitoring agent. Each cycle:

1. Collects telemetry (system, memory, disk, network, process, security,
   cloud, logs)
2. Records metrics to a persistent history ledger (trends across restarts)
3. Runs hard rules, then the LLM decision layer when configured
4. Runs full capabilities analysis (security, cost, predictive) and folds
   the insights into the alert
5. Suppresses repeat alerts within the dedupe window (alert fatigue control)
6. Delivers via the configured notification channels

Usage:
    python -m pace_atlas.runner [-c FILE]             # run once
    python -m pace_atlas.runner --daemon              # run continuously
    python -m pace_atlas.runner --daemon --interval 300
    python -m pace_atlas.runner --install            # write ~/.pace/config.yaml
    python -m pace_atlas.runner --install-systemd    # install a user systemd unit
    python -m pace_atlas.runner --status             # health/status summary
"""

import argparse
import logging
import os
import signal
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from pace_atlas import config as atlas_config
from pace_atlas.alert_engine import AlertDecision, AlertEngine
from pace_atlas.capabilities import AtlasCapabilities
from pace_atlas.feedback import FeedbackLearning
from pace_atlas.history import AtlasHistory
from pace_atlas.notify import NotificationManager
from pace_atlas.telemetry import (
    CloudCollector,
    CompositeCollector,
    DiskCollector,
    LogAggregator,
    MemoryCollector,
    NetworkCollector,
    ProcessCollector,
    SecurityCollector,
    SystemCollector,
)

logger = logging.getLogger(__name__)
PYTHON = sys.executable


class PACEAtlas:
    """Resident SRE agent orchestrating telemetry, analysis, and delivery."""

    def __init__(self, config: Optional[dict] = None):
        self.config = dict(config) if config else {}
        self.home = atlas_config.pace_home()
        self.home.mkdir(parents=True, exist_ok=True)

        self.collector = self._setup_collector()
        self.alert_engine = AlertEngine({"hard_rules": self.config.get("hard_rules", {})})
        self.feedback = FeedbackLearning(str(self.home))
        self.alert_engine.set_feedback(self.feedback)

        self.capabilities = AtlasCapabilities(str(self.home))
        self.llm_client = self._setup_llm_client()
        if self.llm_client:
            self.alert_engine.set_llm_client(self.llm_client)

        alerts_cfg = self.config.get("alerts", {})
        history_path = alerts_cfg.get("history_file") or str(self.home / "history.jsonl")
        self.history = AtlasHistory(
            Path(history_path).expanduser(),
            max_entries=alerts_cfg.get("max_history_entries", 5000),
        )
        self.dedupe_window = alerts_cfg.get("dedupe_window_seconds", 300)
        self.suppress_repeats = alerts_cfg.get("suppress_repeats", True)

        self.notifier = NotificationManager.from_config(self.config)
        self.server_name = self.config.get("server_name", "server")
        self._running = True
        self.last_alert_at: Optional[datetime] = None
        logger.info("PACE Atlas initialized for %s (%d notifier channels)", self.server_name, len(self.notifier.channels))

    def _setup_collector(self):
        collector = CompositeCollector()
        for cls in (SystemCollector, MemoryCollector, DiskCollector, NetworkCollector,
                    ProcessCollector, SecurityCollector, CloudCollector, LogAggregator):
            try:
                collector.add_collector(cls(self.config.get("telemetry", {}).get(cls.__name__.replace("Collector", "").lower(), {})))
            except Exception as exc:
                logger.warning("collector %s failed to init: %s", cls.__name__, exc)
        return collector

    def _setup_llm_client(self):
        llm = self.config.get("llm", {})
        provider = llm.get("provider")
        model = llm.get("model")
        api_key = llm.get("api_key")
        try:
            from openai import OpenAI
        except ImportError:
            logger.warning("openai package not installed; LLM decision layer disabled")
            return None

        if not api_key and not provider:
            logger.info("no LLM configured (no provider/api key); LLM decision layer disabled")
            return None

        bases = {
            "groq": "https://api.groq.com/openai/v1",
            "openai": "https://api.openai.com/v1",
            "anthropic": None,
        }
        base_url = llm.get("base_url") or bases.get(provider)
        try:
            client = OpenAI(api_key=api_key, base_url=base_url) if base_url else OpenAI(api_key=api_key)
        except Exception as exc:
            logger.warning("LLM client init failed: %s", exc)
            return None
        self._llm_model = model or llm.get("model") or "gpt-4o-mini"
        logger.info("LLM configured: %s (%s)", provider, self._llm_model)
        return client

    def _telemetry_dict(self, snapshots):
        data = {}
        for snap in snapshots:
            data[snap.collector_name] = snap.data
        return data

    def _llm_complete(self, prompt: str, max_tokens: int = 500) -> Optional[str]:
        if not self.llm_client:
            return None
        try:
            response = self.llm_client.chat.completions.create(
                model=self._llm_model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
            )
            return response.choices[0].message.content
        except Exception as exc:
            logger.warning("LLM call failed: %s", exc)
            return None

    def run_once(self) -> AlertDecision:
        snapshots = self.collector.collect_all()
        telemetry = self._telemetry_dict(snapshots)

        for snap in snapshots:
            self.history.record_telemetry(snap.collector_name, snap.data)

        try:
            insights = self.capabilities.run_full_analysis(telemetry)
        except Exception as exc:
            logger.warning("capabilities analysis failed: %s", exc)
            insights = []

        context = self.feedback.get_context()
        context["server_name"] = self.server_name
        decision = self.alert_engine.decide(snapshots, context)

        if decision.should_alert:
            self._dispatch_alert(decision, telemetry, insights)
        return decision

    def _dispatch_alert(self, decision, telemetry, insights):
        key = (decision.alert_type, decision.severity)
        if self.suppress_repeats and self.history.is_suppressed(*key, window_seconds=self.dedupe_window):
            logger.info("suppressed repeat alert %s/%s (dedupe window %ss)", *key, self.dedupe_window)
            return

        subject = self._subject(decision)
        body = self._format_alert_message(decision, telemetry, insights)
        delivered = self.notifier.send(subject, body)
        self.history.record_alert_sent(decision.alert_type, decision.severity, decision.reason)
        logger.info("alert delivered via: %s", ", ".join(delivered) or "none")
        self.last_alert_at = datetime.now()

    @staticmethod
    def _subject(decision) -> str:
        sev = decision.severity
        icon = {"critical": "🔴 CRITICAL", "warning": "🟡 WARNING"}.get(sev, "ℹ️ INFO")
        return f"{icon}: {decision.reason[:80]}"

    def _format_alert_message(self, decision, telemetry, insights) -> str:
        lines = [f"Server: {self.server_name}", "", decision.reason, "", "--- Metrics ---"]
        for snap_name, key, label in (("system", "cpu_percent", "CPU"), ("memory", "usage_percent", "Memory"), ("disk", "usage_percent", "Disk")):
            value = (telemetry.get(snap_name) or {}).get(key)
            if value is not None:
                lines.append(f"{label}: {value}%")

        trend_lines = []
        for snap_name, key, label in (("system", "cpu_percent", "CPU"), ("memory", "usage_percent", "Memory"), ("disk", "usage_percent", "Disk")):
            samples = self.history.recent_values(snap_name, key, window_seconds=3600)
            if len(samples) >= 3:
                avg = sum(v for _, v in samples) / len(samples)
                trend_lines.append(f"{label} 1h avg: {avg:.1f}%")
        if trend_lines:
            lines += ["", "--- Trend (1h) ---"] + trend_lines

        if insights:
            lines.append("")
            lines.append("--- Insights ---")
            for result in insights[:5]:
                title = getattr(result, "title", "insight")
                body = getattr(result, "body", "")
                lines.append(f"• {title}: {body}")

        lines.append(f"\n— PACE Atlas ({datetime.now().strftime('%H:%M')})")
        return "\n".join(lines)

    def run_daemon(self, interval: int = 300) -> None:
        self._install_signal_handlers()
        self._acquire_pidfile()
        logger.info("daemon started (interval %ss, pid %d)", interval, os.getpid())
        try:
            while self._running:
                try:
                    self.run_once()
                except Exception as exc:
                    logger.error("cycle failed: %s", exc)
                for _ in range(max(1, interval // 5)):
                    if not self._running:
                        break
                    time.sleep(5)
        finally:
            self._release_pidfile()
            logger.info("daemon stopped cleanly")

    def _install_signal_handlers(self):
        def _stop(_sig, _frame):
            logger.info("signal %s received, shutting down", _sig)
            self._running = False
        signal.signal(signal.SIGTERM, _stop)
        signal.signal(signal.SIGINT, _stop)

    def _pidfile(self) -> Path:
        return self.home / "atlas.pid"

    def _acquire_pidfile(self):
        pidfile = self._pidfile()
        if pidfile.exists():
            try:
                old = int(pidfile.read_text().strip())
                os.kill(old, 0)
                raise SystemExit(f"PACE Atlas already running (pid {old}); remove {pidfile} if stale")
            except (ValueError, ProcessLookupError):
                logger.info("stale pidfile %s removed", pidfile)
                pidfile.unlink(missing_ok=True)
        pidfile.write_text(str(os.getpid()))

    def _release_pidfile(self):
        self._pidfile().unlink(missing_ok=True)


def _systemd_unit(python: str, interval: int) -> str:
    return f"""[Unit]
Description=PACE Atlas — resident SRE agent
After=network-online.target

[Service]
Type=simple
ExecStart={python} -m pace_atlas.runner --daemon --interval {interval}
Restart=always
RestartSec=30
UMask=0022

[Install]
WantedBy=default.target
"""


def install_systemd(python: str, interval: int) -> Path:
    unit_dir = Path.home() / ".config" / "systemd" / "user"
    unit_dir.mkdir(parents=True, exist_ok=True)
    unit = unit_dir / "pace-atlas.service"
    unit.write_text(_systemd_unit(python, interval))
    return unit


def main():
    parser = argparse.ArgumentParser(description="PACE Atlas - Proactive Autonomous Cloud Environment")
    parser.add_argument("--daemon", action="store_true", help="run continuously as a daemon")
    parser.add_argument("--interval", type=int, default=None, help="seconds between checks")
    parser.add_argument("--server-name", type=str, default=None, help="server name")
    parser.add_argument("--config", "-c", type=str, default=None, help="path to config file")
    parser.add_argument("--verbose", "-v", action="store_true", help="verbose output")
    parser.add_argument("--install", action="store_true", help="write default config to ~/.pace/config.yaml")
    parser.add_argument("--install-systemd", action="store_true", help="write user systemd unit and print commands")
    parser.add_argument("--status", action="store_true", help="print health summary and exit")
    parser.add_argument("--once", action="store_true", help="run a single cycle and exit (default)")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [PACE Atlas] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    if args.install:
        path = atlas_config.install_default_config()
        print(f"Default config written to {path}")
        return

    overrides = {}
    if args.interval:
        overrides["check_interval"] = args.interval
    if args.server_name:
        overrides["server_name"] = args.server_name

    config = atlas_config.load_config(args.config, overrides)
    interval = config.get("check_interval", 300)

    if args.install_systemd:
        unit = install_systemd(PYTHON, interval)
        print(f"Systemd unit written to {unit}")
        print(f"  systemctl --user daemon-reload")
        print(f"  systemctl --user enable --now pace-atlas")
        return

    atlas = PACEAtlas(config)

    if args.status:
        print(f"PACE Atlas: {atlas.server_name}")
        print(f"Collectors: {len(atlas.collector.collectors)}")
        print(f"Channels:   {', '.join(c.name for c in atlas.notifier.channels) or 'none'}")
        print(f"LLM:        {'enabled (' + getattr(atlas, '_llm_model', '?') + ')' if atlas.llm_client else 'disabled'}")
        print(f"History:    {atlas.history.summary()}")
        return

    if args.daemon:
        atlas.run_daemon(interval=interval)
    else:
        atlas.run_once()


if __name__ == "__main__":
    main()
