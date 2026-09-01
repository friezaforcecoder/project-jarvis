# Project J.A.R.V.I.S. Bootstrap v0.1

## Goal

Create the minimum working JARVIS Core foundation.

This milestone answers one question:

Can a coding agent build a clean, working foundation without expanding the project beyond the requested scope?

## Implement

- Project structure
- Python package
- FastAPI application
- Configuration system
- SQLite initialization
- Structured logging
- Basic event contracts
- `IntelligenceProvider` interface
- `Tool` interface
- `Sentinel` interface
- pytest
- `GET /v1/health`
- Startup documentation

## Do Not Implement

- Voice
- Speech recognition
- Text-to-speech
- Memory intelligence
- Vector search
- Windows automation
- Browser automation
- React UI
- Tauri
- Home Assistant
- MCP
- Autonomous agents
- Codex worker
- Research worker
- Skill Forge
- Complex authentication
- Production deployment

## Health Endpoint

`GET /v1/health`

Expected semantic result:

```text
status = ok
service = jarvis-core
version = current application version
```

The exact JSON shape may be chosen by the implementation engineer, but tests must verify these semantics.

## Acceptance Criteria

- Fresh clone can be installed using documented steps.
- JARVIS Core starts successfully.
- `GET /v1/health` returns success.
- SQLite database initializes without manual intervention.
- Tests pass.
- Provider, Tool, Sentinel, and Event contracts exist but contain no unnecessary implementation.
- No secrets are committed.
- No later milestone functionality is implemented.
- The structure follows `docs/MASTER_ARCHITECTURE.md`.

## Definition Of Done

Another developer should be able to perform these steps using README instructions without reverse-engineering the project:

1. Clone
2. Install
3. Test
4. Run
5. Verify health

## Constraints

- Use Python 3.12+.
- Use type annotations.
- Use Pydantic for external and architectural contracts.
- Use pytest.
- Keep the implementation boring and maintainable.
- Do not add Redis, PostgreSQL, Docker, Celery, LangGraph, vector databases, message brokers, React, Tauri, or microservices.
- Do not place vendor-specific AI code in the core architecture.
- Do not hide, delete, or weaken failing tests merely to claim completion.
- Do not silently change this task's acceptance criteria.

## Expected Completion Report

When implementation is complete, report:

- What was created
- Tests and actual results
- Manual startup and health-check verification
- Dependencies added
- Architecture decisions or compromises
- Anything incomplete
- Exact command to start JARVIS Core
