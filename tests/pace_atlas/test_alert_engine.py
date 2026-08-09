"""Tests for pace_atlas.alert_engine: hard rules, LLM decision layer, parsing."""
from pace_atlas.alert_engine import AlertDecision, AlertEngine, HardRules


# ---------------------------------------------------------------------------
# HardRules
# ---------------------------------------------------------------------------


def test_disk_rule_fires_over_threshold():
    rules = HardRules({"disk_threshold": 80})
    decision = rules.check(
        {"disk": {"mount_points": [{"mount": "/", "usage_percent": 90}]}}
    )
    assert decision.should_alert is True
    assert decision.alert_type == "hard_rule"
    assert decision.severity == "critical"
    assert "Disk at 90%" in decision.reason


def test_disk_rule_silent_under_threshold():
    rules = HardRules({"disk_threshold": 80})
    decision = rules.check(
        {"disk": {"mount_points": [{"mount": "/", "usage_percent": 40}]}}
    )
    assert decision is None


def test_disk_rule_default_threshold():
    rules = HardRules({})
    assert rules.disk_threshold == 95
    decision = rules.check(
        {"disk": {"mount_points": [{"mount": "/", "usage_percent": 99}]}}
    )
    assert decision.should_alert is True


def test_cpu_rule_fires():
    rules = HardRules({"cpu_threshold": 90})
    decision = rules.check({"system": {"cpu_percent": 95.0}})
    assert decision.should_alert is True
    assert decision.severity == "warning"
    assert decision.details["cpu_percent"] == 95.0


def test_memory_rule_fires():
    rules = HardRules({"memory_threshold": 90})
    decision = rules.check({"memory": {"usage_percent": 93}})
    assert decision.should_alert is True


def test_ssh_bruteforce_rule_fires():
    rules = HardRules({"ssh_threshold": 10})
    decision = rules.check(
        {"security": {"ssh_failed_logins": 15, "ssh_failed_logins_10min": 15}}
    )
    assert decision.should_alert is True
    assert decision.severity == "critical"


def test_no_rules_no_decision():
    rules = HardRules({})
    decision = rules.check({"system": {"cpu_percent": 10.0}})
    assert decision is None


def test_configurable_thresholds():
    rules = HardRules({"cpu_threshold": 30, "disk_threshold": 50})
    assert rules.check({"system": {"cpu_percent": 40.0}}).should_alert is True
    assert rules.check({"system": {"cpu_percent": 20.0}}) is None
    assert (
        rules.check(
            {"disk": {"mount_points": [{"mount": "/", "usage_percent": 60}]}}
        ).should_alert
        is True
    )


def test_services_rule_fires():
    rules = HardRules({})
    decision = rules.check({"process": {"failed_services": ["nginx", "postgres"]}})
    assert decision.should_alert is True
    assert "nginx" in decision.reason


# ---------------------------------------------------------------------------
# AlertEngine.decide ordering
# ---------------------------------------------------------------------------


def test_hard_rule_wins_over_llm():
    engine = AlertEngine({"hard_rules": {"cpu_threshold": 90}})
    engine.set_llm_client(_FakeClient("SILENT: everything looks fine"), model="fake-model")
    decision = engine.decide([_snap("system", {"cpu_percent": 99.0})])
    assert decision.alert_type == "hard_rule"


def test_llm_consulted_when_no_hard_rule():
    engine = AlertEngine({"hard_rules": {"cpu_threshold": 99}})
    engine.set_llm_client(_FakeClient("ALERT: disk usage is rising"), model="fake-model")
    decision = engine.decide([_snap("system", {"cpu_percent": 30.0})])
    assert decision.alert_type == "llm_decision"
    assert decision.should_alert is True


def test_silent_when_no_llm_and_no_hard_rule():
    engine = AlertEngine({"hard_rules": {}})
    decision = engine.decide([_snap("system", {"cpu_percent": 5.0})])
    assert decision.should_alert is False
    assert decision.alert_type == "no_decision"


# ---------------------------------------------------------------------------
# LLM response parsing
# ---------------------------------------------------------------------------


def test_parse_all_quiet_is_silent():
    engine = AlertEngine()
    engine.set_llm_client(_FakeClient("irrelevant"), model="m")
    decision = engine._parse_llm_response("All quiet — no issues detected.")
    assert decision.should_alert is False
    assert decision.alert_type == "llm_decision"


def test_parse_alert_markers():
    engine = AlertEngine()
    decision = engine._parse_llm_response("ALERT: CPU spike detected")
    assert decision.should_alert is True
    assert decision.severity == "warning"


def test_parse_insight_is_not_alert():
    engine = AlertEngine()
    decision = engine._parse_llm_response("Insight: disk will fill in 3 days")
    assert decision.should_alert is False
    assert decision.alert_type == "llm_insight"


def test_parse_garbage_defaults_silent():
    engine = AlertEngine()
    decision = engine._parse_llm_response("lorem ipsum dolor sit amet")
    assert decision.should_alert is False
    assert decision.alert_type == "llm_default"


def test_llm_failure_returns_safe_silent():
    class BoomCompletions:
        def create(self, **kwargs):
            raise RuntimeError("network down")

    engine = AlertEngine({"hard_rules": {"cpu_threshold": 99}})
    client = _FakeClient("anything")
    client.chat._completions = BoomCompletions()
    engine.set_llm_client(client, model="m")
    decision = engine.decide([_snap("system", {"cpu_percent": 5.0})])
    assert decision.should_alert is False
    assert decision.alert_type == "llm_error"


def test_set_llm_client_defaults():
    engine = AlertEngine()
    engine.set_llm_client(object())
    assert engine.llm_model == "llama-3.3-70b-versatile"
    assert engine.llm_max_tokens == 500


def test_set_llm_client_custom():
    engine = AlertEngine()
    engine.set_llm_client(object(), model="gpt-4o-mini", max_tokens=300)
    assert engine.llm_model == "gpt-4o-mini"
    assert engine.llm_max_tokens == 300


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeClient:
    """Duck-typed OpenAI client returning a canned response."""

    def __init__(self, content: str):
        self.chat = _FakeChat(content)

    @property
    def completions(self):
        return self.chat


class _FakeChat:
    def __init__(self, content: str):
        self._content = content
        self.calls = []
        self._completions = self

    @property
    def completions(self):
        return self._completions

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return _FakeResponse(self._content)


class _FakeResponse:
    def __init__(self, content: str):
        self.choices = [_FakeChoice(content)]


class _FakeChoice:
    def __init__(self, content: str):
        self.message = _FakeMessage(content)


class _FakeMessage:
    def __init__(self, content: str):
        self.content = content


def _snap(name: str, data: dict):
    from pace_atlas.telemetry import TelemetrySnapshot

    return TelemetrySnapshot(collector_name=name, timestamp=0.0, data=data)
