# ADR 0001: Personal Jarvis Selective Harvest

Status: proposed; documentation may be reviewed independently

Date: 2026-09-11

Implementation gate: PR #10 merged into `main` on 2026-09-11 at `b3a1a3e26e844d57105e5609509b2930ae97e1f1`. Provider Phase 1 starts on a fresh branch after the documentation in PR #11 lands.

## Context

[AGENTS.md](../../AGENTS.md) and [MASTER_ARCHITECTURE.md](../MASTER_ARCHITECTURE.md) remain the canonical instructions and architecture. This decision records a narrow application of those rules; it does not establish a competing architecture or authorize later milestones.

The [Personal Jarvis architecture harvest](../PERSONAL_JARVIS_HARVEST.md) recommends learning from a mature reference system while retaining Project J.A.R.V.I.S. ownership and module boundaries. The existing intelligence layer already has a provider protocol, capability labels, a registry, normalized errors, and an Ollama adapter. Capability selection can be strengthened within those interfaces.

PR #10 delivered active-window context v0.7 and has merged. PR #11 remains a separate documentation-only change. Provider implementation must start on a fresh branch from updated `main` after PR #11 lands.

## Decision

Adopt Strategy A: Selective Harvest. Adapt small engineering patterns into JARVIS-owned, typed, tested contracts. Do not fork Personal Jarvis or add it as a package dependency.

JARVIS Core continues to own identity, memory, context and attention, Sentinel, permissions, tools, tasks, events, causal provenance, orchestration, and device presence. Provider adapters remain replaceable. Interfaces and satellites do not acquire Core authority.

The first implementation milestone is limited to provider capability metadata and deterministic capability lookup. Its detailed requirements are in [Provider Capabilities Phase 1](../tasks/PROVIDER_CAPABILITIES_PHASE_1.md):

- Keep the existing `IntelligenceProvider` protocol and configured-default lookup compatible.
- Register an immutable snapshot of each provider's public identifier and advertised capabilities.
- Resolve explicit capability requests by matching all required capabilities, with registration order as the deterministic tie-breaker.
- Return normalized errors for missing identifiers and capability misses.
- Keep Ollama's advertised capability limited to its implemented non-streaming text behavior.
- Preserve chat routing, Tool Fabric execution, Sentinel authorization, and existing error behavior.

Provider identifiers identify adapters; they do not decide capabilities. Provider metadata contains an allowlisted contract, with no settings payload, credentials, endpoint URLs, raw environment values, or credential-file paths.

The broader harvest suggests health, locality, and fallback-family fields. Defer those fields until an active milestone consumes them and defines their semantics. This phase does not probe provider health, infer readiness from registration, or introduce fallback execution. Capability advertisement describes the adapter interface, not a successful live provider test.

Documentation should capture decisions and exact regression requirements in focused ADRs and task documents. Additional architecture registers are useful only when they have concrete content and ownership; this decision does not require empty anti-pattern, bug-class, or context documents.

## Alternatives Considered

### Adopt Personal Jarvis wholesale

Rejected. A fork or broad package import would inherit product assumptions, dependencies, and ownership boundaries beyond the current milestone.

### Copy the reference provider implementation

Rejected for this milestone. Native changes to the existing JARVIS contracts are sufficient and avoid importing vendor logic or unnecessary infrastructure.

### Implement the full suggested metadata and fallback model now

Deferred. Health supervision, live provider testing, locality policy, fallback families, and configuration mutation need their own active requirements and consumers. Adding unused fields would imply behavior this phase does not implement.

## Consequences

The registry gains an explicit capability query without changing the configured chat provider or tool-execution path. Immutable registration snapshots prevent later mutation of an adapter's capability attributes from silently changing registry decisions. Re-registration is the explicit way to refresh that snapshot and retains existing provider-replacement behavior.

Registration order is a small, testable selection policy. It is not a ranking, cost, health, privacy, or fallback policy. Future requirements may extend selection through provider-neutral policy contracts in a separately scoped milestone.

No runtime dependencies, providers, storage schemas, migrations, services, workers, voice, UI, plugins, MCP, installers, or computer-control features are introduced by this documentation change. Runtime and test source files are unchanged.

No Personal Jarvis implementation source code is copied in this documentation change. The future Phase 1 implementation must be written against JARVIS contracts. Any later direct source reuse requires a specific license and notice review and a compliance note in the implementing PR, as described in the harvest document.

## Validation And Follow-up

The documentation review should check links, canonical ownership, the satisfied PR #10 prerequisite, the separate PR #11/Phase 1 sequence, and consistency between this ADR and the Phase 1 task. Passing documentation checks does not satisfy the future implementation's acceptance criteria.

After PR #11 lands, implement only the Phase 1 task on a fresh branch from updated `main`. Run its focused tests, the complete test suite, compilation checks, whitespace checks, and documented startup verification. Record the actual results and any remaining limitations in the implementing PR.
