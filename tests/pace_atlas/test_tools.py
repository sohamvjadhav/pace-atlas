"""Tests for pace_atlas.tools: the SRE tool surface, safety, JSON contracts."""
import json

import pace_atlas.tools as t


def _load(result: str) -> dict:
    return json.loads(result)


# ---------------------------------------------------------------------------
# Payload contracts
# ---------------------------------------------------------------------------


def test_system_info_shape():
    data = _load(t.get_system_info())
    assert data["success"] is True
    for key in ("hostname", "platform", "platform_release", "architecture"):
        assert key in data
    assert data["platform"]  # Darwin / Linux / Windows


def test_cpu_metrics_shape():
    data = _load(t.collect_cpu_metrics())
    assert data["success"] is True
    assert "cpu_percent" in data
    assert 0 <= data["cpu_percent"] <= 100
    assert data["cpu_cores"] >= 1


def test_memory_metrics_shape():
    data = _load(t.collect_memory_metrics())
    assert data["success"] is True
    assert data["total_bytes"] > 0
    assert data["used_bytes"] >= 0


def test_disk_metrics_shape():
    data = _load(t.collect_disk_metrics())
    assert data["success"] is True
    assert data["total_bytes"] > 0
    assert data["free_bytes"] >= 0
    assert data["used_bytes"] >= 0
    assert data["total_bytes"] >= data["free_bytes"] + data["used_bytes"] - 1


def test_network_metrics_shape():
    data = _load(t.collect_network_metrics())
    assert data["success"] is True
    assert data["established_connections"] >= 0
    assert isinstance(data["interfaces"], list)


def test_process_metrics_shape():
    data = _load(t.collect_process_metrics())
    assert data["success"] is True
    assert isinstance(data["top_processes"], list)
    assert len(data["top_processes"]) > 0


def test_security_shape():
    data = _load(t.check_security_status())
    assert data["success"] is True
    assert isinstance(data["listening_ports"], list)


def test_logs_shape():
    data = _load(t.analyze_logs(minutes=5, limit=3))
    assert data["success"] is True
    assert "error_count" in data
    assert "lookback_minutes" in data


def test_cloud_shape():
    data = _load(t.check_cloud_status())
    assert data["success"] is True
    assert "provider" in data


# ---------------------------------------------------------------------------
# run_diagnostic safety
# ---------------------------------------------------------------------------


def test_diagnostic_requires_command():
    data = _load(t.run_diagnostic())
    assert data["success"] is False
    assert "required" in data["error"]


def test_diagnostic_runs_simple_command():
    data = _load(t.run_diagnostic(command="echo hello-pace"))
    assert data["success"] is True
    assert data["exit_code"] == 0
    assert "hello-pace" in data["stdout"]


def test_diagnostic_blocks_rm_rf():
    data = _load(t.run_diagnostic(command="rm -rf /"))
    assert data["success"] is False
    assert "blocked" in data["error"]


def test_diagnostic_blocks_reboot():
    data = _load(t.run_diagnostic(command="reboot"))
    assert data["success"] is False


def test_diagnostic_blocks_dd():
    data = _load(t.run_diagnostic(command="dd if=/dev/zero of=/dev/sda"))
    assert data["success"] is False


def test_diagnostic_blocks_forkbomb():
    data = _load(t.run_diagnostic(command=":(){ :|:& };:"))
    assert data["success"] is False


def test_diagnostic_blocks_mkfs():
    data = _load(t.run_diagnostic(command="mkfs.ext4 /dev/sdb1"))
    assert data["success"] is False


def test_diagnostic_timeout_clamped():
    data = _load(t.run_diagnostic(command="echo hi", timeout_seconds=9999))
    assert data["timeout_seconds"] == 120


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def test_ok_error_helpers():
    assert json.loads(t._ok(a=1)) == {"success": True, "a": 1}
    assert json.loads(t._error("boom")) == {"success": False, "error": "boom"}


def test_clamp_int():
    assert t._clamp_int("abc", default=5, minimum=1, maximum=10) == 5
    assert t._clamp_int(0, default=5, minimum=1, maximum=10) == 1
    assert t._clamp_int(99, default=5, minimum=1, maximum=10) == 10
    assert t._clamp_int(7, default=5, minimum=1, maximum=10) == 7


def test_safe_run_captures_output():
    rc, out, err = t._safe_run(["echo", "captured"], timeout=5)
    assert rc == 0
    assert "captured" in out


def test_safe_run_handles_missing_binary():
    rc, out, err = t._safe_run(["/nonexistent/binary-xyz"], timeout=5)
    assert rc != 0
