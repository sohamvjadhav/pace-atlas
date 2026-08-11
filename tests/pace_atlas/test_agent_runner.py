"""Tests for pace_atlas.agent_runner: LLM decision parsing and monitoring loop."""
import json

import pytest

from pace_atlas.agent_runner import PACEAtlasAgent


def make_agent(**attrs):
    agent = object.__new__(PACEAtlasAgent)
    agent.config = {"server_name": "web-prod-01"}
    agent.server_name = "web-prod-01"
    for key, value in attrs.items():
        setattr(agent, key, value)
    return agent


# ---------------------------------------------------------------------------
# _parse_decision
# ---------------------------------------------------------------------------


def parse(response):
    agent = make_agent()
    return agent._parse_decision(response)


def test_parse_clean_alert_json():
    payload = json.dumps(
        {
            "decision": "ALERT",
            "severity": "critical",
            "reason": "disk at 95%",
            "summary": "filled up",
            "suggested_actions": ["clean logs"],
        }
    )
    d = parse(payload)
    assert d.should_alert is True
    assert d.severity == "critical"
    assert d.alert_type == "issue"
    assert "95%" in d.reason


def test_parse_clean_silent_json():
    d = parse('{"decision": "SILENT", "severity": "info", "reason": "all quiet"}')
    assert d.should_alert is False
    assert d.severity == "info"
    assert d.alert_type == "none"


def test_parse_json_in_code_fence():
    response = 'Here is my assessment:\n```json\n{"decision": "ALERT", "severity": "warning", "reason": "mem pressure"}\n```\n'
    d = parse(response)
    assert d.should_alert is True
    assert d.severity == "warning"


def test_parse_empty_response_alerts():
    d = parse("")
    assert d.should_alert is True
    assert "empty" in d.reason.lower()
    assert d.alert_type == "error"


def test_parse_none_response_alerts():
    d = parse(None)
    assert d.should_alert is True


def test_parse_tool_failure_alerts():
    d = parse("Tool execution failed: disk collector crashed")
    assert d.should_alert is True
    assert d.alert_type == "error"
    assert "tool" in d.reason.lower()


def test_parse_bare_alert_word():
    d = parse("I recommend ALERT on this one")
    assert d.should_alert is True


def test_parse_bare_silent_word():
    d = parse("Everything looks fine, recommending SILENT")
    assert d.should_alert is False


def test_parse_both_words_defaults_silent():
    d = parse("consider ALERT but likely SILENT")
    assert d.should_alert is False


def test_parse_invalid_severity_defaults_warning_on_alert():
    d = parse('{"decision": "ALERT", "severity": "catastrophic", "reason": "x"}')
    assert d.severity == "warning"


def test_parse_invalid_severity_defaults_info_on_silent():
    d = parse('{"decision": "SILENT", "severity": "loud", "reason": "x"}')
    assert d.severity == "info"


def test_parse_malformed_json_falls_back_silent():
    d = parse("{not json at all")
    assert d.should_alert is False


def test_parse_long_reason_truncated():
    d = parse(json.dumps({"decision": "ALERT", "reason": "x" * 800}))
    assert len(d.reason) == 500


def test_parse_uses_summary_when_no_reason():
    d = parse('{"decision": "SILENT", "summary": "summary-based reason"}')
    assert "summary-based" in d.reason


# ---------------------------------------------------------------------------
# _build_monitoring_prompt
# ---------------------------------------------------------------------------


def test_prompt_includes_server_and_time():
    agent = make_agent()
    prompt = agent._build_monitoring_prompt({})
    assert "web-prod-01" in prompt
    assert "monitoring cycle" in prompt


def test_prompt_includes_feedback_context():
    agent = make_agent()
    ctx = {
        "recent_alerts": ["disk alert at 20:00"],
        "learned_patterns": ["nightly backup spike"],
    }
    prompt = agent._build_monitoring_prompt(ctx)
    assert "disk alert at 20:00" in prompt
    assert "nightly backup spike" in prompt


def test_prompt_omits_empty_feedback():
    agent = make_agent()
    prompt = agent._build_monitoring_prompt({"recent_alerts": [], "learned_patterns": []})
    assert "Recent alerts:" not in prompt
    assert "Learned patterns:" not in prompt


# ---------------------------------------------------------------------------
# run_once with a stubbed agent
# ---------------------------------------------------------------------------


def test_run_once_silent_does_not_record_feedback():
    class FakeAgent:
        def chat(self, prompt):
            return '{"decision": "SILENT", "severity": "info", "reason": "healthy"}'

    class FakeFeedback:
        def __init__(self):
            self.calls = []

        def get_context(self):
            return {}

        def record_feedback(self, *args):
            self.calls.append(args)

    agent = make_agent()
    agent.agent = FakeAgent()
    agent.feedback = FakeFeedback()
    agent._send_alert = lambda d: None

    d = agent.run_once()
    assert d.should_alert is False
    assert agent.feedback.calls == []


def test_run_once_alert_records_feedback():
    class FakeAgent:
        def chat(self, prompt):
            return '{"decision": "ALERT", "severity": "critical", "reason": "load spike"}'

    class FakeFeedback:
        def __init__(self):
            self.calls = []

        def get_context(self):
            return {}

        def record_feedback(self, *args):
            self.calls.append(args)

    sent = []
    agent = make_agent()
    agent.agent = FakeAgent()
    agent.feedback = FakeFeedback()
    agent._send_alert = lambda d: sent.append(d)

    d = agent.run_once()
    assert d.should_alert is True
    assert agent.feedback.calls == [("llm_decision", "useful", "load spike")]
    assert sent == [d]


def test_run_once_returns_error_decision_on_exception():
    class ExplodingAgent:
        def chat(self, prompt):
            raise RuntimeError("connection refused")

    class FakeFeedback:
        def get_context(self):
            return {}

    agent = make_agent()
    agent.agent = ExplodingAgent()
    agent.feedback = FakeFeedback()

    d = agent.run_once()
    assert d.should_alert is True
    assert d.alert_type == "error"
    assert "connection refused" in d.reason
