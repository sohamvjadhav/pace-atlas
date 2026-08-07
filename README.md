<p align="center">
  <img src="https://raw.githubusercontent.com/sohamvjadhav/pace-atlas/main/assets/banner.png?v=4" alt="PACE Atlas" width="100%">
</p>

# PACE Atlas ⚡

**Proactive Autonomous Cloud Environment** — the server agent that watches your infrastructure and alerts you only when it matters.

PACE Atlas is an AI-powered Site Reliability Engineer that lives inside your cloud instance. It doesn't just check thresholds — it uses LLM knowledge to give context, spot patterns, predict incidents, and explain root causes like an experienced SRE colleague with 15+ years of on-call experience.

> **Key differentiator** — external uptime monitors observe a server from the network boundary. PACE runs *inside* the instance: full visibility into system internals, process states, security logs, and resource utilization that external tools never see.

---

## What I built vs. what I inherited

PACE Atlas is a fork of [Hermes Agent](https://github.com/NousResearch/hermes-agent) — but the two layers are deliberately separate, and only one of them is this project's contribution.

### Built here: the resident SRE agent (`pace_atlas/`)

This entire package is original to this fork — **upstream Hermes Agent has no `pace_atlas/` at all** (all 5,455 lines, authored in this repo, plus the agent-core additions below). This is the submission-worthy core.

| Module | What it does |
|-----------|-------------|
| **Telemetry collection** | 8 collectors — CPU, memory, disk, network, process, security, cloud, logs (`pace_atlas/telemetry/`) |
| **Alert engine** | Hard-rule alerts + an **LLM decision layer** that reads the same telemetry and decides with context, pattern correlation, and severity judgment instead of raw thresholds (`pace_atlas/alert_engine/`) |
| **Root cause analysis** | Chain-of-causation analysis with prevention guidance (`pace_atlas/capabilities.py`) |
| **Security intelligence** | Attack-pattern recognition, threat-level assessment of SSH/network/log events |
| **Cost optimization** | Flags idle resources and over-provisioning against live cloud billing data |
| **Predictive analysis** | Trend detection, rate-of-change, and forecast-to-threshold projections |
| **Feedback learning** | Improves from every alert and interaction — mute patterns, adjust thresholds (`pace_atlas/feedback/`) |
| **Interactive Q&A** | Ask about your infrastructure in plain language |
| **Config layer** | Layered config (defaults < file < env < CLI), provider auto-detect from Groq/OpenAI/Anthropic keys (`pace_atlas/config.py`) |
| **Notification fan-out** | Console, file, webhook, Telegram, email channels with failure isolation (`pace_atlas/notify.py`) |
| **Alert history ledger** | Append-only JSONL with repeat-alert suppression windows and trend history (`pace_atlas/history.py`) |
| **Resident runner** | Daemon lifecycle — pidfile, SIGTERM/SIGINT, dedupe windows, `--install` / `--install-systemd` / `--status` (`pace_atlas/runner.py`) |

This agent is also published standalone: **`pip install pace-atlas`** → `pace-atlas --daemon` — no Hermes runtime required.

### Inherited: the agent runtime (everything else)

Because the fork keeps the upstream runtime, PACE Atlas also ships Hermes Agent's infrastructure — **none of this was written here**, it came with the fork:

- **Agent core** — conversation loop, tool orchestration, model providers (`run_agent.py`, `model_tools.py`)
- **Messaging gateway** — Telegram, Discord, Slack, WhatsApp, Signal, ~20 platforms (`gateway/`)
- **CLI / TUI / desktop** — interactive shells, skins, dashboard (`pace_cli/`, `ui-tui/`, `apps/desktop/`)
- **Memory & skills** — session storage, skill hub, curator (`hermes_state.py`, `skills/`, `plugins/`)
- **Automation** — cron scheduler, delegation, kanban board (`cron/`, `tools/`, `plugins/kanban/`)

### At a glance (diff vs. upstream `main`)

```
pace_atlas/          21 files, ~6,000 lines added   ← the contribution (not in upstream)
config.py, notify.py, history.py, runner.py, tests   ← agent-core work, added on top
total fork diff:     393 files changed, 54,758 insertions, 9,512 deletions
                     (mostly the rebrand pass over docs/CLI/gateway strings)
```

Full account: [`REBRAND_LOG.md`](REBRAND_LOG.md) — including what each `pace_atlas/` module does, which commits added it, and what the diff against upstream really is.

---

## Quick start

```bash
pip install pace-atlas        # standalone agent — or run from this repo:

git clone https://github.com/sohamvjadhav/pace-atlas
cd pace-atlas
uv sync            # or: python -m venv venv && pip install -e .
pace setup         # one-time configuration
pace               # start PACE Atlas CLI
```

The resident agent (from `pace_atlas/`):

```bash
pace-atlas --install        # write ~/.pace/config.yaml
pace-atlas --daemon         # monitor every 5 minutes
pace-atlas --status         # health summary
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
- `REBRAND_LOG.md` — what this fork changed vs. upstream, with the full contribution diff

---

## Acknowledgements

PACE Atlas is a fork of [Hermes Agent](https://github.com/NousResearch/hermes-agent) by [Nous Research](https://nousresearch.com) — kept the runtime, built the `pace_atlas/` SRE agent on top, in the same spirit as Cursor forking VS Code. All `pace_atlas/` code is original to this fork.

---

## License

[MIT](LICENSE)
