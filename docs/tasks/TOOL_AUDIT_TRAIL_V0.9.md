# Project J.A.R.V.I.S. Tool Execution Audit Trail v0.9

Status: implemented on feature branch; pending review and CI

## Objective

Add durable, privacy-safe execution evidence for every request that enters the existing Tool Fabric coordinator.

This milestone strengthens the established Tool Fabric and Sentinel path. It does not add a second executor, general model-selected tools, application control, background workers, or a broader event system.

## Canonical Boundaries

- `AGENTS.md` and `docs/MASTER_ARCHITECTURE.md` remain authoritative.
- `ToolExecutionCoordinator` remains the only runtime tool execution choke point.
- Sentinel remains the authorization authority.
- Direct API and deterministic chat-routed tool requests use the same coordinator and audit path.
- SQLite remains the only durable store.
- Audit persistence must never receive tool payloads or raw exception text.

## Durable Record

Each execution attempt owns one immutable identity and one lifecycle row:

```text
audit_id
correlation_id
tool_name
side_effect_level
execution_boundary
sentinel_decision
outcome
error_code
started_at
completed_at
```

`audit_id` is a generated UUID distinct from the request correlation ID. Timestamps are timezone-aware UTC values. Descriptor and Sentinel fields remain null until that trusted information is known.

The normalized outcomes are:

- `started`
- `tool_not_found`
- `invalid_arguments`
- `approval_required`
- `denied`
- `authorization_failed`
- `succeeded`
- `tool_failed`
- `internal_failure`

The safe `ToolErrorCode` is stored for failed outcomes. Successful records have no error code.

## Privacy Allowlist

Audit persistence may contain only the ten fields listed above.

It must not contain:

- Tool arguments or results
- User or assistant messages
- Provider or system prompts
- Sentinel reason text
- Window titles or application names
- Native context payloads
- Usernames, hostnames, paths, or file contents
- Credentials, tokens, or secret references
- Raw exceptions or database error text
- Arbitrary metadata or serialized objects

Structured runtime logs keep their existing safe metadata behavior and do not become an alternate payload store.

## Lifecycle

Before registry lookup, argument validation, Sentinel authorization, or tool execution:

1. Resolve or generate the request correlation ID.
2. Generate a distinct audit UUID.
3. Insert a durable `started` row.

After that insert succeeds, the coordinator follows its existing order:

```text
registry lookup
-> typed argument validation
-> Sentinel authorization
-> tool execution
-> terminal audit transition
-> caller response
```

Each row can transition from `started` to a terminal outcome exactly once. The transition is atomic and may add trusted descriptor metadata and the Sentinel action. Completed rows cannot be rewritten.

## Failure Semantics

- If the initial audit insert fails, return a safe `tool_internal_error`. Do not call Sentinel or the tool.
- If a required terminal transition fails, return a safe `tool_internal_error` with message `Tool audit persistence failed.`
- If a terminal write fails after the tool ran, never return success. The atomic failure leaves the row as `started`, making the incomplete evidence visible.
- Normalize repository failures to `ToolAuditPersistenceError`; do not expose SQLite text or paths.
- Unexpected coordinator failures become `internal_failure` plus `tool_internal_error` when the terminal record can be written.
- Unknown correlation IDs are not errors for the read endpoint; they return an empty list.

## Read API

Expose one local read-only endpoint:

```text
GET /v1/audit/tool-executions/{correlation_id}
```

The response contains the requested correlation ID and its typed records ordered by `started_at`, then `audit_id`. The endpoint exposes no list-all, search, mutation, deletion, retention, export, or payload retrieval operations.

Audit read failures return HTTP 500 with only:

```json
{
  "status": "error",
  "error": {
    "code": "tool_audit_persistence_failed",
    "message": "Tool audit persistence failed.",
    "correlation_id": "requested-correlation"
  }
}
```

## Storage

Add one versioned SQLite migration for `tool_execution_audits` and one index supporting deterministic correlation lookups.

Repository requirements:

- Explicit transactions for create and completion
- No replace or upsert behavior
- No update of already completed rows
- No identity-field mutation
- Read-only lookup connections
- Safe normalized persistence failures

## Tests

Automated coverage must verify:

- Frozen, extra-forbidden, timezone-aware contracts
- Exact database columns and migration registration
- Deterministic lookup order
- Irreversible completion
- Audit creation before Sentinel and tool execution
- Success and all normalized failure outcomes
- Initial-write fail-closed behavior
- Completion failure after tool execution never returns success
- Direct API and chat-routed tool integration
- Missing-correlation behavior
- Safe read failure responses
- Synthetic arguments, results, reasons, and raw failures do not enter storage or the read response
- Existing Tool Fabric, Sentinel, context, chat, and persistence behavior remains green

## Documentation And Version

- Add README usage, response, privacy, and failure notes.
- Bump package, runtime, health, and test expectations consistently to `0.9.0`.
- Add no dependency.

## Out Of Scope

- Audit retention, pruning, export, or deletion
- Hash chains, signing, tamper-evident ledgers, or remote sinks
- User approval workflows beyond the existing Sentinel result
- Persisting arguments, results, prompts, or context summaries
- General event-bus expansion
- New providers, workers, voice, UI, or computer-control capability
- Changes to deterministic chat routing

## Acceptance Criteria

The milestone is complete when:

1. Every coordinator request creates durable initial evidence before authorization or execution.
2. Every normal terminal path records one normalized final outcome.
3. Audit persistence failure cannot produce an unaudited success.
4. Stored and returned records contain only the documented allowlist.
5. Direct and chat-routed executions are queryable by correlation ID.
6. The complete test suite, compilation, whitespace checks, startup, and health verification pass at version `0.9.0`.

## Local Validation Record

Validated on Windows on 2026-09-30:

- `395 passed`, with one existing Starlette/httpx deprecation warning
- `python -m compileall -q src tests`
- `git diff --check`
- README and task relative-link verification
- Documented `python -m jarvis_core` startup with isolated SQLite state
- `GET /v1/health` returned service `jarvis-core`, status `ok`, and version `0.9.0`
- Direct `system.runtime_info` execution succeeded through Sentinel
- `GET /v1/audit/tool-executions/v09-startup-smoke` returned the matching completed allowlisted record

Ubuntu and Windows GitHub CI remain required before merge.
