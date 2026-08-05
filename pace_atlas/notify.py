"""
PACE Atlas — Notification channels

Delivers alerts to the configured destinations. Channels use only the
standard library so PACE Atlas runs anywhere without extra dependencies.

Supported channels (configure under `notifications:` in config.yaml):
    console          — log line (always available)
    file             — append to ~/.pace/alerts.log
    telegram         — sendMessage via the Bot HTTP API (bot_token + chat_id)
    webhook          — generic JSON POST to a URL (Slack/Teams/etc. adapters)
    email            — SMTP message with optional STARTTLS/SSL

The NotificationManager fans an alert out to every configured channel and
reports which channels succeeded.
"""

import json
import logging
import smtplib
import ssl
import urllib.request
from abc import ABC, abstractmethod
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any, Iterable

logger = logging.getLogger(__name__)


class NotificationError(Exception):
    pass


class NotificationChannel(ABC):
    """A single delivery target for alerts."""

    name = "base"

    @abstractmethod
    def send(self, subject: str, body: str) -> bool:
        """Deliver an alert. Return True on success."""


class ConsoleChannel(NotificationChannel):
    name = "console"

    def send(self, subject: str, body: str) -> bool:
        logger.info("[alert] %s\n%s", subject, body)
        print(f"{subject}\n{body}", flush=True)
        return True


class FileChannel(NotificationChannel):
    name = "file"

    def __init__(self, path: str = "~/.pace/alerts.log"):
        self.path = Path(path).expanduser()

    def send(self, subject: str, body: str) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(f"{subject}\n{body}\n{'=' * 60}\n")
        return True


class WebhookChannel(NotificationChannel):
    """Generic JSON webhook. Subclass and override _build_payload for formats."""

    name = "webhook"

    def __init__(self, url: str, timeout: float = 10.0):
        self.url = url
        self.timeout = timeout

    def _build_payload(self, subject: str, body: str) -> dict:
        return {"title": subject, "text": body}

    def send(self, subject: str, body: str) -> bool:
        if not self.url:
            return False
        payload = json.dumps(self._build_payload(subject, body)).encode()
        req = urllib.request.Request(
            self.url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return 200 <= resp.status < 300
        except Exception as exc:  # network errors must not crash the daemon
            logger.warning("webhook send failed: %s", exc)
            return False


class TelegramChannel(WebhookChannel):
    name = "telegram"

    def __init__(self, bot_token: str, chat_id: str, timeout: float = 10.0):
        if not bot_token or not chat_id:
            raise ValueError("telegram channel requires bot_token and chat_id")
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.timeout = timeout

    @property
    def url(self) -> str:
        return f"https://api.telegram.org/bot{self.bot_token}/sendMessage"

    def _build_payload(self, subject: str, body: str) -> dict:
        return {
            "chat_id": self.chat_id,
            "text": f"<b>{subject}</b>\n<pre>{body}</pre>",
            "parse_mode": "HTML",
        }


class EmailChannel(NotificationChannel):
    name = "email"

    def __init__(self, cfg: dict):
        self.host = cfg.get("host")
        self.port = int(cfg.get("port", 587))
        self.username = cfg.get("username")
        self.password = cfg.get("password")
        self.sender = cfg.get("from") or self.username
        self.recipients = [r for r in (cfg.get("to") or []) if r]
        self.use_tls = bool(cfg.get("tls", True))
        self.use_ssl = bool(cfg.get("ssl", False))

    def send(self, subject: str, body: str) -> bool:
        if not self.host or not self.sender or not self.recipients:
            return False
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = self.sender
        msg["To"] = ", ".join(self.recipients)

        context = ssl.create_default_context()
        try:
            if self.use_ssl:
                with smtplib.SMTP_SSL(self.host, self.port, context=context) as server:
                    return self._authorize_and_send(server, msg)
            with smtplib.SMTP(self.host, self.port, timeout=15) as server:
                if self.use_tls:
                    server.starttls(context=context)
                return self._authorize_and_send(server, msg)
        except Exception as e:  # noqa: BLE001
            logger.warning("email send failed: %s", e)
            return False

    def _authorize_and_send(self, server, msg) -> bool:
        if self.username and self.password:
            server.login(self.username, self.password)
        server.sendmail(self.sender, self.recipients, msg.as_string())
        return True


def build_channels(config: dict) -> list[NotificationChannel]:
    """Build notification channels from config."""
    channels: list[NotificationChannel] = []
    cfg = config.get("notifications", {})
    enabled = cfg.get("channels") or ["console"]

    if "console" in enabled:
        channels.append(ConsoleChannel())
    if "file" in enabled:
        channels.append(FileChannel(cfg.get("file", {}).get("path", "~/.pace/alerts.log")))
    if "webhook" in enabled and cfg.get("webhook", {}).get("url"):
        channels.append(WebhookChannel(cfg["webhook"]["url"]))
    if "telegram" in enabled:
        tg = cfg.get("telegram", {})
        channels.append(TelegramChannel(tg.get("bot_token"), tg.get("chat_id")))
    if "email" in enabled:
        channels.append(EmailChannel(cfg.get("email", {})))

    return channels


class NotificationManager:
    """Fan-out manager that delivers alerts to all configured channels."""

    def __init__(self, channels: Iterable[NotificationChannel]):
        self.channels = list(channels)

    @classmethod
    def from_config(cls, config: dict) -> "NotificationManager":
        return cls(build_channels(config))

    def send(self, subject: str, body: str) -> list[str]:
        delivered = []
        for channel in self.channels:
            try:
                if channel.send(subject, body):
                    delivered.append(channel.name)
            except Exception as e:  # noqa: BLE001
                logger.warning("channel %s failed: %s", channel.name, e)
        return delivered