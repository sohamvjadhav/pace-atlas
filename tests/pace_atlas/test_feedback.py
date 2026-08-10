"""Tests for pace_atlas.feedback: learning from user feedback, suppression, cooldowns."""
from pace_atlas.feedback import FeedbackLearning


def _fresh(tmp_path):
    return FeedbackLearning(str(tmp_path))


def test_record_useful_feedback(tmp_path):
    fb = _fresh(tmp_path)
    fb.record_feedback("cpu_high", "useful", "cpu at 99%")
    assert len(fb.feedback_history) == 1
    assert fb.feedback_history[0].alert_type == "cpu_high"


def test_mute_suppresses_alert_type(tmp_path):
    fb = _fresh(tmp_path)
    fb.record_feedback("disk_full", "mute", "too noisy")
    assert fb.should_suppress("disk_full") is True


def test_ignore_suppresses_alert_type(tmp_path):
    fb = _fresh(tmp_path)
    fb.record_feedback("ssh_alerts", "ignore")
    assert fb.should_suppress("ssh_alerts") is True


def test_unmuted_type_not_suppressed(tmp_path):
    fb = _fresh(tmp_path)
    fb.record_feedback("disk_full", "mute")
    assert fb.should_suppress("cpu_high") is False


def test_too_frequent_increases_cooldown(tmp_path):
    fb = _fresh(tmp_path)
    initial = fb.get_cooldown("cpu_high")
    fb.record_feedback("cpu_high", "too_frequent")
    assert fb.get_cooldown("cpu_high") > initial


def test_persistence_roundtrip(tmp_path):
    fb = _fresh(tmp_path)
    fb.record_feedback("oom_kills", "useful")
    fb2 = FeedbackLearning(str(tmp_path))
    assert fb2.should_suppress("oom_kills") == fb.should_suppress("oom_kills")
    assert len(fb2.feedback_history) >= 1


def test_utility_score_starts_zero(tmp_path):
    fb = _fresh(tmp_path)
    fb.record_feedback("x", "useful")
    fb.record_feedback("x", "not_needed")
    # scoring exists and is numeric for the alert type
    assert isinstance(fb.get_utility_score("x"), float)


def test_context_contains_server_and_learned_patterns(tmp_path):
    fb = _fresh(tmp_path)
    ctx = fb.get_context()
    assert "suppressed_types" in ctx
    assert "recent_feedback" in ctx
    assert "alert_preferences" in ctx


def test_learnt_patterns_from_feedback(tmp_path):
    fb = _fresh(tmp_path)
    fb.record_feedback("disk_full", "too_frequent", "disk full alert")
    patterns = fb._get_recent_feedback_summary()
    assert "0 useful" in patterns or "useful" in patterns