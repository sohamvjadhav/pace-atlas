"""
PACE Atlas — Alert & telemetry history

Append-only JSONL ledger at ~/.pace/history.jsonl that gives a resident
agent three things it needs to "alert only when it matters":

1. Persistence — alerts survive restarts, enabling trend and RCA analysis
   across runs (the in-memory HistoryTracker in capabilities.py does not).
2. Repeat suppression — the same alert_type within the dedupe window is
   skipped (alert fatigue), while a severity escalation still goes out.
3. Trend window — recent metric values for comparison against current
   readings (spikes vs. slow drift).

The ledger is append-only with a hard cap: entries beyond
`max_history_entries` are dropped from the tail, so the file cannot grow
unbounded.
"""

import json
import time
from collections import deque
from pathlib import Path
from typing import Any, Optional


class AtlasHistory:
    def __init__(self, path: str | Path, max_entries: int = 5000):
        self.path = Path(path).expanduser()
        self.max_entries = max_entries
        self._recent: deque[dict[str, Any]] = deque(maxlen=max_entries)
        self._last_sent: dict[tuple[str, str], float] = {}
        self._written = 0
        self._load_tail()

    def _load_tail(self) -> None:
        """Load the most recent entries from the ledger into memory."""
        if not self.path.exists():
            return
        try:
            for line in self.path.read_text(encoding="utf-8").splitlines()[-self.max_entries :]:
                entry = json.loads(line)
                self._recent.append(entry)
                if entry.get("kind") == "alert_sent":
                    key = (entry.get("alert_type", ""), entry.get("severity", ""))
                    self._last_sent[key] = entry.get("ts", 0.0)
        except (OSError, json.JSONDecodeError):
            pass
        self._written = sum(1 for _ in self.path.open()) if self.path.exists() else 0

    def _append(self, entry: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, default=str) + "\n")
        self._written += 1
        self._recent.append(entry)
        if self._written > self.max_entries:
            self._trim()

    def record_alert_sent(
        self, alert_type: str, severity: str, reason: str, ts: Optional[float] = None
    ) -> None:
        """Record that an alert was delivered."""
        now = ts if ts is not None else time.time()
        self._append(
            {
                "kind": "alert_sent",
                "ts": now,
                "alert_type": alert_type,
                "severity": severity,
                "reason": reason[:200],
            }
        )
        self._last_sent[(alert_type, severity)] = now

    def last_sent_ts(self, alert_type: str, severity: str) -> Optional[float]:
        return self._last_sent.get((alert_type, severity))

    def is_suppressed(
        self, alert_type: str, severity: str, window_seconds: int = 300
    ) -> bool:
        """True if an identical alert was sent within the dedupe window."""
        if window_seconds <= 0:
            return False
        last = self.last_sent_ts(alert_type, severity)
        return last is not None and (time.time() - last) < window_seconds

    def record_telemetry(
        self,
        collector_name: str,
        data: dict[str, Any],
        ts: Optional[float] = None,
    ) -> None:
        """Record a metric sample for trend analysis."""
        self._append(
            {
                "kind": "telemetry",
                "ts": ts if ts is not None else time.time(),
                "collector": collector_name,
                "data": data,
            }
        )

    def recent_values(
        self, collector_name: str, key: str, window_seconds: int = 3600
    ) -> list[tuple[float, float]]:
        """Return [(ts, value)] samples for a metric within the window."""
        cutoff = time.time() - window_seconds
        samples = []
        for entry in self._recent:
            if entry.get("kind") != "telemetry" or entry.get("collector") != collector_name:
                continue
            ts = entry.get("ts", 0)
            if ts < cutoff:
                continue
            value = (entry.get("data") or {}).get(key)
            if isinstance(value, (int, float)):
                samples.append((ts, float(value)))
        return samples

    def alerts(self) -> list[dict[str, Any]]:
        """All alert entries (newest last), for status and tests."""
        return [e for e in self._recent if e.get("kind") == "alert_sent"]

    def _trim(self) -> None:
        """Rewrite the ledger keeping only the newest max_entries rows."""
        rows = list(self._recent)[-self.max_entries :]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            for entry in rows:
                f.write(json.dumps(entry, default=str) + "\n")
        self._recent = deque(rows, maxlen=self.max_entries)

    def summary(self) -> dict[str, Any]:
        """Brief stats for `pace atlas status` and health checks."""
        alerts = self.alerts()
        types: dict[str, int] = {}
        for entry in alerts:
            key = f"{entry.get('severity')}/{entry.get('alert_type')}"
            types[key] = types.get(key, 0) + 1
        telemetry = [e for e in self._recent if e.get("kind") == "telemetry"]
        return {
            "alert_entries": len(alerts),
            "telemetry_points": len(telemetry),
            "breakdown": types,
        }
