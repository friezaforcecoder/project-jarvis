# Project J.A.R.V.I.S. Agent Instructions

## Mission

Project J.A.R.V.I.S. is a persistent, local-first personal AI operating layer.

The authoritative architecture is:

`docs/MASTER_ARCHITECTURE.md`

Read the relevant sections of that document before making architectural changes.

## Core Architectural Rules

1. JARVIS owns identity, memory, context, permissions, tasks, tools, and orchestration. AI models are replaceable providers.
2. Do not add vendor-specific model logic outside provider adapters.
3. Do not bypass architectural module boundaries for convenience.
4. Do not introduce a new database, framework, permanent service, runtime, or major dependency without documenting the reason.
5. No side-effecting tool may bypass Sentinel authorization.
6. UI code must not directly perform privileged operating-system actions.
7. Do not expose secrets to prompts, logs, source control, or configuration committed to Git.
8. Prefer deterministic software over LLM calls whenever deterministic code can reliably perform the task.
9. Prefer this tool/integration order: API, native integration, MCP, DOM/UI automation, vision/coordinate control.
10. Do not implement speculative future architecture during a milestone unless the current task explicitly requires it.
11. Keep implementations simple. We are building a modular monolith first, not premature microservices.
12. Every new capability must have typed contracts, tests, failure handling, logging/observability, and documented ownership.

## Development Rules

Use Python 3.12+.

Use type annotations.

Use Pydantic for external and architectural contracts.

Use pytest.

Do not suppress failing tests merely to make CI pass.

Do not silently change acceptance criteria.

Do not commit generated secrets, `.env`, local databases, model files, caches, virtual environments, or IDE state.

Before declaring work complete:

1. Run the relevant tests.
2. Run the complete test suite when practical.
3. Verify startup from the documented command.
4. Verify acceptance criteria manually where applicable.
5. Report any remaining failures or compromises.

## Git

Do not work directly on `main`.

Do not force-push `main`.

Keep each task focused.

Avoid unrelated refactors.

Prefer small, understandable commits.

## Scope Discipline

The active task document defines what should be built.

Do not implement later milestones merely because their architecture is already described.

A working vertical slice is preferred over large amounts of unused infrastructure.

## Required Reading

For architecture:

`docs/MASTER_ARCHITECTURE.md`

For the current implementation milestone:

`docs/tasks/BOOTSTRAP_V0.1.md`
