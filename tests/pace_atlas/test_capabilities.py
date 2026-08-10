"""Tests for pace_atlas.capabilities analyzers: RCA, security, cost, predictive."""
import time

from pace_atlas.capabilities import (
    CostAnalyzer,
    HistoryTracker,
    PredictiveAnalyzer,
    RootCauseAnalyzer,
    SecurityAnalyzer,
)


# ---------------------------------------------------------------------------
# RootCauseAnalyzer
# ---------------------------------------------------------------------------


def test_rca_returns_chain_of_causation():
    rca = RootCauseAnalyzer()
    result = rca.analyze(
        "site went down",
        {"cpu_percent": 99, "memory": {"usage_percent": 98}},
        {"cpu_percent": 5, "memory": {"usage_percent": 20}},
        "process killed: OOM",
    )
    assert result.result_type == "rca"
    assert "site went down" in result.title
    assert len(result.recommendations) >= 1


def test_rca_uses_llm_persona_by_default():
    rca = RootCauseAnalyzer()
    result = rca.analyze("apache crashed", {}, {}, "segfault")
    assert "prompts.atlas_complete" in result.body or "LLM" in result.body


# ---------------------------------------------------------------------------
# SecurityAnalyzer
# ---------------------------------------------------------------------------


def test_ssh_bruteforce_detected():
    sec = SecurityAnalyzer()
    results = sec.analyze_security_event(
        {"ssh_failed_logins": 25, "ssh_failed_logins_10min": 25},
        {},
        "",
    )
    assert len(results) >= 1
    first = results[0]
    assert first.result_type == "alert" or first.result_type == "warning"
    assert "brute" in first.title.lower() or "ssh" in first.title.lower()


def test_ssh_quiet_when_low_failures():
    sec = SecurityAnalyzer()
    results = sec.analyze_security_event({"ssh_failed_logins": 1}, {}, "")
    assert len(results) == 0


def test_unusual_connections_flagged():
    sec = SecurityAnalyzer()
    results = sec.analyze_security_event(
        {"ssh_failed_logins": 0},
        {"connections_total": 15000},
        "",
    )
    assert len(results) >= 1
    assert "High Connection Count" in [r.title for r in results]


def test_connection_count_below_10k_not_flagged():
    sec = SecurityAnalyzer()
    results = sec.analyze_security_event(
        {"ssh_failed_logins": 0}, {"connections_total": 2000}, ""
    )
    assert len(results) == 0


def test_new_users_flagged():
    sec = SecurityAnalyzer()
    results = sec.analyze_security_event(
        {"new_users": ["malice"], "ssh_failed_logins": 0}, {}, ""
    )
    titles = [r.title.lower() for r in results]
    assert any("user" in t for t in titles)


# ---------------------------------------------------------------------------
# CostAnalyzer
# ---------------------------------------------------------------------------


def test_idle_instance_flagged():
    cost = CostAnalyzer()
    results = cost.analyze_cost(
        {"system": {"cpu_percent": 3}}, {}, HistoryTracker("/tmp/pace-cost-1")
    )
    titles = [r.title.lower() for r in results]
    assert any("idle" in t for t in titles)


def test_high_cpu_no_idle_flag():
    cost = CostAnalyzer()
    results = cost.analyze_cost(
        {"system": {"cpu_percent": 70}}, {}, HistoryTracker("/tmp/pace-cost-2")
    )
    titles = [r.title.lower() for r in results]
    assert not any("idle" in t for t in titles)


def test_overprovisioned_memory_flagged():
    cost = CostAnalyzer()
    results = cost.analyze_cost(
        {"memory": {"usage_percent": 4}}, {}, HistoryTracker("/tmp/pace-cost-3")
    )
    titles = [r.title.lower() for r in results]
    assert any("provision" in t for t in titles)


# ---------------------------------------------------------------------------
# PredictiveAnalyzer
# ---------------------------------------------------------------------------


def _history_with_rising(trend_dir, metric="disk_usage", values=None):
    h = HistoryTracker(str(trend_dir))
    for i, v in enumerate(values or [50, 55, 60, 65, 70]):
        h.record(metric, float(v))
    return h


def test_disk_projection_when_rising(tmp_path):
    h = _history_with_rising(tmp_path / "h1")
    pred = PredictiveAnalyzer(h)
    results = pred.analyze_trends({"disk": {"usage_percent": 70}})
    assert len(results) == 1
    forecast = results[0]
    assert forecast.result_type == "forecast"
    assert "until" in forecast.title  # "X hours until 95%"

    # seed history with a projection sequence: 5->10->15->20
def test_disk_projection_days_timeline(tmp_path):
    h = HistoryTracker(str(tmp_path / "h2"))
    # low rate of growth → days until threshold
    for i, v in enumerate([50, 51, 52, 53, 54, 55]):
        h.record("disk_usage", float(v))
    pred = PredictiveAnalyzer(h)
    results = pred.analyze_trends({"disk": {"usage_percent": 55}})
    assert len(results) == 1
    assert "days until" in results[0].title


def test_no_projection_when_flat(tmp_path):
    h = HistoryTracker(str(tmp_path / "h3"))
    for v in [50, 50, 50, 50, 50]:
        h.record("disk_usage", float(v))
    pred = PredictiveAnalyzer(h)
    assert pred.analyze_trends({"disk": {"usage_percent": 50}}) == []


def test_no_projection_below_half_full(tmp_path):
    h = HistoryTracker(str(tmp_path / "h4"))
    for v in [10, 20, 30, 40]:
        h.record("disk_usage", float(v))
    pred = PredictiveAnalyzer(h)
    assert pred.analyze_trends({"disk": {"usage_percent": 40}}) == []


def test_cpu_trending_up_flag(tmp_path):
    h = HistoryTracker(str(tmp_path / "h5"))
    for v in [30, 50, 70, 85]:
        h.record("cpu_percent", float(v))
    pred = PredictiveAnalyzer(h)
    results = pred.analyze_trends({"system": {"cpu_percent": 90}})
    titles = [r.title for r in results]
    assert "CPU Trending Upward" in titles


def test_cpu_high_but_not_trending_no_flag(tmp_path):
    h = HistoryTracker(str(tmp_path / "h6"))
    for v in [90, 85, 88, 87]:
        h.record("cpu_percent", float(v))
    pred = PredictiveAnalyzer(h)
    assert pred.analyze_trends({"system": {"cpu_percent": 88}}) == []


def test_memory_growth_projection(tmp_path):
    h = HistoryTracker(str(tmp_path / "h7"))
    for v in [55, 62, 70, 78, 86]:
        h.record("memory_usage", float(v))
    pred = PredictiveAnalyzer(h)
    results = pred.analyze_trends({"memory": {"usage_percent": 86}})
    assert results[0].result_type == "forecast"


# ---------------------------------------------------------------------------
# HistoryTracker (used by predictors)
# ---------------------------------------------------------------------------


def test_history_tracker_trend_detection(tmp_path):
    h = HistoryTracker(str(tmp_path / "h8"))
    for v in [10, 20, 30]:
        h.record("cpu_percent", float(v))
    assert h.get_trend("cpu_percent") == "increasing"


def test_history_tracker_trend_flat(tmp_path):
    h = HistoryTracker(str(tmp_path / "h9"))
    for v in [30, 30, 30]:
        h.record("cpu_percent", float(v))
    assert h.get_trend("cpu_percent") in ("stable", None)


def test_projection_requires_three_samples(tmp_path):
    h = HistoryTracker(str(tmp_path / "h10"))
    h.record("disk_usage", 60.0)
    h.record("disk_usage", 61.0)
    assert h.get_projection("disk_usage", 95) is None

# ---------------------------------------------------------------------------
# InteractiveQA (LLM-backed)
# ---------------------------------------------------------------------------


class _FakeLLM:
    def __init__(self, answer="Disk is at 60% use; safe for now."):
        self._answer = answer
        self.calls = []

    @property
    def chat(self):
        return self

    @property
    def completions(self):
        return self

    def create(self, **kwargs):
        self.calls.append(kwargs)

        class M:
            content = self._answer

        class C:
            message = M()

        class R:
            choices = [C()]

        return R()


def test_qa_uses_llm_when_configured():
    llm = _FakeLLM()
    from pace_atlas.capabilities import InteractiveQA

    qa = InteractiveQA(llm_client=llm, model="gpt-4o-mini")
    result = qa.answer("How full is my disk?", {"system": {"cpu_percent": 40}}, "")
    assert result.result_type == "qa"
    assert "60%" in result.body
    assert llm.calls[0]["model"] == "gpt-4o-mini"
    assert "How full is my disk" in llm.calls[0]["messages"][0]["content"]


def test_qa_falls_back_static_without_llm():
    from pace_atlas.capabilities import InteractiveQA

    qa = InteractiveQA()
    result = qa.answer("What is my CPU?", {"system": {"cpu_percent": 40}}, "")
    assert result.result_type == "qa"
    assert "What is my CPU" in result.body


def test_qa_failure_is_graceful():
    class Boom(_FakeLLM):
        def create(self, **kwargs):
            raise RuntimeError("api down")

    from pace_atlas.capabilities import InteractiveQA

    qa = InteractiveQA(llm_client=Boom(), model="m")
    result = qa.answer("status?", {}, "")
    assert "LLM unavailable" in result.title


def test_capabilities_accepts_llm_client(tmp_path):
    from pace_atlas.capabilities import AtlasCapabilities

    caps = AtlasCapabilities(str(tmp_path), llm_client=_FakeLLM(), model="m")
    assert caps.qa.llm_client is not None
    assert caps.qa.model == "m"
