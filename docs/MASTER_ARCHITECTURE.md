# Project J.A.R.V.I.S. Master Architecture

Status: planning baseline
Date: 2026-09-01
Source: JARVIS Project Watch architecture conversation and bootstrap planning
Addenda: reliability, provenance, scoped capability, and memory architecture direction

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
11. Recoverability and causal traceability are product requirements. Important actions, beliefs, and persistent state changes should eventually answer what happened, why it happened, who or what authorized it, and whether recovery is possible.
12. Future architecture is not permission to create empty infrastructure. Add required fields and contracts when the relevant subsystem first appears; do not prebuild workers, skills, scheduler tables, vector indexes, graph databases, or update infrastructure before they are needed.

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

Selective perception should escalate from lower-risk context to higher-risk context:

```text
system metadata
-> active application/window metadata
-> structured UI data
-> explicitly attached document, page, or text
-> specific screenshot
-> vision model
```

Rules:

- Do not continuously screenshot the desktop and feed it to an LLM.
- Do not continuously stream workspaces, pages, or screens into models.
- Treat captured webpage, email, document, and screen text as untrusted data.
- Sensitive captures need policy controls and audit logs.
- Context attachments should eventually be previewable and removable where practical.
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

Durable memory should preserve provenance strongly enough for JARVIS to answer "How do you know that?" from recorded memory, event, or project history. Retrieval records should eventually expose fields equivalent to:

- Memory ID
- Content
- Source
- Confidence
- Observed-at timestamp
- Last-verified-at timestamp

Memory retrieval should represent answerability directly instead of forcing the model to infer uncertainty from missing context. Long-term retrieval states should include:

- `known`
- `probably_known`
- `conflicting`
- `stale`
- `unknown`

Knowledge gaps should be representable in the retrieval result. For example:

```json
{
  "answerability": "conflicting",
  "knowledge_gaps": [
    "Current preferred browser is unclear."
  ]
}
```

The system should eventually include a maintenance cycle that can merge duplicates, detect contradictions, summarize old episodes, promote useful facts, expire temporary facts, associate related memories, identify unfinished tasks, compress old conversations, and update project summaries.

Memory maintenance should identify duplicates, contradictions, superseded facts, stale facts, and facts requiring reverification. New facts may supersede older facts without destroying historical provenance.

Memory retrieval has two eventual paths:

Fast retrieval:

```text
FTS
+ metadata
+ entities
+ optional similarity retrieval
```

Use fast retrieval for normal conversation. "Fast memory" does not require a vector database now. FTS and metadata can come first; embeddings and vector search should be added only when useful.

Deep synthesis:

```text
retrieve
-> entity/relationship expansion
-> rerank
-> reconcile contradictions
-> synthesize
-> return provenance
```

Use deep synthesis only when the question genuinely requires expensive historical reasoning.

Relationship data may initially live in the relational database. The conceptual knowledge-graph shape is:

```text
entities

entity_links
  source_entity
  relationship
  target_entity
  confidence
  provenance
```

Example relationships include:

- `works_on`
- `knows`
- `owns`
- `uses`
- `prefers`
- `depends_on`
- `located_at`
- `related_to`
- `member_of`

Do not require Neo4j or another graph database unless real requirements justify it.

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

Future skill libraries must support explicit scopes:

```text
skills/
  system/
  shared/
  users/<user-id>/
  projects/<project-id>/
```

Scope meanings:

- System: trusted built-in JARVIS capabilities.
- Shared: capabilities intentionally available across the environment.
- User: identity-private capabilities.
- Project: capabilities relevant only to one project.

Every skill should eventually expose at least:

- Skill ID
- Version
- Scope
- Owner
- Permissions
- Trust level
- Source

Recommended lookup priority:

```text
active project
-> current user
-> shared
-> system
```

Conflicting names must never silently override one another. Skill resolution must be deterministic and auditable.

Do not implement a skill system before an active task requires it.

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
- Long-term events should use `event_id`, `correlation_id`, and `causation_id`.

Causal identifier semantics:

- `event_id`: unique identity for one event.
- `causation_id`: the immediate parent event or action that directly caused this event.
- `correlation_id`: the larger user operation, task, or trace that groups related events.

Example causal chain:

```text
conversation.message
-> intent.detected
-> tool.requested
-> sentinel.allowed
-> tool.executed
-> application.opened
```

JARVIS must eventually be able to reconstruct this chain from recorded events. Do not use an LLM to invent causal explanations after the fact.

Future recurring monitors and watchers must preserve state. Suggested fields include:

- Watcher ID
- Last checked-at timestamp
- Last successful-at timestamp
- Last result hash
- Last notification-at timestamp
- Known items
- Scratch state
- Failure count

Watcher flow should prefer deterministic change detection:

```text
fetch
-> hash relevant state
-> unchanged? stop
-> changed? AI evaluation if needed
```

Avoid duplicate alerts and unnecessary model cost. Do not implement scheduler persistence until a scheduling or watcher task requires it.

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

Future replaceable workers should expose:

- Heartbeat
- Health status
- Capabilities
- Last successful operation
- Last error
- Restart count

JARVIS Core supervises workers. Worker recovery should follow a bounded flow:

```text
failure
-> classify
-> bounded restart/backoff
-> health check
-> mark unavailable if recovery fails
```

Never retry forever. Worker failure must not crash JARVIS Core.

Future long-running specialist work must not block the primary conversation. A research, coding, or admin task may run in a background task or session while the user continues normal JARVIS interaction. Background work should preserve task identity and causal provenance back to the originating request.

Do not implement workers, background sessions, or agent orchestration before an active task requires them.

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

## Reliability, Lifecycle, And Health

JARVIS should remain operational when optional components fail. Optional provider or integration failures should degrade affected capabilities instead of killing the entire assistant. Core, Sentinel, and memory-critical failures may block affected functionality.

Standard subsystem health states:

- `HEALTHY`
- `DEGRADED`
- `UNAVAILABLE`
- `STARTING`
- `FAILED`

Example subsystem view:

```text
Core              HEALTHY
Memory            HEALTHY
Sentinel          HEALTHY
Windows Bridge    HEALTHY
Ollama            UNAVAILABLE
Home Assistant    UNAVAILABLE
```

JARVIS should disclose degraded capability when relevant rather than fail globally.

Long-term JARVIS must support transactional application updates:

```text
discover
-> download candidate
-> verify integrity
-> stage separately
-> rehearse/test migrations
-> start staged JARVIS
-> health/readiness checks
-> promote OR rollback
```

Transactional update requirements:

- Version identity
- Integrity/checksum verification
- Staged install
- Migration plan
- Health verification
- Rollback
- Audit record

The current working installation must remain recoverable until promotion succeeds. A failed update must never leave JARVIS partially upgraded.

For persistent data, migration rehearsal should use a staged, copied, or snapshotted environment where practical. The live database must not be irreversibly modified before backup and recovery requirements have been satisfied.

Failed upgrades should eventually:

```text
rollback
-> collect safe diagnostics
-> record migration, health, and component failures
-> create an UpdateFailure task
```

A future coding or debug worker may investigate in isolation. Repair workers must not modify the live installation without Sentinel authorization.

Resource pressure should protect essential authority and state before optional work.

Protect first:

1. Sentinel
2. JARVIS Core
3. Essential event and task state
4. Required OS or Windows bridge
5. Active user-control surfaces such as voice when configured

Sacrifice or degrade first:

- Idle specialist workers
- Background research
- Expensive local LLMs
- Optional caches or services

A local model must not be allowed to destabilize Core. The Intelligence Router should permit fallback providers when available.

Do not implement update infrastructure, resource management, or health supervision before an active task requires it.

## Causal Provenance And Explanations

For important actions, JARVIS should eventually answer from recorded system state:

- What happened?
- Why did it happen?
- Who or what authorized it?
- Can it be recovered or undone?

For important beliefs, JARVIS should eventually answer:

- What does JARVIS believe?
- Where did that information come from?
- How confident is it?
- Is it current, stale, or contradicted?

These are architectural capabilities, not after-the-fact debugging features.

The future Activity UI should expose recorded causal chains. Example:

```text
Spotify opened
|- requested by user voice command
|- interpreted as application.open
|- tool system.open_app
|- Sentinel ALLOW
`- launch succeeded
```

This explanation must be generated from recorded event provenance, not model speculation.

## Observability And Evals

JARVIS must be debuggable.

Observability direction:

- Structured logs
- Request IDs or correlation IDs
- Tool/action traces
- Provider latency and error records
- Clear startup errors
- Testable health checks
- Recorded causal chains for important actions
- Recorded provenance for important beliefs

Evaluation direction:

- Tool-routing tests
- Sentinel policy tests
- Prompt-injection resistance tests
- Memory extraction/retrieval tests
- Proactivity/interruption tests
- End-to-end task tests

Bootstrap v0.1 should include ordinary tests for the foundation it creates. More advanced evals belong later.

## Persistent Schema And Migration Discipline

Every future persistent schema change should document:

- Forward migration
- Compatibility considerations
- Migration tests
- Rollback or recovery strategy when practical

Migration tests should exercise realistic previous-version fixtures. Migration records must be written only after the migration completes successfully, and persistent data must not be deleted or recreated just to simplify upgrades.

Transactional updates and migration rehearsal are long-term architecture requirements, not permission to add an external migration framework or unused update system prematurely.

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

Also avoid adding empty scaffolding for:

- Workers
- Skill libraries
- Scheduler or watcher tables
- Vector databases
- Graph databases
- Update infrastructure

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

## Roadmap Timing For Cross-Cutting Contracts

Early, before retrofit becomes expensive:

- `event_id`, `correlation_id`, and `causation_id` semantics.
- Subsystem health-state contract when a subsystem registry appears.
- Skill scope field when a skill subsystem begins.
- Memory provenance fields when durable long-term memory begins.
- Scheduler state model when scheduling or watchers begin.

Do not create empty infrastructure merely to satisfy these future fields today.

Mid development:

- Degraded mode.
- Worker supervision.
- Knowledge-gap retrieval.
- Background specialist sessions.
- Project and user skill resolution.

Pre-1.0 hardening:

- Transactional updates.
- Automatic rollback.
- Resource-pressure handling.
- Migration recovery.
- Update triage.
- Causal Activity UI.

## Scope Discipline

The active task document controls the implementation scope. Architecture documents describe future direction, not permission to build everything now.

This architecture update does not expand Active Window Context v0.7. No current implementation milestone should automatically inherit every feature described here. The active task document remains the implementation scope authority.

When in doubt:

- Prefer a working vertical slice over broad unused infrastructure.
- Prefer fewer dependencies.
- Prefer explicit typed interfaces.
- Prefer tests that prove real behavior.
- Prefer asking for approval before risky side effects.
- Prefer documenting a future need over prematurely implementing it.
