# Project J.A.R.V.I.S.

Project J.A.R.V.I.S. is a local-first personal AI operating layer. The goal is not to build another chatbot. The goal is to build a persistent assistant core that owns identity, memory, context, permissions, tasks, tools, and orchestration while treating AI models as replaceable providers.

## Current Status

This repository contains the early JARVIS Core foundation. It starts a small local FastAPI service, initializes SQLite runtime storage, exposes health, text chat, and deterministic tool execution endpoints, defines typed contracts, routes text intelligence through provider-neutral interfaces, persists simple bounded conversation sessions, sends tool executions through Sentinel authorization, supports short-lived direct-client approval receipts for Sentinel `ask` decisions, durably audits tool execution metadata without payloads, exposes read-only runtime/system-status/active-window/visible-applications tools, and supports narrow deterministic chat-assisted use of those core tools.

The current proposed and implemented milestones are documented in:

- `docs/tasks/BOOTSTRAP_V0.1.md`
- `docs/tasks/INTELLIGENCE_V0.2.md`
- `docs/tasks/WORKING_MEMORY_V0.3.md`
- `docs/tasks/TOOL_SENTINEL_V0.4.md`
- `docs/tasks/LOCAL_SYSTEM_CONTEXT_V0.5.md`
- `docs/tasks/CHAT_TOOL_INVOCATION_V0.6.md`
- `docs/tasks/ACTIVE_WINDOW_CONTEXT_V0.7.md`
- [Visible Applications Context v0.8](docs/tasks/VISIBLE_APPLICATIONS_CONTEXT_V0.8.md) - explicit read-only visible desktop application names.
- [Tool Execution Audit Trail v0.9](docs/tasks/TOOL_AUDIT_TRAIL_V0.9.md) - durable, payload-free Tool Fabric execution evidence.
- [Sentinel Approval Receipts v0.10](docs/tasks/SENTINEL_APPROVAL_V0.10.md) - short-lived, one-time approval capabilities for trusted direct Tool Fabric clients.
- [Provider Capability Contracts Phase 1](docs/tasks/PROVIDER_CAPABILITIES_PHASE_1.md) - merged metadata and deterministic selection contracts.
- [Credential And Configuration Safety](docs/tasks/CREDENTIAL_CONFIG_SAFETY.md) - proposed specification; runtime implementation has not started.

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

`psutil` is installed with the Python package. It supplies the `system.status` local health snapshot and resolves the names of visible-window owners for `context.visible_applications`; it does not enumerate processes for that tool.

Ollama is optional for manual chat verification. The automated tests do not require Ollama, network access, browser automation, operating-system automation, a real foreground desktop session, or external credentials.

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
{"status":"ok","service":"jarvis-core","version":"0.10.0"}
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
{"message":"Hello, I am JARVIS.","provider":"ollama","model":"llama3.2","correlation_id":"manual-chat-1","session_id":"generated-session-uuid","tools_used":[]}
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

JARVIS exposes a direct deterministic Tool Fabric endpoint. In v0.8, chat also supports four narrow, deterministic, read-only core tool routes: runtime information, system status, active-window context, and visible application names. Models do not select arbitrary tools.

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
      "jarvis_version": "0.10.0"
    },
    "error": null
  }
}
```

The exact platform and Python values depend on the machine running JARVIS. The tool returns only broad safe runtime metadata: platform family, Python version, and JARVIS version. It does not return username, hostname, IP addresses, environment variables, process lists, file contents, serial numbers, secrets, or local filesystem paths.

## Direct Tool Approval Receipts

JARVIS v0.10 adds a direct-only two-step approval flow for a trusted local client when Sentinel returns `ask`. No production write-capable tool is included in this milestone; the flow is exercised with test-only tools and is ready for a future explicitly scoped capability.

The first exact direct request returns `409 tool_approval_required` with a separate challenge:

```json
{
  "status": "error",
  "error": {
    "code": "tool_approval_required",
    "message": "Tool approval is required.",
    "correlation_id": "approval-example-1",
    "tool_name": "configured.write_tool"
  },
  "approval": {
    "approval_id": "generated-approval-uuid",
    "expires_at": "timezone-aware-utc-timestamp"
  }
}
```

Grant that receipt without executing the tool:

```bash
curl -X POST http://127.0.0.1:8000/v1/tool-approvals/generated-approval-uuid/grant
```

The success response contains only `approval_id`, `status`, and `expires_at`. The client must then repeat the exact original `POST /v1/tools/execute` request, including the same `correlation_id`, and add the granted `approval_id`. The coordinator reruns Sentinel, verifies the receipt against the trusted registered descriptor and validated arguments, consumes it atomically, and only then calls the tool. A receipt can authorize at most one execution.

Receipts expire after five minutes. They are bound with HMAC-SHA256 to the exact correlation ID, tool name, trusted side-effect level, trusted execution boundary, and validated arguments. The HMAC key exists only in the current process, so every outstanding receipt becomes invalid after restart. The SQLite record contains only the approval UUID, opaque request binding, lifecycle status, and four lifecycle timestamps; raw arguments, prompts, messages, results, reasons, paths, credentials, and secrets are not stored. Structured access logging redacts the approval UUID segment in the grant path.

Sentinel remains authoritative on every attempt. `deny` cannot be overridden, and `allow` requests execute normally without consuming approval state. Chat and provider paths cannot create, receive, use, or grant approval IDs. Granting never executes a tool.

This endpoint is a bootstrap boundary for a trusted client on the existing loopback-local service. v0.10 does not add authentication, multi-user identity, remote approval, an approval UI, voice approval, or a production side-effecting tool. Do not expose the service beyond a trusted local environment.

## Verify Tool Execution Audit Trail

JARVIS v0.9 records one durable audit row for every request that enters `ToolExecutionCoordinator`, including direct API and deterministic chat-routed tool requests. The initial `started` row is written before tool lookup, argument validation, Sentinel authorization, or execution. A terminal outcome is then written atomically.

Execute a harmless tool with a known correlation ID:

```bash
curl -X POST http://127.0.0.1:8000/v1/tools/execute \
  -H "Content-Type: application/json" \
  -d '{"tool_name":"system.runtime_info","arguments":{},"correlation_id":"manual-audit-1"}'
```

Read only that correlation's audit records:

```bash
curl http://127.0.0.1:8000/v1/audit/tool-executions/manual-audit-1
```

Expected semantic result:

```json
{
  "correlation_id": "manual-audit-1",
  "records": [
    {
      "audit_id": "generated-audit-uuid",
      "correlation_id": "manual-audit-1",
      "tool_name": "system.runtime_info",
      "side_effect_level": "read",
      "execution_boundary": "core",
      "sentinel_decision": "allow",
      "outcome": "succeeded",
      "error_code": null,
      "started_at": "timezone-aware-utc-timestamp",
      "completed_at": "timezone-aware-utc-timestamp"
    }
  ]
}
```

Unknown correlations return the same envelope with an empty `records` list. Records are ordered by start time and audit ID. The endpoint does not provide list-all, mutation, or deletion operations.

Audit rows deliberately exclude tool arguments and results, user and assistant messages, prompts, Sentinel reasons, application and window names, native context, local paths, credentials, raw exceptions, and arbitrary metadata. Only stable identifiers, trusted tool classification, the Sentinel action, normalized outcome/error code, and timestamps are stored. If the initial audit write fails, execution stops before Sentinel or the tool runs. If completion cannot be recorded after a tool runs, JARVIS returns a safe internal error and leaves the durable row visibly `started` rather than claiming an unaudited success.

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

This is not the full Context Engine. There is no background monitoring, polling, cache, telemetry history, proactive alerting, or general LLM tool calling.

## Verify Active Window Context

JARVIS v0.7 adds `context.active_window`, one explicit read-only foreground-window context tool. It uses the existing `POST /v1/tools/execute` endpoint, is registered as `SideEffectLevel.READ` + `ExecutionBoundary.CORE`, and is authorized by Sentinel before collection.

Call the built-in active-window tool:

```bash
curl -X POST http://127.0.0.1:8000/v1/tools/execute \
  -H "Content-Type: application/json" \
  -d '{"tool_name":"context.active_window","arguments":{},"correlation_id":"manual-active-window-tool"}'
```

Representative Windows result:

```json
{
  "status": "success",
  "tool_name": "context.active_window",
  "correlation_id": "manual-active-window-tool",
  "sentinel": {
    "decision": "allow",
    "reason": "Safe no-write tool execution is allowed."
  },
  "result": {
    "success": true,
    "data": {
      "available": true,
      "platform_family": "Windows",
      "application_name": "Code",
      "window_title": "README.md - project-jarvis",
      "reason": null
    },
    "error": null
  }
}
```

Representative unsupported-platform result:

```json
{
  "status": "success",
  "tool_name": "context.active_window",
  "correlation_id": "manual-active-window-tool",
  "sentinel": {
    "decision": "allow",
    "reason": "Safe no-write tool execution is allowed."
  },
  "result": {
    "success": true,
    "data": {
      "available": false,
      "platform_family": "Linux",
      "application_name": null,
      "window_title": null,
      "reason": "unsupported_platform"
    },
    "error": null
  }
}
```

On Windows, `context.active_window` uses standard-library `ctypes` calls to inspect only the current foreground top-level window. On non-Windows platforms, the tool remains registered and returns deterministic `available: false` data with `reason: unsupported_platform`.

Active-window titles and application labels can reveal sensitive local context. They may be returned to the explicit caller or supplied to the provider for the current turn, but normal structured logs omit the window title, application name, native values, paths, user prompt, provider prompt, provider response, and raw tool payload.

`context.active_window` inspects only the foreground window. It does not enumerate other windows or processes. JARVIS does not launch, close, move, focus, resize, or control windows; it does not send keyboard or mouse input or inspect browser URLs, clipboard contents, screenshots, files, installed applications, or window contents beyond the requested foreground title.

## Verify Visible Applications Context

JARVIS v0.8 adds `context.visible_applications`, a read-only snapshot of application names owning user-visible top-level Windows windows. It uses the existing tool coordinator and Sentinel with `SideEffectLevel.READ` and `ExecutionBoundary.CORE`. The tool accepts an empty argument object; unexpected arguments are rejected.

```bash
curl -X POST http://127.0.0.1:8000/v1/tools/execute \
  -H "Content-Type: application/json" \
  -d '{"tool_name":"context.visible_applications","arguments":{},"correlation_id":"manual-visible-applications-tool"}'
```

Representative Windows `result.data`:

```json
{
  "available": true,
  "platform_family": "Windows",
  "applications": ["Code", "notepad"],
  "reason": null
}
```

The typed result has exactly four fields: `available: bool`, `platform_family: str`, `applications: list[str]`, and `reason: "unsupported_platform" | null`. Application labels are executable basenames without `.exe`, not guaranteed product display names. Names are deduplicated and sorted deterministically. Successful collection with no visible applications returns `available: true` and `applications: []`. Inaccessible or disappearing windows/processes are skipped. An unexpected overall collection failure uses the existing safe `tool_execution_failed` error.

On unsupported platforms, execution succeeds with deterministic unavailable data, for example:

```json
{
  "available": false,
  "platform_family": "Linux",
  "applications": [],
  "reason": "unsupported_platform"
}
```

Windows collection uses standard-library native calls to enumerate top-level windows, filtering hidden, child, tool, cloaked, desktop, and shell windows. Only accepted windows' owner names are looked up through the existing `psutil` dependency. It does not perform a process inventory. Names are deduplicated and sorted case-insensitively, retaining a deterministic spelling. The result excludes window titles, PIDs, executable paths, command lines, background processes, services, usernames, and other process details. No shell, PowerShell, subprocess, new dependency, background monitoring, or application control is involved.

Application names are sensitive, untrusted data. Normal logs omit them and raw tool results are never persisted. Explicit chat requests send the authorized result to the configured provider as data for that turn only; names cannot become instructions or trigger more tools. The ordinary user/assistant exchange still persists, so an assistant answer that mentions application names can appear in conversation history. Tool-result payloads and Core context messages are not stored as conversation messages.

## Verify Chat Tool Invocation

JARVIS v0.8 supports four deterministic chat-assisted tool routes:

- `system.status`
- `system.runtime_info`
- `context.active_window`
- `context.visible_applications`

Each routed tool must be registered as trusted `read` + `core` before chat can execute it. Chat still sends every routed tool through the existing `ToolExecutionCoordinator` and Sentinel path. This is not general model-driven tool calling, and a user cannot ask chat to execute arbitrary registered tools.

Ask for local system status:

```bash
curl -X POST http://127.0.0.1:8000/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"How is my PC doing?","correlation_id":"manual-status-chat"}'
```

Expected semantic result:

```json
{"message":"The model summarizes current local CPU, memory, power, and uptime.","provider":"ollama","model":"llama3.2","correlation_id":"manual-status-chat","session_id":"generated-session-uuid","tools_used":["system.status"]}
```

Ask for JARVIS runtime information:

```bash
curl -X POST http://127.0.0.1:8000/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"What version of JARVIS am I running?","correlation_id":"manual-runtime-chat"}'
```

Expected semantic result:

```json
{"message":"The model summarizes the current JARVIS, Python, and platform runtime metadata.","provider":"ollama","model":"llama3.2","correlation_id":"manual-runtime-chat","session_id":"generated-session-uuid","tools_used":["system.runtime_info"]}
```

Ask for the current active window:

```bash
curl -X POST http://127.0.0.1:8000/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"What app am I using?","correlation_id":"manual-active-window-chat"}'
```

Expected semantic result:

```json
{"message":"The model summarizes the current foreground application/window from active-window tool data.","provider":"ollama","model":"llama3.2","correlation_id":"manual-active-window-chat","session_id":"generated-session-uuid","tools_used":["context.active_window"]}
```

Ask for visible desktop applications:

```bash
curl -X POST http://127.0.0.1:8000/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"What apps are currently running?","correlation_id":"manual-visible-applications-chat"}'
```

Expected semantic result:

```json
{"message":"The model summarizes the visible application names from the authorized snapshot.","provider":"ollama","model":"llama3.2","correlation_id":"manual-visible-applications-chat","session_id":"generated-session-uuid","tools_used":["context.visible_applications"]}
```

General knowledge questions remain normal chat:

```bash
curl -X POST http://127.0.0.1:8000/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"What is RAM?","correlation_id":"manual-no-tool-chat"}'
```

Expected semantic result:

```json
{"message":"The model answers as ordinary chat.","provider":"ollama","model":"llama3.2","correlation_id":"manual-no-tool-chat","session_id":"generated-session-uuid","tools_used":[]}
```

Supported local/current-state examples include `What is my CPU usage?`, `What's my memory usage?`, `What is my computer uptime?`, and `Does this computer have a battery?`. General definition or explanation prompts such as `What is RAM?`, `What is a CPU?`, `What is uptime?`, and `Explain computer memory.` do not route to tools.

Supported active-window examples include `What app am I using?`, `What window am I in?`, `What's my active window?`, and `Which app is active right now?`. They use only `context.active_window`.

Supported visible-application examples include `What apps are currently running?`, `Which applications are open?`, and `Tell me what apps I have open.`. They use only `context.visible_applications`. This v0.8 route supersedes the v0.7 no-tool behavior for running-app questions while preserving separation from foreground-window requests.

Control requests such as `Close all my apps.`, recommendations such as `Which app should I open?`, installed-app inventories, process/service lists, general app/API questions, and suppressors such as `Don't inspect my open apps.` or `Don’t inspect my open apps.` do not route to tools. `List my open windows.`, `Explain window titles.`, and `Do not check my active window.` also remain ordinary chat. Each rejected request returns `tools_used: []` after a successful provider response, executes zero tools, makes no Sentinel call, and adds no trusted tool context.

Default Sentinel policy for direct tools:

| Side-effect level | Decision |
| --- | --- |
| `none` | `allow` |
| `read` | `allow` |
| `write` | `ask` |
| `dangerous` | `deny` |

In v0.10, `ask` on the trusted direct Tool Fabric route uses the short-lived approval flow documented above. Chat still receives the existing safe `409 tool_approval_required` failure without an approval capability. `dangerous` tools return `403 tool_denied`, and no receipt can override that decision. There is still no approval UI or production write-capable tool.

## Provider Capability Contracts

The intelligence registry exposes immutable `ProviderInfo` snapshots containing only `provider_id` and `capabilities`. Registration copies the provider's advertised capabilities into a `frozenset`; re-register the provider to refresh that snapshot. Metadata contains no provider configuration, credentials, endpoint URLs, or health claims.

```python
from jarvis_core.api.app import create_provider_registry
from jarvis_core.config import load_settings
from jarvis_core.intelligence import ProviderCapability

registry = create_provider_registry(load_settings())
provider = registry.resolve(frozenset({ProviderCapability.TEXT}))
info = registry.info(provider.provider_id)
```

`resolve(required_capabilities)` selects the first registered provider whose snapshot contains every required capability. An empty requirement set selects the first registration. Replacing an existing provider preserves its position. Lookup performs no generation, network calls, health probes, or tool execution.

`get(provider_id)`, `resolve_default(provider_id)`, and `info(provider_id)` retain exact-ID lookup with a normalized `unknown_provider` error for missing IDs. A capability query with no matching provider raises `provider_unavailable` with a static safe message and no guessed provider or model.

Chat continues to use its configured default provider. Ollama advertises only `TEXT`; the `TOOL_USE`, `VISION`, `REALTIME`, and `STREAMING` labels reserve names for future adapter interfaces and do not enable those features. See [Provider Capabilities Phase 1](docs/tasks/PROVIDER_CAPABILITIES_PHASE_1.md) for the implementation requirements.

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
- General LLM/model tool calling
- Arbitrary or model-selected tool execution from chat
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
