"""
PACE Atlas — Configuration

Config resolution order (lowest to highest priority):

1. DEFAULT_CONFIG built-in defaults
2. YAML config file (default: ~/.pace/config.yaml, overridable via --config)
3. Environment variables (API keys)
4. Runtime overrides (CLI args / programmatic)

API keys are read from the environment (GROQ_API_KEY, OPENAI_API_KEY,
ANTHROPIC_API_KEY) or from ~/.pace/.env in the same KEY=VALUE format.
"""

import os
import socket
from pathlib import Path
from typing import Any, Optional


def pace_home() -> Path:
    """Return the PACE config/data directory (~/.pace unless PACE_HOME set)."""
    return Path(os.environ.get("PACE_HOME", str(Path.home() / ".pace")))


def default_config_path() -> Path:
    return pace_home() / "config.yaml"


DEFAULT_CONFIG: dict[str, Any] = {
    "server_name": socket.gethostname() or "server",
    "check_interval": 300,
    "llm": {
        "provider": None,
        "model": None,
        "base_url": None,
        "max_tokens": 500,
    },
    "hard_rules": {
        "disk_threshold": 95,
        "memory_threshold": 95,
        "cpu_threshold": 95,
        "cpu_duration_minutes": 5,
        "ssh_threshold": 10,
        "ssh_window_minutes": 10,
        "billing_threshold": 50,
    },
    "notifications": {
        "channels": ["console"],
        "file": {"path": "~/.pace/alerts.log"},
        "webhook": {"url": None},
        "telegram": {"bot_token": None, "chat_id": None},
        "email": {
            "host": None,
            "port": 587,
            "username": None,
            "password": None,
            "from": None,
            "to": [],
        },
    },
    "alerts": {
        "history_file": "~/.pace/history.jsonl",
        "dedupe_window_seconds": 300,
        "suppress_repeats": True,
        "max_history_entries": 5000,
    },
    "telemetry": {},
}


def deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into a copy of base."""
    result = dict(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _read_env_file(path: Path) -> dict[str, str]:
    """Read KEY=VALUE lines from an env file (~/.pace/.env)."""
    values: dict[str, str] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip()
    return values


def resolve_llm_settings(config: dict) -> dict:
    """Infer LLM provider/model from env vars when not set in config."""
    env = dict(os.environ)
    for key, value in _read_env_file(pace_home() / ".env").items():
        env.setdefault(key, value)

    llm = dict(config.get("llm") or {})

    if not llm.get("provider"):
        for provider, key in (
            ("groq", "GROQ_API_KEY"),
            ("openai", "OPENAI_API_KEY"),
            ("anthropic", "ANTHROPIC_API_KEY"),
        ):
            if env.get(key):
                llm["provider"] = provider
                llm["api_key"] = env[key]
                break

    if not llm.get("model"):
        defaults = {
            "groq": "llama-3.3-70b-versatile",
            "openai": "gpt-4o-mini",
            "anthropic": "claude-3-5-haiku-latest",
        }
        llm["model"] = defaults.get(llm.get("provider"))

    return llm


def load_config(path: Optional[str] = None, overrides: Optional[dict] = None) -> dict:
    """Load and merge config from file, env, and overrides."""
    config = dict(DEFAULT_CONFIG)

    config_path = Path(path) if path else default_config_path()
    if config_path.exists():
        try:
            import yaml
        except ImportError:
            raise RuntimeError(
                "PyYAML is required to load config files; install it or use defaults"
            )
        with open(config_path, encoding="utf-8") as f:
            file_config = yaml.safe_load(f) or {}
        config = deep_merge(config, file_config)

    if overrides:
        config = deep_merge(config, overrides)

    config["llm"] = resolve_llm_settings(config)
    return config


def install_default_config(force: bool = False) -> Path:
    """Write the sample config to ~/.pace/config.yaml if absent."""
    target = default_config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and not force:
        return target
    sample = Path(__file__).parent / "config.example.yaml"
    if sample.exists():
        target.write_text(sample.read_text(encoding="utf-8"), encoding="utf-8")
    else:
        target.write_text(_render_default_yaml(), encoding="utf-8")
    return target


def _render_default_yaml() -> str:
    """Fallback YAML render when the sample file is missing."""
    lines = [
        "# PACE Atlas configuration (see docs in config.example.yaml)",
        "server_name: " + (DEFAULT_CONFIG["server_name"] or "server"),
        "check_interval: 300",
        "hard_rules:",
        "  disk_threshold: 95",
        "  memory_threshold: 95",
        "  cpu_threshold: 95",
        "notifications:",
        "  channels: [console]",
        "  # telegram:",
        "  #   bot_token: <TOKEN>",
        "  #   chat_id: <CHAT_ID>",
        "",
    ]
    return "\n".join(lines)
