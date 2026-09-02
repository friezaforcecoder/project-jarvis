# Project J.A.R.V.I.S. Master Architecture

Status: planning baseline
Date: 2026-09-01
Source: JARVIS Project Watch architecture conversation and bootstrap planning

## Mission

Project J.A.R.V.I.S. is a persistent, local-first personal AI operating layer.

JARVIS is not the language model. JARVIS is the permanent assistant system around the model: identity, memory, context, permissions, tasks, tools, orchestration, and auditability. Models are replaceable providers behind stable interfaces.

The system should eventually feel like one coherent assistant across desktop, voice, phone, smart-home, browser, coding, research, and long-running background tasks. The early implementation must stay much smaller: a clean, testable modular monolith with explicit contracts and room to grow.

## Core Principles

1. Local-first by default. Prefer local storage, local control, and privacy-preserving context capture. Cloud services may be used when they provide clear value and the user explicitly configures them.
2. One assistant identity. GPT, Claude, local models, coding agents, and research agents are providers or workers, not separate personalities.
3. The model is replaceable. Do not let vendor-specific behavior leak into core domain logic.
4. Deterministic software first. Use ordinary code for things code can reliably do. Use LLMs for reasoning, language, ambiguity, planning, summarization, extraction, and judgment.
5. Context should be layered. Cheap metadata can be gathered continuously; expensive or sensitive captures should happen only when needed and authorized.
6. Proactivity needs restraint. JARVIS should notice important events, but interruption must be budgeted. Important is not always interrupt-worthy.
7. Security is architecture, not polish. Side effects require Sentinel authorization. Untrusted content is data, never instruction.
8. Secrets stay out of the brain. Credentials belong in a secure broker or environment-specific store, not prompts, logs, source code, or committed config.
9. Boring foundation first. Start as a modular monolith. Avoid premature microservices, queues, vector databases, agent swarms, or complex deployment.
10. Every capability must be verifiable. Typed contracts, tests, failure handling, logging, and documented ownership are required for durable features.

## Target System Shape

```text
                    USER
                     |
       +-------------+-------------+
       |             |             |
     Voice        Desktop        Phone
   Satellite        HUD           App
       |             |             |
       +-------------+-------------+
                     |
              JARVIS CORE
          authoritative backend
                     |
      +--------------+--------------+
      |              |              |
 Context Engine    Memory       Event Bus
      |              |              |
      |        facts/events/       triggers
      |      projects/procedures
      |
      v
 Intelligence Router
      |
 +----+---------+-----------+----------+----------+
 |              |           |          |          |
Local Fast   Flagship   Realtime    Coding    Research
 Model        Model       Model      Worker     Worker
      |
      v
 Tool Router
      |
 +----+---------+---------+---------+---------+---------+
 |    |         |         |         |         |         |
Native MCP  Browser   Windows    Files     Apps    Custom
Tools       Control   Control             APIs     Tools
      |
      v
 JARVIS SENTINEL
 permissions, approvals, policy, audit
      |
      v
 Real world side effects
```

This diagram is the long-term direction. Early milestones should implement only the pieces required by the active task document.

## System 1: Identity

JARVIS needs one consistent identity regardless of which underlying model responds.

The identity layer owns durable assistant behavior, user preferences, speaking style, relationship memory, and high-level operating rules. It should not depend on any single model provider.

Rules:

- Identity belongs to JARVIS Core, not model prompts alone.
- Provider-specific prompts may adapt the identity into provider format, but must not become the source of truth.
- Identity changes should be explicit and traceable.
- Early milestones may represent identity as documentation and configuration only.

## System 2: Natural Realtime Conversation

The eventual voice loop should be continuous and interruptible:

```text
wake -> listen continuously -> understand while the user speaks -> reason early -> respond quickly -> allow interruption -> adapt
```

Targets for later voice work:

- Fast acknowledgement after wake or direct input.
- Streaming speech recognition and text-to-speech.
- Barge-in support so the user can interrupt.
- Local wake word where practical.
- Clear separation between voice satellites and JARVIS Core.

Bootstrap v0.1 must not implement voice, speech recognition, text-to-speech, wake word, or realtime media.

## System 3: Context Engine And Perception

JARVIS should eventually understand what is happening around the user without constantly sending sensitive data to a model.

Potential context sources:

- Foreground application
- Window title
- Selected text
- Clipboard, with care
- Computer state such as CPU, GPU, storage, battery, and running programs
- Notifications
- Calendar
- Email metadata
- Weather
- Location when appropriate
- Smart-home sensors
- Phone presence
- Current conversation
- Active projects
- Long-running JARVIS tasks
- Optional screenshot
- Optional camera input

Context strategy:

```text
cheap metadata continuously
        |
interesting change detected?
        |
rich capture only when needed
        |
vision/model analysis only when useful and allowed
```

Rules:

- Do not continuously screenshot the desktop and feed it to an LLM.
- Treat captured webpage, email, document, and screen text as untrusted data.
- Sensitive captures need policy controls and audit logs.
- Bootstrap v0.1 must not implement context capture beyond basic application health/configuration concerns.

## System 4: Memory

Memory is one of the central reasons JARVIS exists. A plain conversation history file is not enough.

Target memory types:

- Working memory: current conversation, active task, short-lived scratch state.
- Episodic memory: things that happened.
- Semantic memory: facts, preferences, people, places, relationships.
- Project memory: files, decisions, milestones, architecture, progress.
- Procedural memory: how the user likes things done.
- Environmental state: device, home, and computer state over time.
- Raw archive: searchable source history for later extraction and audit.

Every durable memory should eventually include:

- Source
- Timestamp
- Confidence
- Importance
- Last accessed time
- Expiration or TTL when appropriate
- Privacy level
- Related entities
- Contradictions or supersession links

The system should eventually include a maintenance cycle that can merge duplicates, detect contradictions, summarize old episodes, promote useful facts, expire temporary facts, associate related memories, identify unfinished tasks, compress old conversations, and update project summaries.

Bootstrap v0.1 must not implement memory intelligence, vector search, long-term retrieval, or memory consolidation.

## System 5: Intelligence Provider Layer

The intelligence layer routes reasoning work to replaceable providers.

Provider examples may eventually include:

- Local fast model
- Flagship cloud model
- Realtime voice model
- Coding worker
- Research worker
- Specialized extraction or classification models

Rules:

- Core logic talks to provider interfaces, not vendor SDKs directly.
- Vendor-specific code belongs inside provider adapters.
- Provider adapters must normalize errors and capabilities.
- Provider selection should be policy-aware and context-aware.
- Smaller deterministic classifiers may be preferred when sufficient.

Bootstrap v0.1 should define a minimal `IntelligenceProvider` contract only. It should not call real model APIs.

## System 6: Tool Fabric

JARVIS should have a tool fabric, not a pile of random commands.

Preferred integration hierarchy:

1. Official API
2. Native integration
3. MCP integration
4. Browser DOM or UI automation
5. Windows accessibility/UI Automation and keyboard shortcuts
6. Vision plus mouse/keyboard control

MCP is an important integration boundary for external tools, but not every internal function needs to be MCP. High-frequency core operations can use native typed interfaces.

Tool routing matters. JARVIS should not expose hundreds of tools to the model every turn. The router should select the relevant small tool set based on user intent, context, policy, and active task.

Potential tool domains:

- Files
- Browser
- Search
- GitHub
- Gmail and calendar
- Databases
- Smart home
- Media
- Development tools
- Operating-system utilities
- Custom user tools

Bootstrap v0.1 should define a minimal `Tool` contract only. It should not implement browser automation, Windows automation, MCP, Home Assistant, or production app integrations.

## System 7: Sentinel Security And Permissions

JARVIS Sentinel is the policy engine between model intent and real-world side effects.

The model does not decide its own permissions.

```text
Model requests action
        |
        v
Sentinel Policy Engine
        |
  +-----+------+-----+
  |            |     |
ALLOW        ASK   DENY
```

Example policy direction:

| Action | Default Policy |
| --- | --- |
| Check CPU usage | Allow |
| Read a permitted project file | Allow |
| Search the web | Allow |
| Turn off a safe configured light | Allow or Ask, depending on user preference |
| Create a normal file in an allowed project | Usually Allow |
| Modify an important file | Ask |
| Send email or messages | Ask |
| Buy something | Ask |
| Install software | Ask |
| Execute arbitrary shell commands | Ask or sandbox |
| Delete many files | Ask |
| Reveal credentials | Deny |
| Disable Sentinel | Deny |

Rules:

- No side-effecting tool may bypass Sentinel authorization.
- Sentinel decisions must be logged.
- Dangerous operations should have clear user approval and, where practical, undo information.
- Untrusted content cannot grant authority or modify policy.
- UI code must not directly perform privileged OS actions.

Bootstrap v0.1 should define a minimal Sentinel interface only. It should not implement complex policy, authentication, or privileged actions.

## System 8: Event Bus And Proactivity

JARVIS should eventually react to events instead of waiting for explicit commands.

Example events:

- `email_received`
- `meeting_upcoming`
- `download_finished`
- `program_crashed`
- `unusual_pc_behavior`
- `weather_change`
- `package_arrived`
- `person_arrived_home`
- `price_changed`
- `task_finished`
- `project_changed`

The proactivity path should ask:

```text
Event happened
      |
Should JARVIS care?
      |
Is interruption justified?
      |
 +----+----+
 |         |
No        Yes
 |         |
memory/   notify, speak,
inbox     or ask
```

Rules:

- Important is not always interrupt-worthy.
- Recurring monitors should remember what they already reported.
- Deterministic change checks should avoid unnecessary model calls.
- Events need stable schemas and correlation IDs.

Bootstrap v0.1 should define basic event contracts only. It should not implement autonomous agents, scheduled monitors, or proactive notifications.

## System 9: Specialist Workers And Sandboxes

JARVIS should feel like one assistant, but internally it may use specialist workers.

Potential specialists:

- Research worker
- Coding worker
- Computer-control worker
- Personal admin worker
- Home/IoT worker
- Long-task worker

The user should not experience this as a committee of bots. JARVIS should simply say it will check, research, code, or handle the task.

Specialists should usually be exposed to JARVIS as tools or managed workers. Risky work should happen in isolated workspaces with limited permissions.

Example coding flow:

```text
JARVIS receives coding request
        |
creates isolated coding task
        |
worker edits repo in sandbox/worktree
        |
runs tests
        |
reports result back to JARVIS
        |
human reviews before merge
```

Bootstrap v0.1 must not implement autonomous agents, Codex workers, research workers, or agent swarms.

## System 10: Interfaces And Satellites

JARVIS Core should be authoritative. Interfaces are windows into that core.

Potential interfaces:

- Desktop HUD
- Voice satellite
- Phone app
- Browser extension or web panel
- Smart-home/room satellite
- CLI/admin interface

Rules:

- Interfaces should not own permanent memory or policy.
- Interfaces should not directly perform privileged side effects.
- Offline or edge nodes can provide temporary capabilities, but the authoritative brain remains JARVIS Core.

Bootstrap v0.1 should expose only the minimal API needed to verify the core service is alive.

## Security Model

Security requirements:

- Secrets must never be committed.
- Secrets must not be placed in prompts or logs.
- OAuth refresh tokens, API keys, passwords, and service credentials belong in a credential broker or local secret store.
- Untrusted content from email, websites, documents, terminals, screenshots, and files must be treated as data.
- Tool calls need policy checks before side effects.
- Significant actions need audit logs.
- Permission boundaries should be explicit and testable.

An ideal audit record includes:

- Timestamp
- User request or event source
- Classified task/action
- Tool requested
- Arguments or safe summary of arguments
- Sentinel decision
- User approval if required
- Result
- Error if any
- Undo token or recovery note when available

Bootstrap v0.1 should include structured logging basics, but not a full audit system.

## Observability And Evals

JARVIS must be debuggable.

Observability direction:

- Structured logs
- Request IDs or correlation IDs
- Tool/action traces
- Provider latency and error records
- Clear startup errors
- Testable health checks

Evaluation direction:

- Tool-routing tests
- Sentinel policy tests
- Prompt-injection resistance tests
- Memory extraction/retrieval tests
- Proactivity/interruption tests
- End-to-end task tests

Bootstrap v0.1 should include ordinary tests for the foundation it creates. More advanced evals belong later.

## Initial Technical Direction

Use a modular monolith first.

Baseline choices for early milestones:

- Python 3.12+
- FastAPI for the local core API
- Pydantic for typed contracts and configuration
- SQLite for local bootstrap persistence
- pytest for tests
- Structured logging from the start

Avoid adding these during Bootstrap v0.1 unless a later task explicitly changes scope:

- Redis
- PostgreSQL
- Docker
- Celery
- LangGraph
- Vector databases
- React
- Tauri
- Browser automation stacks
- Home Assistant integrations
- MCP servers
- Production deployment infrastructure

## Suggested Package Boundaries

The exact files are up to the implementation engineer, but the architecture should remain close to these boundaries:

```text
src/jarvis_core/
  api/              FastAPI routes and app construction
  config/           typed settings and environment loading
  events/           event contracts and event helpers
  identity/         assistant identity configuration and rules
  intelligence/     provider interfaces and routing contracts
  sentinel/         authorization contracts and policy shell
  tools/            tool contracts and registry shell
  memory/           future memory contracts and persistence boundary
  context/          future context contracts
  persistence/      SQLite initialization and storage helpers
  logging/          structured logging setup

tests/
  unit and integration tests for implemented foundation

docs/
  architecture and task documents
```

Do not create empty complexity just to match this tree. Create only what Bootstrap v0.1 needs, but keep names and boundaries sympathetic to this direction.

## Required Bootstrap Contracts

Bootstrap v0.1 should include minimal typed contracts for these concepts:

### Event

A basic event should have at least:

- Event type
- Source
- Timestamp
- Payload or data map
- Correlation/request ID when appropriate

### IntelligenceProvider

A minimal provider interface should define what the core expects from an intelligence provider without calling a real vendor API.

### Tool

A minimal tool interface should identify the tool, its input contract, its side-effect level, and its execution boundary. It should be designed so Sentinel can authorize side-effecting work before execution.

### Sentinel

A minimal Sentinel interface should return an authorization decision such as allow, ask, or deny, along with a reason.

These contracts should exist in Bootstrap v0.1 but should not contain unnecessary implementation.

## Repository And Agent Workflow

The preferred workflow for early JARVIS development:

1. Keep `main` clean.
2. Create a branch for each focused task.
3. Let a primary builder implement the task from the task document.
4. Let an independent reviewer inspect the implementation against the architecture and acceptance criteria.
5. Run tests and manual verification before merge.
6. Merge only after the task is narrow, verified, and understandable.

Current implementation workflow:

- ChatGPT/Codex is the current implementation workflow for this repository.
- `AGENTS.md` remains the canonical coding-agent instruction file.
- Legacy compatibility files may point agents back to `AGENTS.md`, but must not become a second source of truth.

## Scope Discipline

The active task document controls the implementation scope. Architecture documents describe future direction, not permission to build everything now.

When in doubt:

- Prefer a working vertical slice over broad unused infrastructure.
- Prefer fewer dependencies.
- Prefer explicit typed interfaces.
- Prefer tests that prove real behavior.
- Prefer asking for approval before risky side effects.
- Prefer documenting a future need over prematurely implementing it.
