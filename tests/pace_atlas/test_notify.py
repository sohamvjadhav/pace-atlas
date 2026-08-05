"""Tests for pace_atlas.notify: channel building, fan-out, failure isolation."""
from pace_atlas.notify import (
    ConsoleChannel,
    EmailChannel,
    FileChannel,
    NotificationManager,
    WebhookChannel,
)


class FakeChannel:
    """Channel double so no real I/O happens."""

    name = "recording"

    def __init__(self):
        self.received = []

    def send(self, subject, body):
        self.received.append((subject, body))
        return True


def test_build_channels_console_default_when_empty():
    channels = NotificationManager.from_config({}).channels
    assert len(channels) == 1
    assert isinstance(channels[0], ConsoleChannel)


def test_build_channels_respects_enabled_list(tmp_path):
    cfg = {
        "notifications": {
            "channels": ["file"],
            "file": {"path": str(tmp_path / "alerts.log")},
        }
    }
    channels = NotificationManager.from_config(cfg).channels
    assert len(channels) == 1
    assert isinstance(channels[0], FileChannel)


def test_fan_out_delivers_to_all():
    channel = FakeChannel()
    manager = NotificationManager([channel])
    delivered = manager.send("subject", "body")
    assert delivered == ["recording"]
    assert channel.received == [("subject", "body")]


def test_fan_out_isolates_failures():
    class Good(FakeChannel):
        name = "good"

    class Flaky(FakeChannel):
        name = "flaky"

        def send(self, subject, body):
            raise OSError("boom")

    manager = NotificationManager([Good(), Flaky()])
    delivered = manager.send("s", "b")
    assert delivered == ["good"]


def test_fan_out_skips_false_results():
    class Silent(FakeChannel):
        name = "silent"

        def send(self, subject, body):
            return False

    manager = NotificationManager([Silent(), ConsoleChannel()])
    delivered = manager.send("s", "b")
    assert delivered == ["console"]


def test_console_channel_returns_true():
    assert ConsoleChannel().send("s", "b") is True


def test_email_channel_init_requires_full_config():
    email = EmailChannel(
        {
            "enabled": True,
            "host": "sandbox.smtp.example.com",
            "port": 587,
            "username": "user",
            "password": "pass",
            "sender": "atlas@example.com",
            "to": ["ops@example.com"],
            "tls": True,
        }
    )
    assert email.port == 587


def test_webhook_constructs():
    wh = WebhookChannel("https://hooks.example.com/abc")
    assert wh.url == "https://hooks.example.com/abc"