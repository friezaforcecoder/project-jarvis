# Personal Jarvis Architecture Harvest

Status: selective-harvest decision accepted; Provider Capability Contracts Phase 1 merged
Date: 2026-09-11
Audience: Ryan, JARVIS Builder, future reviewers
Source of truth: Project J.A.R.V.I.S. `AGENTS.md`, `docs/MASTER_ARCHITECTURE.md`, and the current repository state

## Executive Decision

Use **Strategy A: Selective Harvest**.

Personal Jarvis is useful as a mature reference system. It has strong ideas around provider contracts, capability-driven routing, live provider testing, voice/realtime abstractions, worker isolation, critic review, config mutation safety, channel adapters, and documentation discipline. Those ideas should shape Project J.A.R.V.I.S.

Project J.A.R.V.I.S. should not become a fork of Personal Jarvis. JARVIS already has a clearer long-term ownership model: JARVIS Core owns identity, long-term memory, context and attention, Sentinel, causal provenance, project awareness, proactivity, device presence, tasks, events, and orchestration philosophy. Personal Jarvis code should be adapted only when it strengthens those boundaries.

## Current Project J.A.R.V.I.S. State

The current Project J.A.R.V.I.S. mainline is still a lean modular monolith with FastAPI, Pydantic, SQLite, structured logging, provider contracts, chat routing, tool contracts, Sentinel policy, and local context foundations. [PR #10](https://github.com/friezaforcecoder/project-jarvis/pull/10) merged active-window context v0.7 on 2026-09-11 at `b3a1a3e26e844d57105e5609509b2930ae97e1f1`.

[PR #11](https://github.com/friezaforcecoder/project-jarvis/pull/11) landed the documentation-only harvest, accepted selective-harvest decision, and Phase 1 specification at `7a7a8211f14c8dea34bdd568c9e30a2a4338daa0`. [PR #12](https://github.com/friezaforcecoder/project-jarvis/pull/12) then implemented Provider Capability Contracts Phase 1 and merged at `c436d5c69f1919ca3eb2beb793ee275b05210f01`. The next task is the documentation-only [Credential And Configuration Safety](tasks/CREDENTIAL_CONFIG_SAFETY.md) specification; its runtime work remains deferred until a concrete consumer and implementation scope are defined.

## Reviewed Personal Jarvis Sources

Primary external repository:

- https://github.com/PersonalJarvis/PersonalJarvis
- https://github.com/PersonalJarvis/PersonalJarvis/blob/main/README.md
- https://github.com/PersonalJarvis/PersonalJarvis/blob/main/AGENTS.md
- https://github.com/PersonalJarvis/PersonalJarvis/blob/main/SECURITY.md
- https://github.com/PersonalJarvis/PersonalJarvis/blob/main/LICENSE
- https://github.com/PersonalJarvis/PersonalJarvis/blob/main/NOTICE

Subsystem source files and docs reviewed:

- https://github.com/PersonalJarvis/PersonalJarvis/blob/main/jarvis/core/protocols.py
- https://github.com/PersonalJarvis/PersonalJarvis/blob/main/jarvis/core/capabilities.py
- https://github.com/PersonalJarvis/PersonalJarvis/blob/main/jarvis/brain/provider_registry.py
- https://github.com/PersonalJarvis/PersonalJarvis/blob/main/jarvis/brain/provider_test.py
- https://github.com/PersonalJarvis/PersonalJarvis/blob/main/jarvis/brain/factory.py
- https://github.com/PersonalJarvis/PersonalJarvis/blob/main/docs/adr/0011-router-pure-dispatcher.md
- https://github.com/PersonalJarvis/PersonalJarvis/blob/main/jarvis/safety/tool_executor.py
- https://github.com/PersonalJarvis/PersonalJarvis/blob/main/jarvis/safety/risk_tier.py
- https://github.com/PersonalJarvis/PersonalJarvis/blob/main/jarvis/core/config.py
- https://github.com/PersonalJarvis/PersonalJarvis/blob/main/jarvis/core/config_writer.py
- https://github.com/PersonalJarvis/PersonalJarvis/blob/main/jarvis/core/self_mod/writer.py
- https://github.com/PersonalJarvis/PersonalJarvis/blob/main/jarvis/realtime/protocol.py
- https://github.com/PersonalJarvis/PersonalJarvis/blob/main/jarvis/realtime/factory.py
- https://github.com/PersonalJarvis/PersonalJarvis/blob/main/jarvis/channels/base.py
- https://github.com/PersonalJarvis/PersonalJarvis/blob/main/jarvis/channels/manager.py
- https://github.com/PersonalJarvis/PersonalJarvis/blob/main/jarvis/missions/manager.py
- https://github.com/PersonalJarvis/PersonalJarvis/blob/main/jarvis/missions/state_machine.py
- https://github.com/PersonalJarvis/PersonalJarvis/blob/main/jarvis/missions/missions_schema.sql
- https://github.com/PersonalJarvis/PersonalJarvis/blob/main/docs/adr/0009-self-healing-worker-critic.md
- https://github.com/PersonalJarvis/PersonalJarvis/blob/main/wiki/obsidian-vault/schema.md
- https://github.com/PersonalJarvis/PersonalJarvis/blob/main/docs/adr/0013-knowledge-wiki-architecture.md
- https://github.com/PersonalJarvis/PersonalJarvis/blob/main/docs/LLM-CONTEXT.md
- https://github.com/PersonalJarvis/PersonalJarvis/blob/main/docs/BUGS.md

## Architecture Fit

```text
Personal Jarvis ideas worth harvesting
        |
        v
Provider contracts, capability metadata, tests, worker isolation,
critic review, safe config writes, credential access patterns,
voice/channel protocols, headless setup, documentation practice
        |
        v
Project J.A.R.V.I.S. Core
        |
        +-- owns identity
        +-- owns memory and provenance
        +-- owns context and attention
        +-- owns Sentinel and permissions
        +-- owns task/event orchestration
        +-- owns platform strategy
        |
        v
Selective, typed, tested implementation milestones
```

Do not invert this relationship. Personal Jarvis is input material. Project J.A.R.V.I.S. remains the product and architecture authority.

## Subsystem Harvest Matrix

| Subsystem | Decision | Reason | Reusable code? | Integration difficulty | Risks | Recommended milestone |
| --- | --- | --- | --- | --- | --- | --- |
| Provider architecture | Adapt and port concepts | Personal Jarvis has useful provider protocols, plugin discovery, capability checks, error classification, fallback thinking, and contract tests. JARVIS already has a minimal provider contract and should evolve it without importing vendor decisions into core. | Small contract shapes and test ideas can be reused after license review; adapters should be new. | Medium | Vendor leakage, fallback policy drift, secret exposure, too many dependencies. | Provider Capability Contracts Phase 1 completed in PR #12; broader provider hardening remains future scope. |
| STT, TTS, wake, realtime provider model | Adapt later | The protocol split between STT, TTS, wake word, and full-duplex realtime is strong. Project J.A.R.V.I.S. should keep voice satellites separate from Core and add these only when voice becomes active scope. | Reference and selectively port protocol ideas; avoid copying full speech pipeline. | High | Audio stack complexity, local model downloads, device-specific bugs, latency regressions. | Voice foundation milestone, not before provider capability hardening. |
| Lean router and brain architecture | Adapt | The "router stays small" discipline matches JARVIS. The exact Personal Jarvis router has grown product-specific tools and should not be copied. JARVIS should keep deterministic routing, narrow tool exposure, and strong regression tests. | Concepts and routing tests are reusable; exact tool list is not. | Medium | Router becoming a dumping ground; LLM deciding policy; false tool triggers. | Intelligence routing hardening. |
| Capability registry | Adapt | A capability registry is a good way to describe action surfaces by verbs, objects, source, risk, and evidence needs. JARVIS should eventually use this for tool discovery and policy-aware routing. | Possible small model inspiration; implement under JARVIS contracts. | Medium | Regex overreach, language coupling, duplicated policy fields. | Tool Fabric capability milestone. |
| Mission and specialist worker system | Adapt later | Worktree-per-task, state machine, event store, cancellation, bounded recovery, and result reading are valuable. The full Personal Jarvis mission stack is too large for current JARVIS and assumes existing agent CLIs/UI flows. | Reference architecture first; port only after a JARVIS worker contract exists. | High | Cost, orphan processes, state recovery, file races, review burden, platform differences. | Specialist Worker MVP after events/provenance baseline. |
| Critic and independent review | Adapt later | Evidence-grounded critic review is a strong pattern for coding, research, and sensitive autonomous work. In JARVIS, critic should verify signed observations and artifacts, not become a second personality. | Prompt/test patterns can inform design; implementation should be native. | Medium to high | Sycophancy, invented defects, excessive retries, cost, false approval. | Worker MVP follow-up. |
| Tool execution choke point | Reference and adapt | Personal Jarvis has a clear "only executor may run tools" rule, risk evaluation, approval handling, and action event logging. JARVIS already has ToolExecutionCoordinator plus Sentinel; keep that path and strengthen it. | Use as reference; do not replace current Tool Fabric. | Medium | Bypass paths, direct tool calls, approval confusion, unsafe UI-triggered actions. | Sentinel/tool audit hardening. |
| Sentinel and risk policy | Reference only | JARVIS Sentinel must remain contextual and provenance-aware. Personal Jarvis risk tiers, blacklist/whitelist precedence, and approval-surface handling are useful, but wholesale adoption would flatten JARVIS policy. | No wholesale copy. Borrow specific tests and rule patterns. | Medium | Underpowered policy, model-controlled permissions, missed side effects. | Sentinel v0.x policy expansion. |
| Config safety and self-modification | Adapt | Atomic write, pre-validation, backup, reload test, rollback, audit, and a lock around provider switching are excellent patterns. JARVIS should adopt the pipeline shape when mutable config arrives. | Pattern is reusable; code is product-specific. | Medium | Corrupt config, config watcher loops, unsafe self-modification, settings drift. | Config mutation milestone. |
| Secrets and credentials | Adapt | The single secret access point, OS credential store priority, environment fallback, and refusal to accept secrets through chat/voice fit JARVIS. | Implement a JARVIS credential broker; do not copy provider-specific mapping wholesale. | Medium | Secrets in prompts/logs/config, inconsistent provider credential lookup, headless storage risk. | Credential broker milestone. |
| Voice provider architecture | Adapt later | Personal Jarvis has more lived voice engineering than JARVIS. The main value is the separation of realtime, STT, TTS, wake, VAD, interruption, and fallback responsibilities. | Protocol ideas only at first. | High | Latency, barge-in bugs, platform audio variance, privacy exposure. | Voice foundation after provider/credential work. |
| Channel architecture | Adapt later | Channel adapters for chat, web, Telegram, Discord, and similar surfaces match the JARVIS rule that interfaces are satellites and Core stays authoritative. | Interface ideas can be reused; channel implementations should be new or connector-specific. | Medium to high | Channels owning memory/policy, duplicate identity prompts, inconsistent approvals. | Interfaces/satellites milestone. |
| Headless operation | Adapt | Personal Jarvis treats no-audio/no-GPU/headless startup as a first-class requirement. That strongly fits JARVIS, especially Linux Tier 2. | Requirements and tests are reusable; code likely needs rewrite. | Medium | Import-time native dependency failures, optional component startup crashes. | Continuous foundation hardening. |
| Installer and setup experience | Reference now, adapt later | One-command setup, provider tests, local model checks, and guided setup are useful, but premature for current JARVIS. | No code now. Use as reference for a future setup milestone. | High | Installer security, cross-platform failures, large downloads, support burden. | Setup/installer milestone after core capabilities stabilize. |
| Documentation discipline | Adapt now | Personal Jarvis maintains ADRs, bug-class docs, LLM context docs, and exact regression references. JARVIS should adopt the discipline without copying stale project-specific assumptions. | Yes, document structure and review practice. | Low to medium | Docs becoming second source of truth, stale instructions. | Immediate docs milestone. |
| Memory/wiki system | Reference only | Personal Jarvis uses a Markdown knowledge wiki plus awareness. JARVIS memory target is richer: provenance, confidence, answerability states, contradiction/supersession, project memory, maintenance, and deep synthesis. | Do not use as canonical memory. Wiki ideas may become an export/editing view. | Medium to high | Losing provenance, treating prose notes as facts, underpowered retrieval. | Memory milestone, but JARVIS-native. |
| Computer control and visual automation | Reference only, adapt as fallback | Personal Jarvis has live desktop control, but JARVIS has a stricter integration hierarchy: API, native integration, MCP, DOM/UI automation, Windows UI Automation/accessibility, vision, then pixel control. | No primary reuse. Reference fallback mechanics only. | High | Unsafe clicks/types, prompt injection from screen text, brittle UI automation. | Desktop control fallback milestone only after safer layers. |
| Desktop UI framework | Evaluate, do not inherit | Personal Jarvis uses a desktop WebView and React-style frontend patterns. Project J.A.R.V.I.S. likely wants React plus Tauri eventually, but framework choice should be evaluated against JARVIS needs. | No direct reuse. | High | UI owning privileged actions, framework lock-in, premature frontend complexity. | Desktop HUD milestone. |

## Licensing And Dependency Findings

Personal Jarvis is Apache-2.0 on current main, with a NOTICE file and third-party component notices. The NOTICE says earlier releases through 1.6.0 used MIT and that from 2.0.0 onward the project uses Apache-2.0. If Project J.A.R.V.I.S. copies code, it must preserve required license and notice material, mark changes where appropriate, and review any bundled third-party assets or model license files.

Recommendation: prefer clean-room implementation guided by the reviewed architecture. Direct code copy should require an explicit license review and a short note in the implementing PR.

Major dependency areas to avoid inheriting prematurely:

- Audio and realtime stacks
- Local model runtimes and model downloads
- WebRTC or provider-specific realtime SDKs
- Desktop WebView and frontend build toolchains
- Telephony integrations
- MCP/plugin marketplace infrastructure
- External coding agent CLIs
- OS credential/keyring behavior on each platform
- GUI automation libraries

Project J.A.R.V.I.S. should keep the current dependency bar: add a major runtime only when a milestone needs it and the reason is documented.

## Security Findings

Personal Jarvis is strongest where it treats security as architecture: tool calls go through one executor, risk tiers are explicit, secrets come through a single access path, config mutation is audited, and untrusted observed content is data rather than instruction.

Project J.A.R.V.I.S. should take these lessons, but keep its own Sentinel model:

- No side-effecting tool may bypass Sentinel.
- UI and channel code must never directly perform privileged OS actions.
- Tool results, window titles, screen text, webpage text, email, files, and terminal output remain untrusted data.
- Chat/voice should not accept raw secret values as ordinary prompt content.
- Important actions need causal records, not after-the-fact model explanations.
- Computer control must follow the JARVIS integration hierarchy, with visual or coordinate control as a last fallback.

## What To Take

- Capability-oriented provider contracts.
- Honest live provider test statuses.
- Provider fallback rules based on capability and policy, not brand names.
- Deterministic router guards and exact regression tests for routing scope.
- One tool-execution coordinator for all tool calls.
- Risk policy tests that prove blacklist precedence and approval behavior.
- Atomic config mutation pipeline: validate, backup, write, reload, rollback, audit.
- Secret access through a broker-like interface.
- Worker state machine concepts: pending, running, reviewing, looping, approved, failed, cancelled, timed out.
- Worktree isolation and bounded recovery concepts for later coding workers.
- Evidence-grounded critic review.
- Headless startup as a permanent quality gate.
- ADRs, bug-class docs, and LLM context docs as review tools.

## What To Improve

- Project J.A.R.V.I.S. should make memory more structured and provenance-rich than Personal Jarvis's Markdown-first knowledge wiki.
- JARVIS should preserve the distinction between context metadata, structured context, rich captures, and model-analyzed vision.
- JARVIS Sentinel should reason over action context, causal provenance, user intent, surface, and reversibility, not just a static tier.
- Provider fallback should expose degraded-mode information to the user when relevant.
- Worker review should distinguish "artifact exists" from "task is verified complete."
- Future UI should be a satellite over Core, not a place where authority moves.

## What Must Remain JARVIS-Owned

- Assistant identity and behavioral source of truth
- Long-term memory, retrieval, answerability, and provenance
- Context engine and attention policy
- Sentinel authorization and audit model
- Event bus, causal identifiers, and proactivity policy
- Project/task awareness
- Tool Fabric ownership and integration hierarchy
- Device presence model
- Worker orchestration philosophy
- Desktop and voice satellite authority boundaries

## What To Avoid Inheriting

- A full fork or package import dependency on Personal Jarvis.
- Personal Jarvis memory as canonical JARVIS memory.
- Screenshot, vision, or pixel automation as the primary computer-control model.
- Large voice/realtime code before JARVIS has provider, credential, and channel contracts ready.
- Desktop UI framework decisions before a JARVIS HUD milestone exists.
- Provider-specific rules in core logic.
- A giant router tool surface.
- Config fields that no current code reads.
- Installer/runtime/download complexity before the core service stabilizes.

## Recommended Development Plan

1. PR #10 merged on 2026-09-11; the v0.7 merge prerequisite is satisfied.
2. PR #11 landed the documentation-only harvest, ADR, and Phase 1 specification at `7a7a8211f14c8dea34bdd568c9e30a2a4338daa0`.
3. PR #12 landed provider capability hardening at `c436d5c69f1919ca3eb2beb793ee275b05210f01`, completing [Provider Capabilities Phase 1](tasks/PROVIDER_CAPABILITIES_PHASE_1.md).
4. Define credential broker and configuration mutation boundaries in [Credential And Configuration Safety](tasks/CREDENTIAL_CONFIG_SAFETY.md) on a fresh branch from updated `main`. Runtime work follows when a task identifies a real consumer and resolves the specification's prerequisites.
5. Add event/provenance records before long-running workers.
6. Add specialist worker MVP with isolated worktrees and signed observations.
7. Add critic review as a verifier over worker output.
8. Add voice/channel foundations only after the above interfaces are stable.
9. Add installer/setup and desktop HUD later.
10. Add computer-control fallback only after safer API/native/MCP/DOM/UIA/accessibility layers exist.

## Current Task

Provider capability hardening is merged. Its `ProviderInfo` contains only `provider_id` and `capabilities`. The next task is the documentation-only [Credential And Configuration Safety](tasks/CREDENTIAL_CONFIG_SAFETY.md) specification; that document defines the scope and completion checks without embedding a duplicate implementation task here.

## Final Recommendation

Take the engineering discipline, not the product wholesale.

Personal Jarvis shows good answers to problems JARVIS will face: provider interchangeability, contract testing, safe self-modification, worker isolation, critic review, headless operation, and written architecture memory. Project J.A.R.V.I.S. should harvest those ideas in small, typed, tested milestones while preserving the JARVIS-owned systems that make this project distinct.
