#!/usr/bin/env python3
"""
PACE Atlas telemetry tools.

These tools are registered into Hermes' tool registry under the
`pace_atlas` toolset so the LLM can decide what to inspect at runtime.
"""

from __future__ import annotations

import inspect
import json
import logging
import os
import platform
import re
import shutil
import subprocess
import time
import urllib.request
from collections import deque
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)


def _ok(**payload: Any) -> str:
    return json.dumps({"success": True, **payload})


def _error(message: str, **payload: Any) -> str:
    return json.dumps({"success": False, "error": message, **payload})


def _safe_run(command: list[str], timeout: int = 10) -> tuple[int, str, str]:
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return completed.returncode, completed.stdout or "", completed.stderr or ""
    except Exception as exc:
        return 1, "", str(exc)


def _clamp_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        n = int(value)
    except Exception:
        return default
    return max(minimum, min(maximum, n))


def _register_tool(
    *,
    name: str,
    description: str,
    parameters: dict[str, Any],
    function: Callable[..., str],
) -> None:
    """Register a pace tool with a registry-compatible wrapper."""
    try:
        from tools.registry import registry
    except ModuleNotFoundError:
        # Standalone use (PyPI wheel / scripts): the hermes tools registry is
        # not installed, so registration is skipped without failing import.
        return

    def _handler(args: dict[str, Any] | None, **kwargs: Any) -> str:
        payload: dict[str, Any] = {}
        if isinstance(args, dict):
            payload.update(args)
        payload.update(kwargs)

        try:
            result = function(**payload)
        except TypeError:
            # Defensive fallback if the function has a strict signature.
            signature = inspect.signature(function)
            accepts_var_kw = any(
                p.kind == inspect.Parameter.VAR_KEYWORD
                for p in signature.parameters.values()
            )
            if accepts_var_kw:
                result = function(**payload)
            else:
                filtered = {
                    key: value
                    for key, value in payload.items()
                    if key in signature.parameters
                }
                result = function(**filtered)
        except Exception as exc:
            logger.exception("PACE tool %s failed", name)
            return _error(str(exc))

        if isinstance(result, str):
            return result
        return json.dumps(result)

    registry.register(
        name=name,
        toolset="pace_atlas",
        schema={
            "name": name,
            "description": description,
            "parameters": parameters,
        },
        handler=_handler,
        check_fn=None,
        requires_env=[],
        is_async=False,
        description=description,
        emoji="PA",
    )


def get_system_info(**_: Any) -> str:
    system = platform.system()
    payload: dict[str, Any] = {
        "hostname": platform.node(),
        "platform": system,
        "platform_release": platform.release(),
        "platform_version": platform.version(),
        "architecture": platform.machine(),
        "python_version": platform.python_version(),
    }

    if system == "Linux":
        try:
            with open("/proc/uptime", "r", encoding="utf-8") as f:
                uptime_seconds = float(f.readline().split()[0])
            days = int(uptime_seconds // 86400)
            hours = int((uptime_seconds % 86400) // 3600)
            minutes = int((uptime_seconds % 3600) // 60)
            payload["uptime"] = f"{days}d {hours}h {minutes}m"
        except Exception:
            pass
    elif system == "Darwin":
        rc, out, _ = _safe_run(["uptime"], timeout=5)
        if rc == 0 and out.strip():
            payload["uptime"] = out.strip()

    return _ok(**payload)


def collect_cpu_metrics(**_: Any) -> str:
    system = platform.system()
    cpu_percent: float | None = None
    cpu_idle_percent: float | None = None

    if system == "Linux":
        try:
            with open("/proc/stat", "r", encoding="utf-8") as f:
                first = f.readline().split()[1:]
            t1 = [int(x) for x in first]
            idle1 = t1[3] + (t1[4] if len(t1) > 4 else 0)
            total1 = sum(t1)
            time.sleep(0.2)
            with open("/proc/stat", "r", encoding="utf-8") as f:
                second = f.readline().split()[1:]
            t2 = [int(x) for x in second]
            idle2 = t2[3] + (t2[4] if len(t2) > 4 else 0)
            total2 = sum(t2)
            delta_total = max(1, total2 - total1)
            delta_idle = max(0, idle2 - idle1)
            cpu_percent = round((1.0 - (delta_idle / delta_total)) * 100.0, 1)
            cpu_idle_percent = round(100.0 - cpu_percent, 1)
        except Exception:
            pass

    elif system == "Darwin":
        rc, out, _ = _safe_run(["top", "-l", "1", "-n", "0"], timeout=10)
        if rc == 0:
            match = re.search(
                r"CPU usage:\s*([\d.]+)% user,\s*([\d.]+)% sys,\s*([\d.]+)% idle",
                out,
            )
            if match:
                user_pct = float(match.group(1))
                sys_pct = float(match.group(2))
                idle_pct = float(match.group(3))
                cpu_percent = round(user_pct + sys_pct, 1)
                cpu_idle_percent = round(idle_pct, 1)

    load_average: list[float] | None = None
    try:
        load_average = [round(x, 2) for x in os.getloadavg()]
    except Exception:
        pass

    return _ok(
        platform=system,
        cpu_percent=cpu_percent,
        cpu_idle_percent=cpu_idle_percent,
        cpu_cores=os.cpu_count() or 1,
        load_average=load_average,
    )


def collect_memory_metrics(**_: Any) -> str:
    system = platform.system()

    if system == "Linux":
        try:
            mem_info: dict[str, int] = {}
            with open("/proc/meminfo", "r", encoding="utf-8") as f:
                for line in f:
                    key, value = line.split(":", 1)
                    mem_info[key.strip()] = int(value.strip().split()[0]) * 1024

            total_bytes = mem_info.get("MemTotal", 0)
            available_bytes = mem_info.get("MemAvailable", mem_info.get("MemFree", 0))
            used_bytes = max(0, total_bytes - available_bytes)
            swap_total_bytes = mem_info.get("SwapTotal", 0)
            swap_free_bytes = mem_info.get("SwapFree", 0)
            swap_used_bytes = max(0, swap_total_bytes - swap_free_bytes)

            usage_percent = (
                round((used_bytes / total_bytes) * 100.0, 1) if total_bytes else 0.0
            )

            return _ok(
                platform=system,
                total_bytes=total_bytes,
                used_bytes=used_bytes,
                available_bytes=available_bytes,
                usage_percent=usage_percent,
                swap_total_bytes=swap_total_bytes,
                swap_used_bytes=swap_used_bytes,
            )
        except Exception as exc:
            return _error(str(exc), platform=system)

    if system == "Darwin":
        try:
            rc_memsize, out_memsize, _ = _safe_run(
                ["sysctl", "-n", "hw.memsize"], timeout=5
            )
            total_bytes = (
                int(out_memsize.strip())
                if rc_memsize == 0 and out_memsize.strip().isdigit()
                else 0
            )

            rc_pagesize, out_pagesize, _ = _safe_run(
                ["sysctl", "-n", "hw.pagesize"], timeout=5
            )
            page_size = (
                int(out_pagesize.strip())
                if rc_pagesize == 0 and out_pagesize.strip().isdigit()
                else 4096
            )

            rc_vmstat, out_vmstat, _ = _safe_run(["vm_stat"], timeout=10)
            if rc_vmstat != 0:
                return _error("vm_stat command failed", platform=system)

            pages: dict[str, int] = {}
            for line in out_vmstat.splitlines():
                if ":" not in line:
                    continue
                key, value = line.split(":", 1)
                key = key.strip()
                value = value.strip().rstrip(".")
                if value.isdigit():
                    pages[key] = int(value)

            free_pages = pages.get("Pages free", 0)
            inactive_pages = pages.get("Pages inactive", 0)
            speculative_pages = pages.get("Pages speculative", 0)
            active_pages = pages.get("Pages active", 0)
            wired_pages = pages.get("Pages wired down", 0)
            compressed_pages = pages.get("Pages occupied by compressor", 0)

            available_bytes = (
                free_pages + inactive_pages + speculative_pages
            ) * page_size
            used_bytes = (active_pages + wired_pages + compressed_pages) * page_size

            if total_bytes <= 0:
                total_bytes = max(used_bytes + available_bytes, 1)
            usage_percent = round((used_bytes / total_bytes) * 100.0, 1)

            return _ok(
                platform=system,
                total_bytes=total_bytes,
                used_bytes=used_bytes,
                available_bytes=available_bytes,
                usage_percent=usage_percent,
            )
        except Exception as exc:
            return _error(str(exc), platform=system)

    return _error("unsupported platform", platform=system)


def collect_disk_metrics(path: str = "/", **_: Any) -> str:
    system = platform.system()
    target = path or "/"
    try:
        usage = shutil.disk_usage(target)
    except Exception as exc:
        return _error(str(exc), platform=system, path=target)

    usage_percent = round((usage.used / usage.total) * 100.0, 1) if usage.total else 0.0
    return _ok(
        platform=system,
        path=target,
        total_bytes=usage.total,
        used_bytes=usage.used,
        free_bytes=usage.free,
        usage_percent=usage_percent,
    )


def collect_network_metrics(interface_limit: int = 8, **_: Any) -> str:
    system = platform.system()
    limit = _clamp_int(interface_limit, default=8, minimum=1, maximum=32)

    established = 0
    listening = 0
    interfaces: list[dict[str, Any]] = []

    if system == "Linux":
        rc, out, _ = _safe_run(["ss", "-tan"], timeout=10)
        if rc == 0:
            for line in out.splitlines():
                if "ESTAB" in line:
                    established += 1
                elif "LISTEN" in line:
                    listening += 1

        net_dir = Path("/sys/class/net")
        if net_dir.exists():
            for iface in sorted(net_dir.iterdir()):
                if not iface.is_dir():
                    continue
                stats = iface / "statistics"
                rx = tx = None
                if stats.exists():
                    try:
                        rx = int(
                            (stats / "rx_bytes").read_text(encoding="utf-8").strip()
                        )
                        tx = int(
                            (stats / "tx_bytes").read_text(encoding="utf-8").strip()
                        )
                    except Exception:
                        pass
                interfaces.append({"name": iface.name, "rx_bytes": rx, "tx_bytes": tx})

    elif system == "Darwin":
        rc, out, _ = _safe_run(["netstat", "-an"], timeout=10)
        if rc == 0:
            for line in out.splitlines():
                if "ESTABLISHED" in line:
                    established += 1
                elif "LISTEN" in line:
                    listening += 1

        rc_if, out_if, _ = _safe_run(["ifconfig", "-l"], timeout=5)
        if rc_if == 0:
            for name in out_if.strip().split():
                interfaces.append({"name": name})

    return _ok(
        platform=system,
        established_connections=established,
        listening_sockets=listening,
        interfaces=interfaces[:limit],
        interface_count=len(interfaces),
    )


def collect_process_metrics(limit: int = 10, **_: Any) -> str:
    system = platform.system()
    max_rows = _clamp_int(limit, default=10, minimum=1, maximum=25)

    if system == "Linux":
        cmd = ["ps", "-eo", "pid,pcpu,pmem,comm", "--sort=-pcpu"]
    elif system == "Darwin":
        cmd = ["ps", "-Ao", "pid,pcpu,pmem,comm", "-r"]
    else:
        return _error("unsupported platform", platform=system)

    rc, out, err = _safe_run(cmd, timeout=10)
    if rc != 0:
        return _error(f"process command failed: {err.strip()}", platform=system)

    rows = out.splitlines()
    processes: list[dict[str, Any]] = []
    for row in rows[1 : max_rows + 1]:
        parts = row.split(None, 3)
        if len(parts) < 4:
            continue
        pid, cpu, mem, command = parts
        try:
            processes.append(
                {
                    "pid": int(pid),
                    "cpu_percent": float(cpu),
                    "memory_percent": float(mem),
                    "command": command,
                }
            )
        except Exception:
            continue

    return _ok(platform=system, top_processes=processes)


def check_security_status(**_: Any) -> str:
    system = platform.system()
    listening_ports: set[int] = set()
    warnings: list[str] = []

    if system == "Linux":
        rc, out, _ = _safe_run(["ss", "-tln"], timeout=10)
        if rc == 0:
            for line in out.splitlines():
                if "LISTEN" not in line:
                    continue
                parts = line.split()
                if len(parts) < 4:
                    continue
                address = parts[3]
                if ":" not in address:
                    continue
                port_text = address.rsplit(":", 1)[-1].strip("[]")
                if port_text.isdigit():
                    listening_ports.add(int(port_text))

    elif system == "Darwin":
        rc, out, _ = _safe_run(["lsof", "-nP", "-iTCP", "-sTCP:LISTEN"], timeout=10)
        if rc == 0:
            for line in out.splitlines()[1:]:
                match = re.search(r":(\d+)\s*\(LISTEN\)", line)
                if match:
                    listening_ports.add(int(match.group(1)))

    risky_ports = sorted(p for p in listening_ports if p in {21, 23, 3389, 5900})
    if risky_ports:
        warnings.append(f"Potentially risky ports listening: {risky_ports}")

    return _ok(
        platform=system,
        listening_ports=sorted(listening_ports),
        open_port_count=len(listening_ports),
        warnings=warnings,
    )


def analyze_logs(minutes: int = 30, limit: int = 20, **_: Any) -> str:
    system = platform.system()
    lookback = _clamp_int(minutes, default=30, minimum=5, maximum=240)
    max_items = _clamp_int(limit, default=20, minimum=1, maximum=60)

    errors: list[str] = []
    warnings: list[str] = []

    def _ingest_line(line: str) -> None:
        text = line.strip()
        if not text:
            return
        lowered = text.lower()
        if ("error" in lowered or "fail" in lowered) and len(errors) < max_items:
            errors.append(text[:300])
        elif "warn" in lowered and len(warnings) < max_items:
            warnings.append(text[:300])

    if system == "Linux":
        if shutil.which("journalctl"):
            rc, out, _ = _safe_run(
                [
                    "journalctl",
                    "--since",
                    f"-{lookback} min",
                    "-n",
                    str(max_items * 10),
                    "--no-pager",
                ],
                timeout=15,
            )
            if rc == 0:
                for line in out.splitlines():
                    _ingest_line(line)
        else:
            candidates = ["/var/log/syslog", "/var/log/messages", "/var/log/dmesg"]
            for log_path in candidates:
                path = Path(log_path)
                if not path.exists():
                    continue
                try:
                    with open(path, "r", encoding="utf-8", errors="ignore") as f:
                        for line in deque(f, maxlen=max_items * 20):
                            _ingest_line(line)
                except Exception:
                    continue

    elif system == "Darwin":
        if shutil.which("log"):
            rc, out, _ = _safe_run(
                [
                    "log",
                    "show",
                    "--last",
                    f"{lookback}m",
                    "--style",
                    "compact",
                    "--predicate",
                    "eventMessage CONTAINS[c] 'error' OR eventMessage CONTAINS[c] 'fail' OR eventMessage CONTAINS[c] 'warn'",
                ],
                timeout=20,
            )
            if rc == 0:
                for line in out.splitlines():
                    _ingest_line(line)

    return _ok(
        platform=system,
        lookback_minutes=lookback,
        error_count=len(errors),
        warning_count=len(warnings),
        recent_errors=errors[:max_items],
        recent_warnings=warnings[:max_items],
    )


def check_cloud_status(**_: Any) -> str:
    system = platform.system()
    provider = None
    evidence: list[str] = []

    env_signals = [
        ("AWS_EXECUTION_ENV", "aws"),
        ("GOOGLE_CLOUD_PROJECT", "gcp"),
        ("AZURE_HTTP_USER_AGENT", "azure"),
        ("DIGITALOCEAN", "digitalocean"),
    ]
    for env_key, inferred in env_signals:
        if os.getenv(env_key):
            provider = inferred
            evidence.append(f"environment variable detected: {env_key}")
            break

    if system == "Linux":
        dmi_path = Path("/sys/class/dmi/id/product_name")
        if dmi_path.exists():
            try:
                product = (
                    dmi_path.read_text(encoding="utf-8", errors="ignore")
                    .strip()
                    .lower()
                )
                if any(x in product for x in ("amazon", "ec2", "aws")):
                    provider = provider or "aws"
                    evidence.append("dmi product indicates aws")
                elif any(x in product for x in ("google", "gce")):
                    provider = provider or "gcp"
                    evidence.append("dmi product indicates gcp")
                elif "azure" in product:
                    provider = provider or "azure"
                    evidence.append("dmi product indicates azure")
            except Exception:
                pass

    # Metadata probes (very short timeout to avoid hangs).
    probes = [
        ("aws", "http://169.254.169.254/latest/meta-data/", {}),
        (
            "gcp",
            "http://metadata.google.internal/computeMetadata/v1/",
            {"Metadata-Flavor": "Google"},
        ),
        (
            "azure",
            "http://169.254.169.254/metadata/instance?api-version=2021-02-01",
            {"Metadata": "true"},
        ),
    ]

    for probe_provider, url, headers in probes:
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=1) as _:
                provider = provider or probe_provider
                evidence.append(f"metadata endpoint reachable: {probe_provider}")
                break
        except Exception:
            continue

    return _ok(platform=system, provider=provider, evidence=evidence)


_BLOCKED_DIAGNOSTIC_PATTERN = re.compile(
    r"(rm\s+-rf|mkfs(\.[a-z0-9]+)?|\breboot\b|\bshutdown\b|\bpoweroff\b|\bhalt\b|dd\s+if=|:\(\)\s*\{|:\s*\(\)\s*\{)",
    re.IGNORECASE,
)


def run_diagnostic(
    command: str | None = None, timeout_seconds: int = 20, **_: Any
) -> str:
    if not command:
        return _error("command is required")

    if _BLOCKED_DIAGNOSTIC_PATTERN.search(command):
        return _error("command blocked for safety", command=command)

    timeout = _clamp_int(timeout_seconds, default=20, minimum=1, maximum=120)

    try:
        completed = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except Exception as exc:
        return _error(str(exc), command=command)

    return _ok(
        command=command,
        timeout_seconds=timeout,
        exit_code=completed.returncode,
        stdout=(completed.stdout or "")[:6000],
        stderr=(completed.stderr or "")[:2000],
    )


def register_all_tools() -> None:
    _register_tool(
        name="pace_get_system_info",
        description="Get hostname, operating system, architecture, and uptime",
        parameters={"type": "object", "properties": {}, "required": []},
        function=get_system_info,
    )

    _register_tool(
        name="pace_collect_cpu",
        description="Collect CPU usage, idle percentage, core count, and load averages",
        parameters={"type": "object", "properties": {}, "required": []},
        function=collect_cpu_metrics,
    )

    _register_tool(
        name="pace_collect_memory",
        description="Collect memory utilization (total, used, available, swap where available)",
        parameters={"type": "object", "properties": {}, "required": []},
        function=collect_memory_metrics,
    )

    _register_tool(
        name="pace_collect_disk",
        description="Collect disk usage metrics for a path",
        parameters={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Filesystem path to inspect (default: /)",
                }
            },
            "required": [],
        },
        function=collect_disk_metrics,
    )

    _register_tool(
        name="pace_collect_network",
        description="Collect network connection counts and interface stats",
        parameters={
            "type": "object",
            "properties": {
                "interface_limit": {
                    "type": "integer",
                    "description": "Maximum interfaces returned (default: 8)",
                }
            },
            "required": [],
        },
        function=collect_network_metrics,
    )

    _register_tool(
        name="pace_collect_processes",
        description="Collect top processes by CPU and memory",
        parameters={
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Maximum processes returned (default: 10)",
                }
            },
            "required": [],
        },
        function=collect_process_metrics,
    )

    _register_tool(
        name="pace_check_security",
        description="Inspect open listening ports and return security warnings",
        parameters={"type": "object", "properties": {}, "required": []},
        function=check_security_status,
    )

    _register_tool(
        name="pace_analyze_logs",
        description="Scan recent system logs for error and warning patterns",
        parameters={
            "type": "object",
            "properties": {
                "minutes": {
                    "type": "integer",
                    "description": "Log lookback window in minutes (default: 30)",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum errors/warnings returned per category (default: 20)",
                },
            },
            "required": [],
        },
        function=analyze_logs,
    )

    _register_tool(
        name="pace_check_cloud",
        description="Detect cloud provider signals and metadata availability",
        parameters={"type": "object", "properties": {}, "required": []},
        function=check_cloud_status,
    )

    _register_tool(
        name="pace_run_diagnostic",
        description="Run a non-destructive diagnostic shell command",
        parameters={
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Command to execute",
                },
                "timeout_seconds": {
                    "type": "integer",
                    "description": "Command timeout in seconds (default: 20)",
                },
            },
            "required": ["command"],
        },
        function=run_diagnostic,
    )


register_all_tools()
