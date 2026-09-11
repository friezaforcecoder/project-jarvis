# Selective Harvest Phase 1: Provider Capability Contracts

Status: proposed; PR #10 merge prerequisite satisfied, implementation pending PR #11 landing

Date: 2026-09-11

Repository: `friezaforcecoder/project-jarvis`

## Goal

Allow JARVIS to resolve registered intelligence providers by explicitly requested capabilities while preserving the existing configured-default chat behavior. Use native JARVIS contracts and deterministic tests; do not add runtime providers or execution features.

This task concretizes the first implementation step in the [Personal Jarvis harvest](../PERSONAL_JARVIS_HARVEST.md) and [ADR 0001](../adr/0001-personal-jarvis-selective-harvest.md). [AGENTS.md](../../AGENTS.md) and [MASTER_ARCHITECTURE.md](../MASTER_ARCHITECTURE.md) remain canonical.

## Sequencing And Branch

PR #10 merged active-window context v0.7 on 2026-09-11 at `b3a1a3e26e844d57105e5609509b2930ae97e1f1`. Its merge prerequisite is satisfied. The harvest documentation and this task remain documentation-only in PR #11 and do not expand v0.7.

Before runtime implementation:

1. Verify that PR #11, including this specification, has landed in `main`; PR #10 is already merged.
2. Update the local view of `origin/main` and inspect the resulting provider contracts and tests.
3. Create a fresh, separate implementation branch from that updated `main`.

Keep PR #11 documentation-only. After it lands, implement this task on the fresh branch, not on the harvest or active-window branch. A passing PR review does not mean the PR has merged.

## Required Reading

- `AGENTS.md`.
- `docs/MASTER_ARCHITECTURE.md`, especially Core Principles, Intelligence Provider Layer, Tool Fabric, Sentinel, and Reliability, Lifecycle, And Health.
- `docs/PERSONAL_JARVIS_HARVEST.md` and ADR 0001.
- Existing task documents under `docs/tasks/`, especially intelligence v0.2, Tool Fabric and Sentinel v0.4, chat tool invocation v0.6, and the merged active-window v0.7 task.
- Current intelligence contracts, registry, provider adapter, chat router, normalized errors, API error mapping, and provider/chat/tool/Sentinel tests.

## Scope

Implement only capability labels, immutable provider metadata snapshots, explicit capability lookup, and focused regression tests.

Keep these existing behaviors:

- `IntelligenceProvider` exposes `provider_id`, `capabilities`, and `generate`.
- Providers that implement that existing protocol need no new required property or constructor argument.
- `get(provider_id)` and `resolve_default(provider_id)` return the registered provider instance for that exact identifier.
- Registering a provider under an existing identifier replaces that provider.
- Chat uses the configured default provider. A capability query does not silently replace the configured default or trigger fallback.
- Tool execution continues through `ToolExecutionCoordinator` and Sentinel.

Do not add vendors, SDKs, model execution modes, voice, workers, plugins, MCP, UI, installers, computer control, configuration mutation, credential storage, provider-health probes, fallback execution, or new runtime dependencies.

No persistence schema changes, database tables, migrations, scheduler state, worker state, vector stores, graph stores, or credential persistence are allowed.

## Capability Contract

Extend the existing provider-neutral `ProviderCapability` enum with these labels:

| Member | Value | Meaning |
| --- | --- | --- |
| `TEXT` | `text` | The adapter supports the existing text generation contract. |
| `TOOL_USE` | `tool_use` | Reserved label for a future implemented provider tool-use interface. |
| `VISION` | `vision` | Reserved label for a future implemented visual-input interface. |
| `REALTIME` | `realtime` | Reserved label for a future implemented realtime interface. |
| `STREAMING` | `streaming` | Reserved label for a future implemented streaming interface. |

Adding labels does not implement those interfaces. Test doubles may advertise multiple labels to verify registry behavior. Production adapters must advertise only capabilities their JARVIS adapter actually implements.

Ollama continues to advertise only `frozenset({ProviderCapability.TEXT})`. Core's deterministic use of tools does not make Ollama a `TOOL_USE` adapter. The Ollama request remains non-streaming, and model or vendor feature claims do not expand the adapter's advertised capabilities.

## Immutable Provider Metadata

Add a Pydantic `ProviderInfo` contract containing only:

- `provider_id: str`, a non-empty, public, stable adapter identifier.
- `capabilities: frozenset[ProviderCapability]`.

Use `ConfigDict(frozen=True, extra="forbid")`. The capability collection and the model's fields must be read-only through the normal public interface. Do not add a free-form metadata dictionary.

The registry constructs an allowlisted `ProviderInfo` snapshot from the existing protocol properties at registration. It must not serialize the provider object, inspect its `__dict__`, or copy its settings. The registry uses that stored snapshot for capability decisions and exposes it through a small read-only accessor such as `info(provider_id)`.

Changing or replacing the provider's capability attribute after registration must not alter the stored capability snapshot. Re-registering explicitly replaces both the provider and its metadata snapshot. Returning a descriptor must not provide mutable access to registry state.

Do not add `health`, `local`, or `fallback_family` fields in this phase. No current consumer or live health check needs them. Capability metadata must not imply that registration verified provider readiness.

## Deterministic Resolution

Add an explicit capability lookup, such as `resolve(required_capabilities: frozenset[ProviderCapability]) -> IntelligenceProvider`.

Resolution must:

1. Compare the requested set against each stored capability snapshot using an all-required subset check.
2. Return the first matching provider in registration order.
3. Leave registration order unchanged when replacing a provider under an existing identifier.
4. Treat an empty requirement set as no capability restriction: return the first registered provider, or the normalized capability-miss error if the registry is empty.
5. Perform no provider calls, network calls, discovery, health checks, retries, or tool execution.

Provider identifiers must never determine support for a capability. Do not inspect vendor names, model names, endpoint URLs, or settings to infer capabilities. Registration order is the only tie-breaker in this phase; cost, health, locality, and fallback policy remain deferred.

`get()` and `resolve_default()` keep their current explicit-ID semantics. They do not impose new capability requirements or select a different provider when the configured identifier is absent. No chat-router change is required by this design.

## Normalized Errors And Safe Observability

Missing explicit IDs, including metadata lookup for an unknown ID, continue to raise `ProviderError` with `ProviderErrorCode.UNKNOWN_PROVIDER` and the existing safe message and identifier behavior.

When capability lookup has no match, raise `ProviderError` with the existing `ProviderErrorCode.UNAVAILABLE` and a static safe message, such as `No registered intelligence provider satisfies the required capabilities.` Set no guessed provider ID or model. The empty registry and partial-capability mismatch use the same normalized failure.

Reuse the existing code rather than adding an unhandled enum member to the chat API's exhaustive provider-error status map. Existing unknown-provider and adapter-failure HTTP statuses must remain unchanged.

Keep metadata, errors, and any structured logs free of credentials, API keys, endpoint URLs, credential-file paths, raw environment values, provider settings, raw exceptions, prompts, and responses. Adapter IDs must be public labels and must not be populated from credential values. Metadata is an allowlisted descriptor, not a credential-redaction facility.

If resolution logging is added, restrict it to safe event names, normalized capability labels, counts, public registered identifiers, and normalized error codes. Do not dump provider objects or the metadata input. Preserve existing safe chat lifecycle logging.

## Expected Files

- Modify `src/jarvis_core/intelligence/contracts.py`.
- Modify `src/jarvis_core/intelligence/registry.py`.
- Export the new contract from `src/jarvis_core/intelligence/__init__.py` if consistent with the module's existing public exports.
- Modify `src/jarvis_core/intelligence/providers/ollama.py` only if needed to preserve accurate metadata; its current `TEXT` capability already satisfies this task.
- Update `tests/test_intelligence_registry.py`.
- Add `tests/test_intelligence_provider_capabilities.py`.
- Update focused documentation to describe the implemented interface and actual validation results.

Do not change Sentinel, Tool Fabric, chat-tool routing, persistence, runtime dependencies, or package versions as incidental work. Change the chat router only if inspection of updated `main` reveals a concrete compatibility requirement, and explain that need in the implementing PR.

## Required Tests

Use deterministic test providers and mocked transports. Tests must not require Ollama, credentials, network services, audio, graphical sessions, or native computer control.

### Metadata And Adapter Behavior

1. A provider advertises multiple capability labels, and the registered snapshot preserves all of them.
2. `ProviderInfo` rejects unknown fields and invalid capability values, and rejects assignment to its fields.
3. Input capability collections are normalized into a `frozenset`; a caller cannot mutate the stored collection through an exposed descriptor.
4. Reassigning an adapter's capabilities after registration leaves the stored snapshot and selection behavior unchanged until re-registration.
5. Re-registration refreshes both the provider instance and capability snapshot.
6. Ollama advertises exactly `TEXT`, without a network call or an implicit live-health claim.
7. Metadata serialization contains only the public identifier and capability labels. Put unique sentinel values in fake provider secret/configuration attributes and in a mocked Ollama endpoint/model configuration; none may appear in the descriptor. Do not use real secrets.
8. Unknown metadata fields cannot be used to attach an API key, raw environment value, endpoint URL, or credential-file path.

### Registry Selection And Compatibility

1. One required capability resolves a matching provider.
2. Multiple required capabilities resolve only a provider that supports all of them.
3. Partial matches and absent capabilities raise the normalized `UNAVAILABLE` error, including on an empty registry.
4. An empty required set returns the first registered provider when one exists.
5. Multiple matching providers resolve in registration order, consistently across repeated calls.
6. Replacement under an existing identifier preserves its selection position.
7. Provider-specific IDs do not drive checks: use misleading IDs whose declared capabilities differ from what their names suggest, and verify selection follows the declarations.
8. Existing `get()` and `resolve_default()` return the same registered instance and preserve existing replacement behavior.
9. An unknown explicit ID retains `UNKNOWN_PROVIDER`; it does not fall back to a provider that happens to have `TEXT`.
10. Capability lookup never calls `generate()` or performs network/tool work.
11. Capability-miss errors contain the static safe message and no provider settings, secrets, model guesses, or raw exception text. If logs are added, test their allowlist and sentinel non-disclosure too.

### Existing Behavior

Run existing provider, chat, conversation, tool, Sentinel, and merged active-window tests unchanged. Confirm configured-default chat routing, normalized HTTP errors, non-streaming Ollama payloads, tool authorization, and conversation atomicity remain intact.

## Acceptance And Completion Evidence

The implementation is complete only when:

- Every required behavior and focused regression above is verified.
- `python -m pytest` passes for the complete suite.
- `python -m compileall src tests` passes.
- `git diff --check` passes.
- Core starts using the documented README command and its health endpoint responds, without requiring Ollama to be available at startup.
- There are no runtime dependency or persistence changes.
- Core capability checks contain no vendor-specific branches.
- Existing providers still satisfy `IntelligenceProvider` and configured-default resolution remains compatible.
- No Personal Jarvis source code was copied. Any proposed direct reuse must first receive a specific license/notice review and an explicit compliance note in the implementing PR.
- Canonical architecture and ownership remain unchanged.

Report the implementation branch, commit, PR if created, files changed, exact final public interface, test/check results, startup verification, and any limitations. State explicitly that no new providers, dependencies, storage, workers, voice, UI, or computer-control features were added.

Documentation-only review does not fulfill these runtime acceptance criteria. Record Phase 1 as pending until its separate implementation after PR #11 lands and its verification are complete.
