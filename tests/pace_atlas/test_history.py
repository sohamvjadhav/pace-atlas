"""Tests for pace_atlas.history: JSONL ledger, dedupe, trends, summary."""
import json
import time

from pace_atlas.history import AtlasHistory


def _fresh_history(tmp_path):
    return AtlasHistory(tmp_path / "history.jsonl", max_entries=100)


def test_alert_records_are_persisted(tmp_path):
    h = _fresh_history(tmp_path)
    h.record_alert_sent("disk", "critical", "disk at 99%")
    h2 = AtlasHistory(tmp_path / "history.jsonl")
    assert len(h2.alerts()) == 1
    assert h2.alerts()[0]["alert_type"] == "disk"
    assert h2.alerts()[0]["severity"] == "critical"


def test_repeat_suppression_within_window(tmp_path):
    h = _fresh_history(tmp_path)
    h.record_alert_sent("disk", "critical", "disk at 99%")
    assert h.is_suppressed("disk", "critical", window_seconds=300) is True
    assert h.is_suppressed("disk", "warning", window_seconds=300) is False
    assert h.is_suppressed("memory", "critical", window_seconds=300) is False


def test_no_suppression_after_window(tmp_path):
    h = _fresh_history(tmp_path)
    h.record_alert_sent("disk", "critical", "old", ts=time.time() - 3600)
    assert h.is_suppressed("disk", "critical", window_seconds=300) is False


def test_window_zero_disables_suppression(tmp_path):
    h = _fresh_history(tmp_path)
    h.record_alert_sent("disk", "critical", "a")
    assert h.is_suppressed("disk", "critical", window_seconds=0) is False


def test_telemetry_trends_ordered(tmp_path):
    h = _fresh_history(tmp_path)
    now = time.time()
    for i, v in enumerate([50.0, 60.0, 70.0]):
        h.record_telemetry("system", {"cpu_percent": v}, ts=now - (2 - i) * 60)
    samples = h.recent_values("system", "cpu_percent", window_seconds=600)
    values = [v for _, v in samples]
    assert values == [50.0, 60.0, 70.0]


def test_telemetry_ignores_non_numeric(tmp_path):
    h = _fresh_history(tmp_path)
    h.record_telemetry("system", {"cpu_percent": "n/a"}, ts=time.time())
    h.record_telemetry("system", {"cpu_percent": 42.0}, ts=time.time())
    assert h.recent_values("system", "cpu_percent")[0][1] == 42.0


def test_unknown_collector_has_no_trend(tmp_path):
    h = _fresh_history(tmp_path)
    h.record_telemetry("system", {"cpu_percent": 10.0})
    assert h.recent_values("memory", "usage_percent") == []


def test_summary_counts(tmp_path):
    h = _fresh_history(tmp_path)
    h.record_alert_sent("disk", "critical", "a")
    h.record_alert_sent("disk", "critical", "b")
    h.record_alert_sent("memory", "warning", "c")
    h.record_telemetry("system", {"cpu_percent": 12.0})
    summary = h.summary()
    assert summary["alert_entries"] == 3
    assert summary["telemetry_points"] == 1
    assert summary["breakdown"] == {"critical/disk": 2, "warning/memory": 1}


def test_max_entries_trims_oldest(tmp_path):
    h = AtlasHistory(tmp_path / "history.jsonl", max_entries=5)
    for i in range(10):
        h.record_telemetry("system", {"cpu_percent": float(i)}, ts=1000 + i)
    assert len(h._entries if hasattr(h, "_entries") else h._recent) == 5
    first_ts = list(h._recent)[0]["ts"]
    assert first_ts == 1005  # oldest dropped


def test_append_is_bounded_after_trim(tmp_path):
    h = AtlasHistory(tmp_path / "history.jsonl", max_entries=3)
    for i in range(10):
        h.record_telemetry("system", {"cpu_percent": float(i)}, ts=1000 + i)
    assert len(h._recent) == 3
    lines = tmp_path.joinpath("history.jsonl").read_text().strip().splitlines()
    assert len(lines) == 3


def test_append_only_jsonl_roundtrip(tmp_path):
    h = _fresh_history(tmp_path)
    h.record_alert_sent("ssh", "warning", "failed login")
    lines = tmp_path.joinpath("history.jsonl").read_text().strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["alert_type"] == "ssh"