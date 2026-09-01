# Project J.A.R.V.I.S.

Project J.A.R.V.I.S. is a local-first personal AI operating layer. The goal is not to build another chatbot. The goal is to build a persistent assistant core that owns identity, memory, context, permissions, tasks, tools, and orchestration while treating AI models as replaceable providers.

## Current Status

This repository is in foundation setup only. No JARVIS runtime features have been implemented yet.

The first implementation milestone is documented in:

`docs/tasks/BOOTSTRAP_V0.1.md`

## Source Of Truth

Read these before making project changes:

- `docs/MASTER_ARCHITECTURE.md` - architecture, boundaries, security model, and long-term direction.
- `docs/tasks/BOOTSTRAP_V0.1.md` - the first narrow implementation ticket.
- `AGENTS.md` - Codex-facing repo instructions.
- `CLAUDE.md` - Claude-facing repo instructions.

## Early Workflow

- Keep `main` clean.
- Do not work directly on `main`.
- Use a focused branch for each milestone or task.
- Open a pull request back to `main` when a task is ready for review.
- Do not commit secrets, local `.env` files, local databases, caches, model files, or generated runtime artifacts.

The intended first build flow is:

1. Claude performs the initial Bootstrap v0.1 implementation on a branch such as `claude/bootstrap-v0.1`.
2. Codex independently reviews and fixes only concrete issues.
3. A human reviews the result before merge.

## First Local Requirements

Bootstrap v0.1 should stay intentionally small. The expected local requirements are:

- Git
- Python 3.12+

Do not add a large stack during the bootstrap milestone. Node, Tauri, Whisper, TTS, Home Assistant, browser automation, MCP, and richer UI work belong to later milestones unless a future task explicitly changes that scope.

## Not Built Yet

The following are deliberately out of scope for the initial repository setup and Bootstrap v0.1:

- Voice interaction
- Speech recognition
- Text-to-speech
- Memory intelligence
- Vector search
- Windows automation
- Browser automation
- React UI
- Tauri
- Home Assistant
- MCP integrations
- Autonomous agents
- Codex worker
- Research worker
- Skill Forge
- Production deployment
