<p align="center">
  <img src="https://raw.githubusercontent.com/sohamvjadhav/pace-atlas/main/assets/banner.png?v=4" alt="PACE Atlas" width="100%">
</p>

# PACE Atlas ⚡

**Proactive Autonomous Cloud Environment** — the server agent that watches your infrastructure and alerts you only when it matters.

PACE Atlas is an AI-powered Site Reliability Engineer that lives inside your cloud instance. It doesn't just check thresholds — it uses LLM knowledge to give context, spot patterns, predict incidents, and explain root causes like an experienced SRE colleague with 15+ years of on-call experience.

> **Key differentiator** — external uptime monitors observe a server from the network boundary. PACE runs *inside* the instance: full visibility into system internals, process states, security logs, and resource utilization that external tools never see.

---

## Capabilities (v1.0)

| Capability | What it does |
|-----------|-------------|
| **Telemetry collection** | CPU, memory, disk, network, process, security, cloud, and log telemetry (`pace_atlas/telemetry/`) |
| **Alert engine** | Hard-rule alerts with an LLM decision layer — context, patterns, correlation, not just thresholds (`pace_atlas/alert_engine/`) |
| **Root cause analysis** | Chain-of-causation analysis with prevention guidance |
| **Security intelligence** | Attack-pattern recognition and threat-level assessment |
| **Cost optimization** | Flags idle resources and over-provisioning |
| **Predictive analysis** | Trend detection and forecasting |
| **Feedback learning** | Improves from every alert and interaction (`pace_atlas/feedback/`) |
| **Interactive Q&A** | Ask about your infrastructure in plain language |

### Architecture

```
Telemetry → Atlas Capabilities → Smart Alert / Insight / Forecast / RCA
                    ↓
         Full LLM Knowledge + Personality
         (not just threshold checking)
```

- Identity: AI SRE engineer with 15+ years of experience
- Telemetry analysis: context, patterns, correlation
- Security excellence: attack recognition, threat levels
- Cost excellence: idle resources, over-provisioning
- RCA excellence: chain of causation, prevention

---

## Also on board

Because PACE Atlas inherits the full agent runtime it was forked from, you also get:

- **Terminal interface** — full TUI with multiline editing, slash-command autocomplete, conversation history, interrupt-and-redirect, streaming tool output
- **Lives where you do** — Telegram, Discord, Slack, WhatsApp, Signal, and CLI, all from a single gateway process
- **Closed learning loop** — agent-curated memory, autonomous skill creation, FTS5 session search with LLM summarization
- **Scheduled automations** — built-in cron with natural-language schedules and delivery to any platform
- **Delegation** — parallel subagents with isolated contexts
- **Runs anywhere** — local, Docker, SSH, Modal, or a $5 VPS

---

## Quick start

PACE Atlas isn't published to PyPI yet — install from source:

```bash
git clone https://github.com/sohamvjadhav/pace-atlas
cd pace-atlas
uv sync            # or: python -m venv venv && pip install -e .
pace setup         # one-time configuration
pace               # start PACE Atlas CLI
```

### Commands

```bash
pace                        # interactive chat
pace chat -q "..."          # single query, no TUI
pace setup                  # one-time setup wizard
pace model                  # select default model
pace config                 # view config (edit / set / get / unset)
pace auth                   # pooled credentials (add / list / remove / reset)
pace gateway                # run the messaging gateway
pace gateway install        # install as a background service (systemd / launchd)
pace cron                   # scheduled jobs (list / add / edit / run / remove)
pace skills                 # skill hub (install / list / browse / search / update)
pace sessions list          # past sessions
pace webhook                # webhook endpoints
pace doctor                 # environment diagnostics
pace profile                # multi-instance profiles
pace update                 # update to latest
```

Config lives in `~/.pace/` — `config.yaml` for settings, `.env` for API keys only, logs in `~/.pace/logs/`.

Use any model you want — OpenRouter (200+ models), OpenAI, Anthropic, Google, Hugging Face, or your own endpoint. Switch with `pace model` — no code changes, no lock-in.

---

## Documentation

- `docs/architecture.md` — system architecture and design
- `REBRAND_LOG.md` — history of the PACE Atlas fork and its changes

---

## Acknowledgements

PACE Atlas is a fork of [Hermes Agent](https://github.com/NousResearch/hermes-agent) by [Nous Research](https://nousresearch.com) — kept the core runtime, rebranded and extended for infrastructure operations, in the same spirit as Cursor forking VS Code.

---

## License

[MIT](LICENSE)
