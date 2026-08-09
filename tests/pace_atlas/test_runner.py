"""Tests for pace_atlas.runner: wiring, daemon lifecycle, dispatch, systemd."""
import os
import signal
import time

import pytest

from pace_atlas.runner import PACEAtlas, _systemd_unit, install_systemd
from pace_atlas.telemetry import TelemetrySnapshot


# ---------------------------------------------------------------------------
# Systemd unit
# ---------------------------------------------------------------------------


def test_systemd_unit_shape():
    unit = _systemd_unit("/usr/bin/python3", 300)
    assert "pace_atlas.runner --daemon --interval 300" in unit
    assert "Restart=always" in unit
    assert "[Service]" in unit and "[Install]" in unit


def test_install_systemd_writes_unit(tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    unit = install_systemd("/usr/bin/python3", 60)
    assert unit.exists()
    content = unit.read_text()
    assert "--interval 60" in content
    assert "pace-atlas.service" in unit.name


# ---------------------------------------------------------------------------
# PACEAtlas wiring
# ---------------------------------------------------------------------------


def test_llm_model_flows_to_alert_engine(tmp_path, monkeypatch):
    monkeypatch.setenv("PACE_HOME", str(tmp_path))
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    from pace_atlas.runner import PACEAtlas

    atlas = PACEAtlas({"llm": {"provider": "openai", "model": "gpt-4o-mini"}})
    assert atlas.llm_client is not None
    assert atlas._llm_model == "gpt-4o-mini"
    assert atlas.alert_engine.llm_model == "gpt-4o-mini"


def test_no_key_means_no_llm(tmp_path, monkeypatch):
    monkeypatch.setenv("PACE_HOME", str(tmp_path))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    atlas = PACEAtlas({})
    assert atlas.llm_client is None
    assert atlas.alert_engine.llm_client is None


# ---------------------------------------------------------------------------
# Dispatch + dedupe
# ---------------------------------------------------------------------------


def test_run_once_dispatches_then_suppresses(tmp_path, monkeypatch):
    monkeypatch.setenv("PACE_HOME", str(tmp_path))
    alert_log = tmp_path / "alerts.log"
    atlas = PACEAtlas(
        {
            "hard_rules": {"cpu_threshold": 80},
            "alerts": {"suppress_repeats": True, "dedupe_window_seconds": 300},
            "notifications": {
                "channels": ["file"],
                "file": {"path": str(alert_log)},
            },
        }
    )
    atlas.collector = _FakeCollector({"cpu_percent": 95.0})

    d1 = atlas.run_once()
    assert d1.should_alert is True
    body = alert_log.read_text()
    assert "CPU at 95.0%" in body
    assert "— PACE Atlas" in body

    d2 = atlas.run_once()
    assert d2.should_alert is True  # engine still decides
    # but no second delivery happened
    assert alert_log.read_text() == body


def test_run_once_silent_when_healthy(tmp_path, monkeypatch):
    monkeypatch.setenv("PACE_HOME", str(tmp_path))
    atlas = PACEAtlas({"notifications": {"channels": ["file"]}})
    atlas.collector = _FakeCollector({"cpu_percent": 5.0})
    decision = atlas.run_once()
    assert decision.should_alert is False


def test_alert_message_contains_metrics_and_insights(tmp_path, monkeypatch):
    monkeypatch.setenv("PACE_HOME", str(tmp_path))
    alert_log = tmp_path / "alerts.log"
    atlas = PACEAtlas(
        {
            "hard_rules": {"cpu_threshold": 80},
            "notifications": {"channels": ["file"], "file": {"path": str(alert_log)}},
        }
    )
    atlas.collector = _FakeCollector(
        {"cpu_percent": 95.0, "disk": {"usage_percent": 88.0}}
    )
    atlas.run_once()
    body = alert_log.read_text()
    assert "CPU: 95.0%" in body
    assert "Disk: 88.0%" in body


# ---------------------------------------------------------------------------
# Daemon lifecycle
# ---------------------------------------------------------------------------


def test_pidfile_acquire_release(tmp_path, monkeypatch):
    monkeypatch.setenv("PACE_HOME", str(tmp_path))
    atlas = PACEAtlas({"notifications": {"channels": ["file"]}})
    pidfile = atlas._pidfile()
    atlas._acquire_pidfile()
    assert pidfile.exists()
    assert int(pidfile.read_text()) == os.getpid()
    atlas._release_pidfile()
    assert not pidfile.exists()


def test_stale_pidfile_is_recovered(tmp_path, monkeypatch):
    monkeypatch.setenv("PACE_HOME", str(tmp_path))
    atlas = PACEAtlas({"notifications": {"channels": ["file"]}})
    atlas._pidfile().write_text("999999999")  # PID that doesn't exist
    atlas._acquire_pidfile()
    assert int(atlas._pidfile().read_text()) == os.getpid()


def test_double_start_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("PACE_HOME", str(tmp_path))
    atlas = PACEAtlas({"notifications": {"channels": ["file"]}})
    atlas._acquire_pidfile()
    try:
        with pytest.raises(SystemExit, match="already running"):
            atlas._acquire_pidfile()
    finally:
        atlas._release_pidfile()


def test_signal_stops_loop(tmp_path, monkeypatch):
    monkeypatch.setenv("PACE_HOME", str(tmp_path))
    atlas = PACEAtlas({"notifications": {"channels": ["file"]}})
    atlas.collector = _FakeCollector({"cpu_percent": 5.0})
    atlas._install_signal_handlers()
    os.kill(os.getpid(), signal.SIGTERM)
    assert atlas._running is False


def test_status_summary_fields(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("PACE_HOME", str(tmp_path))
    atlas = PACEAtlas({"notifications": {"channels": ["file"]}})
    atlas.collector = _FakeCollector({"cpu_percent": 5.0})
    atlas.run_once()
    summary = atlas.history.summary()
    assert "alert_entries" in summary
    assert summary["alert_entries"] == 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeCollector:
    def __init__(self, data: dict):
        self.collectors = []
        if "cpu_percent" in data:
            self.collectors.append(
                TelemetrySnapshot(collector_name="system", timestamp=0.0, data={"cpu_percent": data["cpu_percent"]})
            )
        if "disk" in data:
            self.collectors.append(
                TelemetrySnapshot(collector_name="disk", timestamp=0.0, data=data["disk"])
            )

    def collect_all(self):
        return self.collectors
