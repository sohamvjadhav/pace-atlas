# PACE Atlas — Architecture Documentation

> **Version**: 1.0.0  
> **Status**: Full SRE Agent  
> **Last Updated**: 2025-04-05

---

## 1. Overview

### 1.1 What is PACE Atlas?

**PACE Atlas** is an AI-powered Site Reliability Engineer (SRE) that lives inside your cloud server. It's not just a monitoring tool — it's a knowledgeable colleague who:

- Watches your infrastructure 24/7
- Uses its vast knowledge to provide context and insight
- Predicts problems before they become incidents
- Performs root cause analysis when things break
- Optimizes costs without you asking
- Answers your questions about infrastructure
- Has a personality (experienced sysadmin, helpful, direct)

### 1.2 Key Differentiator

> Unlike external uptime monitors that observe a server from the network boundary, PACE runs as a resident agent inside the cloud instance itself — giving it full visibility into system internals, process states, security logs, and resource utilization that external tools cannot access.

> Unlike simple monitoring tools, Atlas doesn't just check thresholds. It uses LLM knowledge to analyze patterns, provide context, and act as an experienced SRE would.

---

## 2. System Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         PACE ATLAS (Resident Agent)                      │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌──────────┐ │
│  │  Telemetry  │    │    Alert    │    │  Feedback  │    │ Gateway  │ │
│  │  Collection │ →  │   Engine    │ →  │   Learning │    │ (Notify) │ │
│  └─────────────┘    └─────────────┘    └─────────────┘    └──────────┘ │
│         │                   │                   │                   │     │
│         └───────────────────┴───────────────────┴───────────────────┘     │
│                              │                                            │
│                    ┌─────────▼─────────┐                                 │
│                    │  LLM Decision    │                                 │
│                    │    (Atlas Brain) │                                 │
│                    └───────────────────┘                                 │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    SERVER INFRASTRUCTURE (Internal)                     │
├─────────────────────────────────────────────────────────────────────────┤
│  ┌────────┐  ┌─────────┐  ┌──────┐  ┌───────┐  ┌────────┐  ┌────────┐ │
│  │  CPU   │  │ Memory  │  │ Disk │  │ Network│  │Process │  │  Logs  │ │
│  │ /proc/ │  │ /proc/  │  │ df   │  │  ss    │  │  ps    │  │journal │ │
│  └────────┘  └─────────┘  └──────┘  └───────┘  └────────┘  └────────┘ │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Core Components

### 3.1 Telemetry Collection Module

**Purpose**: Collect real-time server metrics from internal system files and commands.

| Component | Data Sources | Update Frequency |
|-----------|--------------|------------------|
| **SystemMetrics** | `/proc/stat`, `top`, `uptime` | Every 30s |
| **MemoryMetrics** | `/proc/meminfo`, `free` | Every 30s |
| **DiskMetrics** | `df`, `du`, `iostat` | Every 60s |
| **NetworkMetrics** | `ss`, `netstat`, `/proc/net/` | Every 30s |
| **ProcessMetrics** | `ps`, `systemctl`, `/proc/` | Every 30s |
| **SecurityMonitor** | `/var/log/auth.log`, `journalctl` | Every 60s |
| **LogAggregator** | `/var/log/`, `journalctl` | On event |
| **CloudProvider** | AWS CloudWatch, GCP, Azure APIs | Every 300s |

### 3.2 Alert Engine

**Purpose**: Determine if observed state warrants user notification.

```
┌─────────────────┐
│  Raw Telemetry  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   Hard Rules    │  ← Always alert (critical events)
│  (First Pass)   │
└────────┬────────┘
         │ No
         ▼
┌─────────────────┐
│ LLM Decision    │  ← Should we alert?
│   (Atlas Brain) │
└────────┬────────┘
         │
    ┌────┴────┐
    │         │
  ALERT    SILENT
    │         │
    ▼         ▼
┌────────┐  ┌─────────┐
│Gateway │  │  Store  │
│Notify  │  │ Silence │
└────────┘  └─────────┘
```

**Hard Rules** (Always alert regardless of LLM):
- Disk ≥ 95%
- Memory ≥ 95%
- CPU ≥ 95% sustained > 5 min
- Service in failed state
- 10+ SSH failed logins (brute force)
- Billing spike > 50%
- OOM killer triggered

### 3.3 Feedback Learning System

**Purpose**: Learn from user feedback to improve alert relevance over time.

| Feedback Type | Action |
|---------------|--------|
| "useful", "thanks" | Maintain current threshold |
| "not needed", "ignore" | Raise threshold for this alert type |
| "mute X" | Silence this alert type for 24h |
| "alert me earlier" | Lower threshold |
| "too frequent" | Increase cooldown between alerts |

### 3.4 Gateway (Notification Layer)

**Purpose**: Send alerts to user via preferred channel.

**Supported Channels**:
- Telegram (primary)
- WhatsApp
- Discord
- Slack
- Signal
- Email

---

## 4. Data Flow

### 4.1 Monitoring Cycle

```
1. CRON triggers PACE Atlas (every 1-5 minutes)
2. Telemetry Module collects metrics
3. Hard Rules check (critical events → immediate alert)
4. Telemetry + Context → LLM prompt
5. LLM decides: ALERT or SILENT
6. If ALERT → Gateway → Send to user
7. Store decision for feedback learning
8. Wait for next cycle
```

### 4.2 Event-Driven Flow

```
1. Log event triggers (error, warning, security)
2. Parse event → Extract relevant data
3. Hard Rules check
4. LLM decides action
5. If ALERT → Immediate notification
6. Store for learning
```

---

## 5. Directory Structure

```
pace-atlas/
├── pace_atlas/
│   ├── __init__.py
│   ├── runner.py           # Main entry point
│   ├── telemetry/          # Telemetry collection
│   │   ├── __init__.py
│   │   ├── base.py         # Base collector class
│   │   ├── system.py       # CPU, load averages
│   │   ├── memory.py       # RAM, swap
│   │   ├── disk.py         # Disk usage, I/O
│   │   ├── network.py      # Connections, bandwidth
│   │   ├── process.py     # Process list, services
│   │   ├── security.py    # Auth logs, failed logins
│   │   ├── logs.py        # Log aggregation
│   │   └── cloud.py       # Cloud provider APIs
│   ├── alert_engine/
│   │   ├── __init__.py
│   │   ├── hard_rules.py  # Critical event detection
│   │   └── decision.py    # LLM decision handling
│   ├── feedback/
│   │   ├── __init__.py
│   │   └── learning.py    # Feedback processing
│   ├── prompts/            # (from parent: prompts/pace_atlas.py)
│   └── gateway/            # (from parent: gateway/)
├── config/
│   └── pace.yaml          # Configuration
├── tests/
└── README.md
```

---

## 6. Configuration

### 6.1 Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `PACE_HOME` | Config directory | `~/.pace/` |
| `PACE_CHECK_INTERVAL` | Seconds between checks | `300` (5 min) |
| `PACE_LOG_LEVEL` | Logging level | `INFO` |
| `PACE_NOTIFICATION_CHANNEL` | Primary channel | `telegram` |

### 6.2 Config File (`~/.pace/config.yaml`)

```yaml
pace:
  check_interval: 300        # seconds
  notification_channel: telegram
  
atlas:
  hard_rules:
    disk_threshold: 95      # %
    memory_threshold: 95   # %
    cpu_threshold: 95       # % sustained
    ssh_fail_threshold: 10 # attempts in 10 min
    
  llm:
    model: anthropic/claude-sonnet-4-20250514
    decision_threshold: 0.7
    
  learning:
    enabled: true
    cooldown_minutes: 30
    
alerts:
  channels:
    - telegram
    # - whatsapp
    
  quiet_hours:
    enabled: false
    start: "22:00"
    end: "08:00"
```

---

## 7. Dependencies

### 7.1 Core Dependencies

```
psutil           # System metrics
requests         # HTTP for cloud APIs
python-dotenv    # Environment config
pydantic         # Config validation
```

### 7.2 Optional Dependencies

```
python-telegram-bot  # Telegram notifications
discord.py          # Discord notifications
aiohttp             # Async HTTP for WhatsApp
croniter            # Cron scheduling
```

---

## 8. API Reference

### 8.1 TelemetryCollector (Base Class)

```python
class TelemetryCollector(ABC):
    @abstractmethod
    def collect(self) -> dict:
        """Collect metrics and return as dict."""
        pass
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier for this collector."""
        pass
```

### 8.2 AlertEngine

```python
class AlertEngine:
    def __init__(self, config: PACEConfig):
        self.hard_rules = HardRules(config)
        self.llm_client = LLMClient(config)
        self.feedback = FeedbackLearning(config)
    
    def should_alert(self, telemetry: dict) -> tuple[bool, str]:
        """
        Returns:
            (should_alert: bool, reason: str)
        """
        # 1. Check hard rules
        if self.hard_rules.triggered(telemetry):
            return True, "hard_rule"
        
        # 2. Ask LLM
        return self.llm_client.decide(telemetry, self.feedback.get_context())
```

### 8.3 FeedbackLearning

```python
class FeedbackLearning:
    def record_feedback(self, alert_type: str, feedback: str):
        """Record user feedback for learning."""
        
    def get_context(self) -> dict:
        """Get learning context for LLM decision."""
        
    def should_suppress(self, alert_type: str) -> bool:
        """Check if alert type is muted."""
```

---

## 9. Security Considerations

### 9.1 Data Handling

- Telemetry stored locally only
- No external data transmission except notifications
- API keys stored in `~/.pace/.env`

### 9.2 Access Control

- Run as non-privileged user where possible
- Read-only access to most system files
- Write access only to `~/.pace/`

---

## 10. Future Enhancements

- [ ] Multi-server support (aggregate from multiple instances)
- [ ] Custom metric plugins
- [ ] Integration with Prometheus/Grafana
- [ ] Runbook automation (auto-remediate on alert)
- [ ] Historical data visualization

---

## 11. Glossary

| Term | Definition |
|------|------------|
| **Resident Agent** | Software that runs inside the monitored server, not externally |
| **Telemetry** | Machine-readable data about system state |
| **Hard Rules** | Non-negotiable alert conditions |
| **LLM Decision** | Atlas brain deciding if alert is needed |
| **Feedback Loop** | User input that improves future alerts |
| **Gateway** | Notification delivery layer (Telegram, etc.) |

---

*Document Version: 0.1.0*  
*Part of PACE Atlas Project*