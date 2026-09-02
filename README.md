# Project J.A.R.V.I.S.

Project J.A.R.V.I.S. is a local-first personal AI operating layer. The goal is not to build another chatbot. The goal is to build a persistent assistant core that owns identity, memory, context, permissions, tasks, tools, and orchestration while treating AI models as replaceable providers.

## Current Status

This repository contains the early JARVIS Core foundation. It starts a small local FastAPI service, initializes SQLite runtime storage, exposes health and text chat endpoints, defines typed contracts, and routes text intelligence through provider-neutral interfaces.

The current proposed and implemented milestones are documented in:

- `docs/tasks/BOOTSTRAP_V0.1.md`
- `docs/tasks/INTELLIGENCE_V0.2.md`

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

Ollama is optional for manual v0.2 chat verification. The automated tests do not require Ollama, network access, or external credentials.

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

The tests use fake and mocked providers for intelligence behavior. They do not require Ollama to be installed or running.

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
| `JARVIS_PROVIDER_TIMEOUT_SECONDS` | `30` |
| `JARVIS_SYSTEM_INSTRUCTION` | `You are JARVIS, a local-first personal AI assistant. Be concise, helpful, and honest.` |

## Verify Health

With the service running, verify the bootstrap health endpoint:

```bash
curl http://127.0.0.1:8000/v1/health
```

Expected semantic result:

```json
{"status":"ok","service":"jarvis-core","version":"0.1.0"}
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
{"message":"Hello, I am JARVIS.","provider":"ollama","model":"llama3.2","correlation_id":"manual-chat-1"}
```

The exact message text comes from the configured model. If `correlation_id` is omitted, JARVIS generates one and returns it.

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
export JARVIS_PROVIDER_TIMEOUT_SECONDS=30
```

On Windows PowerShell:

```powershell
$env:JARVIS_OLLAMA_BASE_URL = "http://127.0.0.1:11434"
$env:JARVIS_OLLAMA_MODEL = "llama3.2"
$env:JARVIS_PROVIDER_TIMEOUT_SECONDS = "30"
```

If Ollama is unavailable during `POST /v1/chat`, JARVIS returns a normalized provider error instead of exposing internal exceptions.

## Not Built Yet

The following are deliberately out of scope for the current early milestones:

- Voice interaction
- Speech recognition
- Text-to-speech
- Memory intelligence
- Vector search
- Windows automation
- Browser automation
- Tool calling
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
