# Credential And Configuration Safety

Status: proposed specification; documentation only, runtime implementation not started

Date: 2026-09-29

## Goal And Sequence

Define the next bounded step in the [Personal Jarvis harvest](../PERSONAL_JARVIS_HARVEST.md): keep credentials outside model context and make future configuration changes recoverable. [AGENTS.md](../../AGENTS.md) and [MASTER_ARCHITECTURE.md](../MASTER_ARCHITECTURE.md) remain authoritative.

[Provider Capability Contracts Phase 1](PROVIDER_CAPABILITIES_PHASE_1.md) landed in [PR #12](https://github.com/friezaforcecoder/project-jarvis/pull/12) at `c436d5c69f1919ca3eb2beb793ee275b05210f01`. This specification starts on `docs/credential-config-safety-spec`, a fresh branch from that updated `main`. Do not extend the merged provider branch.

This task completes the specification and current-code assessment. It does not authorize a credential backend, a configuration writer, or an unused broker interface. The next runtime task must identify a real consumer and settle the implementation decisions below before adding code.

## Current Implementation

| Boundary | Evidence | Consequence |
| --- | --- | --- |
| Configuration | [Settings and load_settings](../../src/jarvis_core/config/settings.py) validate an allowlisted environment mapping. | There is no configuration-file loader, `.env` loader, or persistent settings writer. |
| Application construction | [create_app](../../src/jarvis_core/api/app.py) builds settings, the provider registry, and chat service at construction. | Rewriting a file would not update the running application's provider or settings. |
| Provider | [OllamaProvider](../../src/jarvis_core/intelligence/providers/ollama.py) accepts an endpoint, model, and timeout, with no credential argument. | The only production adapter has no broker consumer. Do not add an unused API-key setting. |
| Authorization | [DefaultSentinelPolicy](../../src/jarvis_core/sentinel/policy.py) returns `ASK` for write-capable tools. | A future settings tool cannot treat `ASK` as permission to write. An authorized activation path must be designed with its consumer. |
| Provider metadata | [ProviderInfo](../../src/jarvis_core/intelligence/contracts.py) contains only `provider_id` and `capabilities`. | Credentials, configuration, and mutable health state must stay outside this descriptor. |

An explicitly supplied mapping replaces `os.environ` as the settings source; omitted keys use model defaults. Both the CLI and application construction load startup settings. Changing a `.env` file does not change the process environment read by `load_settings`. There is no live reload or provider-switch operation to wrap with a transaction today. Keep startup configuration behavior intact while this task is documentation only.

## Credential Boundary For The First Consumer

Core owns the secret-access boundary. An authenticated provider or integration must name the credential it needs through an explicit, allowlisted reference; vendor-specific authentication and request construction stay inside its adapter. Do not discover credentials by enumerating the environment or by accepting a model-supplied environment-variable name, file path, or keyring key.

The first runtime task must define these decisions together with that consumer:

- The public credential reference, its owner, and the exact trusted caller. Keep credential values out of `Settings` serialization, `ProviderInfo`, tool results, and model messages.
- The supported operating systems and a concrete credential-store backend. Document any dependency and its need; do not add a keyring package or platform bridge during this specification.
- Store precedence and headless behavior. Prefer the configured OS credential store, with an explicitly configured environment fallback. Distinguish an absent entry from access denied, a locked store, and an unavailable backend. Default to no fallback on store errors; any exception needs an explicit policy and tests.
- The typed result/error contract and adapter mapping. Missing or inaccessible required credentials must stop the affected operation before its network request, using a safe normalized error. Unrelated local startup and health must remain usable.
- The trusted setup path. Do not ask the user to provide credentials in chat, voice, tool arguments, or provider prompts. Secret retrieval must not become a general model-callable tool. This specification does not claim that the existing chat path detects or redacts arbitrary pasted secrets.

Credentials may be unwrapped only where the authorized adapter needs them for authentication. Avoid including them in object representations, exception text, logs, audit records, persistence, or general configuration backups. Normalize validation errors without exposing raw Pydantic input values or backend exceptions. A masked secret wrapper alone does not enforce this boundary; test the complete consuming path with synthetic sentinel values.

Credential creation, rotation, and deletion are separate side effects. Do not silently add them to the first read-only lookup implementation. Do not copy Personal Jarvis provider mappings or implementation source.

## Configuration Mutation Boundary

Core's configuration layer owns validation and activation. Provider adapters may validate their own configuration, but must not independently rewrite shared settings. Sentinel owns authorization for side-effecting tools; a UI, model, or API must not bypass it.

Before implementing mutation, a runtime task must name:

1. One concrete user operation and the exact allowlisted settings it changes. Do not start with an arbitrary settings editor.
2. The persistent source of truth, location and ownership rules, schema, and precedence relative to environment variables. Distinguish saved configuration from effective values overridden by the environment; do not report an overridden saved value as active. A file writer without a matching loader is not a working slice.
3. The authorized entry point and how approval is bound to the exact proposed change. Existing `ASK` responses do not supply an approval/resume mechanism.
4. Whether activation requires a restart or supports a live swap. A restart-required change remains pending activation until startup verifies it; saving alone must not be reported as an active change. Define effects on in-flight requests and prevent old settings from being paired with a newly constructed provider.
5. The concurrency boundary, including what happens if another process or an external editor changes configuration. A process-local lock must not be presented as cross-process protection.
6. Recovery and audit behavior, including a missing initial file, backup retention, access permissions, crashes, and rollback failure. Do not put secrets into configuration or its backups.

Once those decisions have a real consumer, implement and test this transaction shape:

```text
authorize the specific change
-> acquire the defined mutation lock and check the expected revision
-> validate the complete candidate before changing active state
-> preserve the previous recoverable state
-> write a staged candidate and atomically replace the persistent source
-> read back and validate through the actual loader
-> activate using the specified restart or live-swap policy
-> verify the defined readiness condition
-> record success, or restore the prior persistent and active state
-> record a safe failure/recovery outcome and release the lock
```

Atomic replacement alone does not provide rollback, concurrency control, or crash recovery. A failed restore must be visible as a recovery failure; never report success while disk and active state disagree. Audit records should identify the operation, authorization, revision, and normalized outcome without recording values, secret references that disclose account details, raw exceptions, or full settings dumps. The future task must specify what happens if audit recording itself fails.

## Required Evidence For Future Runtime Work

These are acceptance requirements for separately scoped implementations, not claims that this documentation task supplies the features or tests.

| Area | Required verification |
| --- | --- |
| Credential lookup | Deterministic configured-store precedence; missing entry versus locked/denied/unavailable store; explicit environment fallback; unknown references rejected without arbitrary lookup. |
| Credential containment | Synthetic secret sentinels absent from provider messages, API/tool responses, logs, representations, normalized errors, metadata, and persisted conversation/configuration records. Verify the adapter receives only its authorized credential. |
| Failure isolation | No consuming network call after credential failure; local startup and health remain available without external credentials or a graphical session. |
| Authorization | Denied, unresolved `ASK`, and stale approvals perform zero writes and no activation. The approved change cannot be replaced after authorization. |
| Configuration transaction | Validation and revision failures preserve the old state; fault injection at backup, write, replace, reload, activation, readiness, audit, and restore verifies the specified recovery outcome. |
| Concurrency and recovery | Concurrent requests cannot interleave changes; external edits and crash restart follow the declared policy; in-flight work cannot observe mixed configurations. |
| Compatibility | Configured-default chat behavior, capability selection, Ollama's `TEXT` capability, Sentinel routing, conversation atomicity, and active-window suppression regressions remain intact. |

Use injected stores, mocked transports, temporary configuration files, and fake credentials. Automated tests must not read a developer's actual credential store or environment secrets, contact paid providers, or require desktop interaction.

## Scope And Completion For This Specification

Deliver this task document, update the harvest's next-step pointer and Phase 1 merge status, and keep the README milestone index current. No changes to runtime code, tests, dependencies, storage, providers, workers, voice, UI, computer control, or canonical architecture are part of this specification.

Before completing this documentation PR:

- Confirm the branch starts from updated `main` after PR #12, and its diff is documentation only.
- Review the current-code claims and the distinction between completed behavior and future requirements.
- Check relative documentation links and `git diff --check`.
- Run the practical baseline: `python -m pytest`, `python -m compileall src tests`, and documented `python -m jarvis_core` startup with `/v1/health`, isolated local state, and Ollama unavailable.
- Record the actual checks in the PR, including any failure. Passing baseline checks does not mark credential or configuration mutation features implemented.

After this specification lands, choose one real credential consumer or one authorized configuration operation and turn its prerequisites into a focused runtime task. Start that implementation on another fresh branch from updated `main`; do not turn this documentation branch into a broad provider, configuration, or security framework.
