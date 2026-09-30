# ADR 0001: Personal Jarvis Selective Harvest

Status: accepted; Provider Capability Contracts Phase 1 implemented and merged

Date: 2026-09-11

Implementation record: PR #10 merged active-window context v0.7 at `b3a1a3e26e844d57105e5609509b2930ae97e1f1`. PR #11 landed this documentation at `7a7a8211f14c8dea34bdd568c9e30a2a4338daa0`. [PR #12](https://github.com/friezaforcecoder/project-jarvis/pull/12) implemented Provider Capability Contracts Phase 1 on a fresh branch from that mainline and merged at `c436d5c69f1919ca3eb2beb793ee275b05210f01`.

## Context

[AGENTS.md](../../AGENTS.md) and [MASTER_ARCHITECTURE.md](../MASTER_ARCHITECTURE.md) remain the canonical instructions and architecture. This decision records a narrow application of those rules; it does not establish a competing architecture or authorize later milestones.

The [Personal Jarvis architecture harvest](../PERSONAL_JARVIS_HARVEST.md) recommends learning from a mature reference system while retaining Project J.A.R.V.I.S. ownership and module boundaries. The intelligence layer has a provider protocol, capability labels, a registry, normalized errors, and an Ollama adapter. Phase 1 strengthened capability selection within those interfaces.

PR #10, the documentation-only PR #11, and the separate Phase 1 implementation in PR #12 have all merged. Follow-up work is defined by the documentation-only [Credential And Configuration Safety](../tasks/CREDENTIAL_CONFIG_SAFETY.md) specification on a fresh branch from updated `main`.

## Decision

Adopt Strategy A: Selective Harvest. Adapt small engineering patterns into JARVIS-owned, typed, tested contracts. Do not fork Personal Jarvis or add it as a package dependency.

JARVIS Core continues to own identity, memory, context and attention, Sentinel, permissions, tools, tasks, events, causal provenance, orchestration, and device presence. Provider adapters remain replaceable. Interfaces and satellites do not acquire Core authority.

The completed first implementation milestone is limited to provider capability metadata and deterministic capability lookup. Its requirements and implementation record are in [Provider Capabilities Phase 1](../tasks/PROVIDER_CAPABILITIES_PHASE_1.md):

- Keep the existing `IntelligenceProvider` protocol and configured-default lookup compatible.
- Register an immutable snapshot of each provider's public identifier and advertised capabilities.
- Resolve explicit capability requests by matching all required capabilities, with registration order as the deterministic tie-breaker.
- Return normalized errors for missing identifiers and capability misses.
- Keep Ollama's advertised capability limited to its implemented non-streaming text behavior.
- Preserve chat routing, Tool Fabric execution, Sentinel authorization, and existing error behavior.

Provider identifiers identify adapters; they do not decide capabilities. Provider metadata contains an allowlisted contract, with no settings payload, credentials, endpoint URLs, raw environment values, or credential-file paths.

Defer health, locality, and fallback-family fields until an active milestone consumes them and defines their semantics. This phase does not probe provider health, infer readiness from registration, or introduce fallback execution. Capability advertisement describes the adapter interface, not a successful live provider test.

Documentation should capture decisions and exact regression requirements in focused ADRs and task documents. Additional architecture registers are useful only when they have concrete content and ownership; this decision does not require empty anti-pattern, bug-class, or context documents.

## Alternatives Considered

### Adopt Personal Jarvis wholesale

Rejected. A fork or broad package import would inherit product assumptions, dependencies, and ownership boundaries beyond the current milestone.

### Copy the reference provider implementation

Rejected for this milestone. Native changes to the existing JARVIS contracts are sufficient and avoid importing vendor logic or unnecessary infrastructure.

### Implement the full suggested metadata and fallback model now

Deferred. Health supervision, live provider testing, locality policy, fallback families, and configuration mutation need their own active requirements and consumers. Adding unused fields would imply behavior this phase does not implement.

## Consequences

The registry now provides an explicit capability query without changing the configured chat provider or tool-execution path. Immutable registration snapshots prevent later mutation of an adapter's capability attributes from silently changing registry decisions. Re-registration is the explicit way to refresh that snapshot and retains existing provider-replacement behavior.

Registration order is a small, testable selection policy. It is not a ranking, cost, health, privacy, or fallback policy. Future requirements may extend selection through provider-neutral policy contracts in a separately scoped milestone.

No runtime dependencies, providers, storage schemas, migrations, services, workers, voice, UI, plugins, MCP, installers, or computer-control features are introduced by this documentation change. Runtime and test source files are unchanged.

No Personal Jarvis implementation source code was copied in the documentation change or Phase 1 implementation. Phase 1 was implemented against native JARVIS contracts. Any later direct source reuse requires a specific license and notice review and a compliance note in the implementing PR, as described in the harvest document.

## Validation And Follow-up

Phase 1 passed its focused tests, the complete 285-test suite, compilation, whitespace checks, documented startup and health verification, and CI on Ubuntu and Windows before merging in PR #12. Its [implementation record](../tasks/PROVIDER_CAPABILITIES_PHASE_1.md) preserves the results and limitations.

The current follow-up is [Credential And Configuration Safety](../tasks/CREDENTIAL_CONFIG_SAFETY.md), a documentation-only specification. Review its links, current-code claims, ownership boundaries, and prerequisites before defining a runtime task. Passing documentation checks does not implement credential lookup or configuration mutation. Any later runtime implementation starts on another fresh branch from updated `main`, using its own focused task and acceptance criteria.
