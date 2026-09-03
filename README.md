# Project J.A.R.V.I.S.

Project J.A.R.V.I.S. is a local-first personal AI operating layer. The goal is not to build another chatbot. The goal is to build a persistent assistant core that owns identity, memory, context, permissions, tasks, tools, and orchestration while treating AI models as replaceable providers.

## Current Status

This repository contains the early JARVIS Core foundation. It starts a small local FastAPI service, initializes SQLite runtime storage, exposes health, text chat, and direct deterministic tool execution endpoints, defines typed contracts, routes text intelligence through provider-neutral interfaces, persists simple bounded conversation sessions, sends direct tool executions through Sentinel authorization, and exposes one safe local system-status tool.

The current proposed and implemented milestones are documented in:

- `docs/tasks/BOOTSTRAP_V0.1.md`
- `docs/tasks/INTELLIGENCE_V0.2.md`
- `docs/tasks/WORKING_MEMORY_V0.3.md`
- `docs/tasks/TOOL_SENTINEL_V0.4.md`
- `docs/tasks/LOCAL_SYSTEM_CONTEXT_V0.5.md`

## Source Of Truth

Read these before making project changes:

- `docs/MASTER_ARCHITECTURE.md` - architecture, boundaries, security model, and long-term direction.
- `docs/tasks/*.md` - active milestone task documents.
- `AGENTS.md` - canonical coding-agent instructions.
- `CLAUDE.md` - legacy compatibility pointer back to `AGENTS.md`.

## Early Workflow

- Keep `main` clean.
- Do not work directly on `main`.
- Use a focused branch for each milestone or task.
- Open a pull request back to `main` when a task is ready for review.
- Do not commit secrets, local `.env` files, local databases, caches, model files, or generated runtime artifacts.

ChatGPT/Codex is the current implementation workflow for this repository. A human reviews changes before merge.

## Local Requirements

Early milestones should stay intentionally small. The expected local requirements are:

- Git
- Python 3.12+

`psutil` is installed with the Python package and is used only for the v0.5 `system.status` local health snapshot.

Ollama is optional for manual chat verification. The automated tests do not require Ollama, network access, browser automation, operating-system automation, or external credentials.

Do not add a large stack during early milestones. Node, Tauri, Whisper, TTS, Home Assistant, browser automation, MCP, and richer UI work belong to later milestones unless a future task explicitly changes that scope.

## Install

Clone the repository, create a virtual environment, and install the package with its test dependencies:

```bash
git clone https://github.com/friezaforcecoder/project-jarvis.git
cd project-jarvis
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

On Windows PowerShell, activate the virtual environment with:

```powershell
.\.venv\Scripts\Activate.ps1
```

## Test

Run the complete test suite:

```bash
python -m pytest
```

The tests use fake and mocked providers for intelligence behavior and deterministic in-process tools for Tool Fabric behavior. They do not require Ollama to be installed or running.

## Run

Start JARVIS Core:

```bash
python -m jarvis_core
```

By default, the service listens on `127.0.0.1:8000` and creates its SQLite database at `data/jarvis-core.sqlite3`. The `data/` directory is local runtime state and is ignored by Git.

Configuration is read from environment variables:

| Variable | Default |
| --- | --- |
| `JARVIS_ENVIRONMENT` | `local` |
| `JARVIS_DATABASE_PATH` | `data/jarvis-core.sqlite3` |
| `JARVIS_LOG_LEVEL` | `INFO` |
| `JARVIS_HOST` | `127.0.0.1` |
| `JARVIS_PORT` | `8000` |
| `JARVIS_INTELLIGENCE_PROVIDER` | `ollama` |
| `JARVIS_OLLAMA_BASE_URL` | `http://127.0.0.1:11434` |
| `JARVIS_OLLAMA_MODEL` | `llama3.2` |
| `JARVIS_PROVIDER_TIMEOUT_SECONDS` | `60` |
| `JARVIS_CHAT_HISTORY_LIMIT` | `10` |
| `JARVIS_SYSTEM_INSTRUCTION` | `You are JARVIS, a local-first personal AI assistant. Be concise, helpful, and honest.` |

## Verify Health

With the service running, verify the bootstrap health endpoint:

```bash
curl http://127.0.0.1:8000/v1/health
```

Expected semantic result:

```json
{"status":"ok","service":"jarvis-core","version":"0.5.0"}
```

## Verify Chat

With the service running, verify the text chat endpoint:

```bash
curl -X POST http://127.0.0.1:8000/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"Say hello in one short sentence.","correlation_id":"manual-chat-1"}'
```

Expected semantic result:

```json
{"message":"Hello, I am JARVIS.","provider":"ollama","model":"llama3.2","correlation_id":"manual-chat-1","session_id":"generated-session-uuid"}
```

The exact message text comes from the configured model. If `correlation_id` is omitted, JARVIS generates one and returns it. If `session_id` is omitted, JARVIS generates a new UUID session, persists the successful exchange, and returns that session ID.

## Working Memory Sessions

`correlation_id` identifies one request for tracing. `session_id` identifies a durable SQLite conversation session.

Continue an existing session by sending the returned `session_id`:

```bash
curl -X POST http://127.0.0.1:8000/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"What did I ask you to do?","session_id":"returned-session-uuid","correlation_id":"manual-chat-2"}'
```

JARVIS loads up to `JARVIS_CHAT_HISTORY_LIMIT` prior persisted messages, drops a leading orphaned assistant message after truncation, adds the configured system instruction, and sends the resulting ordered provider-neutral messages to the configured provider.

Sessions survive restarts when JARVIS Core is started with the same `JARVIS_DATABASE_PATH`.

Same-session chat requests are serialized within a single JARVIS Core process. Cross-process or multi-worker session coordination is out of scope for v0.3.

Unknown well-formed sessions return a stable 404 response before provider execution:

```json
{"status":"error","error":{"code":"session_not_found","message":"Conversation session was not found.","correlation_id":"manual-chat-missing","session_id":"11111111-1111-4111-8111-111111111111"}}
```

Malformed session IDs are rejected with request validation before provider execution. Provider failures persist nothing from the failed turn; a newly generated session does not become durable if the provider fails.

## Verify Tool Execution

JARVIS v0.4 adds a direct deterministic Tool Fabric endpoint. Chat does not call tools yet, and models do not select tools yet.

Call the harmless built-in runtime-info tool:

```bash
curl -X POST http://127.0.0.1:8000/v1/tools/execute \
  -H "Content-Type: application/json" \
  -d '{"tool_name":"system.runtime_info","arguments":{}}'
```

Expected semantic result:

```json
{
  "status": "success",
  "tool_name": "system.runtime_info",
  "correlation_id": "generated-correlation-id",
  "sentinel": {
    "decision": "allow",
    "reason": "Safe no-write tool execution is allowed."
  },
  "result": {
    "success": true,
    "data": {
      "platform_family": "Windows",
      "python_version": "3.12.x",
      "jarvis_version": "0.5.0"
    },
    "error": null
  }
}
```

The exact platform and Python values depend on the machine running JARVIS. The tool returns only broad safe runtime metadata: platform family, Python version, and JARVIS version. It does not return username, hostname, IP addresses, environment variables, process lists, file contents, serial numbers, secrets, or local filesystem paths.

## Verify Local System Status

JARVIS v0.5 adds `system.status`, one safe read-only local system context tool. It uses the existing `POST /v1/tools/execute` endpoint, is registered as `SideEffectLevel.READ` + `ExecutionBoundary.CORE`, and is authorized by the default Sentinel `read -> allow` policy.

Call the built-in system-status tool:

```bash
curl -X POST http://127.0.0.1:8000/v1/tools/execute \
  -H "Content-Type: application/json" \
  -d '{"tool_name":"system.status","arguments":{}}'
```

Representative result:

```json
{
  "status": "success",
  "tool_name": "system.status",
  "correlation_id": "generated-correlation-id",
  "sentinel": {
    "decision": "allow",
    "reason": "Safe no-write tool execution is allowed."
  },
  "result": {
    "success": true,
    "data": {
      "cpu": {
        "usage_percent": 12.5,
        "logical_core_count": 16,
        "physical_core_count": 8
      },
      "memory": {
        "total_bytes": 34359738368,
        "available_bytes": 20000000000,
        "used_bytes": 14359738368,
        "usage_percent": 41.8
      },
      "power": {
        "battery_present": false,
        "battery_percent": null,
        "plugged_in": null
      },
      "system": {
        "uptime_seconds": 123456.0
      }
    },
    "error": null
  }
}
```

`system.status` uses `psutil` for CPU usage, CPU counts, memory, battery state, and boot time. This keeps the implementation cross-platform for Windows and Linux CI without shell, PowerShell, WMI, subprocess calls, or hand-written operating-system collectors.

The tool deliberately excludes username, hostname, IP and MAC addresses, network interfaces, environment variables, processes, command lines, files, paths, drives, mounts, serial numbers, device IDs, account data, secrets, clipboard contents, screenshots, window titles, installed applications, and arbitrary file contents. It does not perform disk/storage enumeration.

This is not the full Context Engine. There is no background monitoring, polling, cache, telemetry history, proactive alerting, or chat/LLM tool calling in v0.5.

Default Sentinel policy for direct tools:

| Side-effect level | Decision |
| --- | --- |
| `none` | `allow` |
| `read` | `allow` |
| `write` | `ask` |
| `dangerous` | `deny` |

In v0.4, `ask` means the API returns `409 tool_approval_required`; no approval UI or approval persistence exists yet. `dangerous` tools return `403 tool_denied`. Tools execute only when Sentinel returns `allow`.

## Ollama

JARVIS Core starts without calling Ollama. Ollama is contacted only when `POST /v1/chat` routes to the `ollama` provider.

Install and start Ollama outside this repository, then pull a local model:

```bash
ollama pull llama3.2
```

Configure a different Ollama URL or model with environment variables:

```bash
export JARVIS_OLLAMA_BASE_URL=http://127.0.0.1:11434
export JARVIS_OLLAMA_MODEL=llama3.2
export JARVIS_PROVIDER_TIMEOUT_SECONDS=60
export JARVIS_CHAT_HISTORY_LIMIT=10
```

On Windows PowerShell:

```powershell
$env:JARVIS_OLLAMA_BASE_URL = "http://127.0.0.1:11434"
$env:JARVIS_OLLAMA_MODEL = "llama3.2"
$env:JARVIS_PROVIDER_TIMEOUT_SECONDS = "60"
$env:JARVIS_CHAT_HISTORY_LIMIT = "10"
```

If Ollama is unavailable during `POST /v1/chat`, JARVIS returns a normalized provider error instead of exposing internal exceptions.

## Not Built Yet

The following are deliberately out of scope for the current early milestones:

- Voice interaction
- Speech recognition
- Text-to-speech
- Semantic long-term memory
- Vector search
- Windows automation
- Browser automation
- LLM/model tool calling
- Automatic tool selection from chat
- Streaming responses
- React UI
- Tauri
- Home Assistant
- MCP integrations
- Autonomous agents
- Codex worker
- Research worker
- Skill Forge
- Production deployment
