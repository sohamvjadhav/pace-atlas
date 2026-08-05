"""Tests for pace_atlas.config: defaults, env inference, file merge."""
from pathlib import Path

from pace_atlas import config


def test_default_config_baseline(monkeypatch, tmp_path):
    monkeypatch.setenv("PACE_HOME", str(tmp_path))
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    cfg = config.load_config()
    assert cfg["check_interval"] == 300
    assert "disk_threshold" in cfg["hard_rules"]
    assert cfg["server_name"]
    assert cfg["llm"]["provider"] is None
    assert cfg["llm"]["model"] is None


def test_env_infers_provider_and_default_model(monkeypatch, tmp_path):
    monkeypatch.setenv("PACE_HOME", str(tmp_path))
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    cfg = config.load_config()
    assert cfg["llm"]["provider"] == "groq"
    assert cfg["llm"]["model"] == "llama-3.3-70b-versatile"
    assert cfg["llm"]["api_key"] == "test-key"


def test_env_file_is_read(monkeypatch, tmp_path):
    (tmp_path / ".env").write_text("OPENAI_API_KEY=sk-envfile\nPACE_EXTRA=1\n")
    monkeypatch.setenv("PACE_HOME", str(tmp_path))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    cfg = config.load_config()
    assert cfg["llm"]["provider"] == "openai"
    assert cfg["llm"]["api_key"] == "sk-envfile"


def test_file_config_overrides_defaults(monkeypatch, tmp_path):
    monkeypatch.setenv("PACE_HOME", str(tmp_path))
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(
        "server_name: atlas-01\ncheck_interval: 60\nhard_rules:\n  disk_threshold: 80\n"
    )
    cfg = config.load_config(str(cfg_path))
    assert cfg["server_name"] == "atlas-01"
    assert cfg["check_interval"] == 60
    assert cfg["hard_rules"]["disk_threshold"] == 80


def test_overrides_win_over_file_and_defaults(monkeypatch, tmp_path):
    monkeypatch.setenv("PACE_HOME", str(tmp_path))
    cfg = config.load_config(overrides={"server_name": "cli-name", "check_interval": 999})
    assert cfg["server_name"] == "cli-name"
    assert cfg["check_interval"] == 999


def test_dotenv_never_overrides_explicit_env(monkeypatch, tmp_path):
    (tmp_path / ".env").write_text("OPENAI_API_KEY=sk-dotenv\n")
    monkeypatch.setenv("PACE_HOME", str(tmp_path))
    monkeypatch.setenv("OPENAI_API_KEY", "sk-real")
    cfg = config.load_config()
    assert cfg["llm"]["api_key"] == "sk-real"


def test_install_default_config(monkeypatch, tmp_path):
    monkeypatch.setenv("PACE_HOME", str(tmp_path))
    path = config.install_default_config()
    assert Path(path).exists()
    content = Path(path).read_text()
    assert "server_name:" in content
    assert "check_interval:" in content