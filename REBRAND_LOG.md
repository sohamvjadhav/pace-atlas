# PACE Rebrand Log

## Overview
Date: 2025-04-05
Purpose: Full rebrand from Hermes Agent to PACE Atlas + build the resident SRE agent
Reference: Like Cursor (forked VS Code) - kept core, hidden original branding
Status: ✅ COMPLETED

## Changes Made

### 1. Package Configuration (pyproject.toml)
- name: hermes-agent → pace-agent
- version: 0.7.0 → 0.1.0
- description: Updated for PACE Atlas
- scripts: hermes → pace, hermes-agent → pace-agent
- Include: pace_cli, prompts packages

### 2. CLI Module (pace_cli/)
- Created copy of hermes_cli → pace_cli
- All "Hermes" → "PACE Atlas"
- All "Hermes CLI" → "PACE CLI"
- All "Hermes Agent" → "PACE Atlas"
- HERMES_HOME → PACE_HOME (environment variable)
- hermes_cli → pace_cli (imports)
- Default config: ~/.hermes → ~/.pace
- Branding: "⚕ Hermes" → "⚡ PACE"
- Skin defaults: agent_name "Hermes Agent" → "PACE Atlas"

### 3. Gateway Module
- All Hermes references replaced with PACE

### 4. Prompts Module
- prompts/pace_atlas.py - Original PACE Atlas prompts
- prompts/atlas_knowledge.py - Knowledge-powered version
- prompts/atlas_complete.py - Complete SRE agent prompts (v1.0)

### 5. PACE Atlas Core Modules (NEW)
- pace_atlas/ - Main package
  - runner.py - Main entry point
  - capabilities.py - Advanced capabilities module
  - telemetry/ - Telemetry collection
    - base.py, system.py, memory.py, disk.py
    - network.py, process.py, security.py
    - cloud.py, logs.py
  - alert_engine/ - Alert decision logic
  - feedback/ - Learning system

### 6. Scripts
- scripts/rebrand.py - Rebrand automation
- scripts/rebrand.py - Future rebrand operations

## Files Modified (64+ files)
- pace_cli/* (43 files)
- gateway/* (21 files)
- pyproject.toml
- prompts/pace_atlas.py, atlas_knowledge.py, atlas_complete.py (created)
- pace_atlas/* (created)

## Usage
After install:
```bash
pace                    # Start PACE Atlas CLI
pace gateway start      # Start messaging gateway
pace model              # Configure model
```

Config directory: ~/.pace/

## PACE Atlas Capabilities (v1.0)

### Implemented Features:
1. ✅ Telemetry Collection (CPU, Memory, Disk, Network, Process, Security, Cloud, Logs)
2. ✅ Alert Engine with Hard Rules
3. ✅ Feedback Learning System
4. ✅ Knowledge-powered LLM Analysis (not just thresholds)
5. ✅ Root Cause Analysis Engine
6. ✅ Security Intelligence (attack pattern detection)
7. ✅ Cost Optimization Analysis
8. ✅ Predictive Analysis (trends, forecasting)
9. ✅ Interactive Q&A System
10. ✅ Personality (experienced SRE colleague)

### Architecture:
```
Telemetry → Atlas Capabilities → Smart Alert/Insight/Forecast/RCA
                       ↓
            Full LLM Knowledge + Personality
            Not just threshold checking
```

### System Prompts:
- Identity: AI SRE Engineer with 15+ years experience
- Telemetry Analysis: Context, patterns, correlation
- Security Excellence: Attack recognition, threat levels
- Cost Excellence: Idle resources, over-provisioning
- RCA Excellence: Chain of causation, prevention

---

# Contribution Summary (what is actually ours)

## Provenance

- **`pace_atlas/` is original to this fork.** Upstream
  `NousResearch/hermes-agent` has no `pace_atlas/` directory at all.
  All files under it were authored here (`git log` shows only fork commits;
  added in `cf6562857`, "rebrand to PACE Atlas").
- **Everything else is inherited upstream code**, rebranded: `pace_cli/`,
  `gateway/`, prompts, docs, and the agent runtime. None of that is a
  contribution; it is the fork base.

## Diff against upstream `main`

Measured `upstream/main...main` (the full fork):

```
393 files changed, 54,758 insertions(+), 9,512 deletions(-)
```

Breakdown:

| Scope | Size | Nature |
|-------|------|--------|
| `pace_atlas/` | 21 files, +6,012 | **Original contribution** — telemetry, alert engine, capabilities, runner |
| `pace_atlas/` agent-core additions | `config.py`, `notify.py`, `history.py`, `config.example.yaml` + `tests/pace_atlas/` (26 tests) | **Original contribution** (commit `c4b3e99c8`) |
| `pace_cli/`, `gateway/`, prompts, docs, website | ~370 files | Rebrand pass — string/name replacements on upstream code |
| `assets/banner.png` | 1 file | Replacement branding |

The agent-core additions (commit `c4b3e99c8`) are the most recent, standalone
piece of work: layered config with env inference, notification fan-out,
append-only alert history with repeat suppression, and a full `runner.py`
rebuild (daemon lifecycle, pidfile, signal handling, `--install-systemd`,
`--status`). 26 unit tests cover config/notify/history.

## Per-file breakdown of the contribution (`pace_atlas/`)

| File | Lines | What it is |
|------|-------|-----------|
| `telemetry/base.py` | 358 | `TelemetryCollector` ABC, `TelemetrySnapshot`, `CompositeCollector` |
| `telemetry/system.py` | 272 | CPU/load from `/proc` |
| `telemetry/memory.py` | 182 | `/proc/meminfo` reader |
| `telemetry/disk.py` | 246 | mounts, usage, inodes |
| `telemetry/network.py` | 252 | connections, TCP state |
| `telemetry/process.py` | 226 | process stats |
| `telemetry/security.py` | 296 | auth/SSH event collection |
| `telemetry/cloud.py` | 289 | cloud metadata + billing |
| `telemetry/logs.py` | 238 | log aggregation |
| `alert_engine/__init__.py` | 522 | `HardRules` thresholds, `AlertEngine` with LLM decision layer |
| `capabilities.py` | 623 | RCA, security, cost, predictive analyzers, interactive Q&A |
| `feedback/__init__.py` | 355 | alert feedback learning |
| `tools.py` | 758 | SRE tool surface for the agent runtime |
| `agent_runner.py` | 333 | agent-mode runner |
| `runner.py` | 344 | **rebuilt**: daemon, lifecycle, dedupe, notifications, `--install`/`--status` |
| `config.py` | 180 | *new*: YAML, env/.env inference, provider auto-detect |
| `notify.py` | 198 | *new*: console/file/webhook/telegram/email channels |
| `history.py` | 145 | *new*: JSONL ledger, repeat suppression, trends |

## Version History
- 0.1.0: Initial PACE Atlas with basic telemetry + hard rules
- 1.0.0: Complete SRE agent with all capabilities
- 0.1.0 (PyPI `pace-atlas`): slim standalone wheel of the agent — `pip install pace-atlas`