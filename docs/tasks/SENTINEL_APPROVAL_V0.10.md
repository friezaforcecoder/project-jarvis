# Project J.A.R.V.I.S. Sentinel Approval Receipts v0.10

Status: implementation complete on `qwen/sentinel-approval-v0.10`; pending draft PR CI and Build Head approval

## Objective

Add the smallest safe approval foundation for direct Tool Fabric requests whose trusted descriptor causes Sentinel to return `ASK`.

The milestone makes a short-lived, one-time approval receipt usable by a trusted local direct-API client. It does not add a production write tool, configuration mutation, credentials, chat approval, UI, computer control, or autonomous behavior.

`AGENTS.md` and `docs/MASTER_ARCHITECTURE.md` remain canonical. `ToolExecutionCoordinator` remains the only tool execution choke point, and Sentinel remains the policy authority.

## Security Boundary

- Sentinel must run on every execution attempt before approval is considered.
- `DENY` can never be overridden by an approval receipt.
- `ALLOW` keeps the existing read-only path and does not consume approval state.
- Only the direct tool API may request or present an approval receipt.
- Chat and provider paths may receive the existing safe `approval_required` failure, but they must never create, receive, persist, log, or grant an approval ID.
- Granting a receipt never executes a tool. A later direct execution request must present it to the coordinator.
- Approval IDs are random UUID capabilities. They must not enter logs, tool audit rows, conversation persistence, provider messages, or exception text.
- The local approval endpoint is a bootstrap trusted-client boundary, not multi-user authentication. Keep it loopback-local under the existing service deployment and document that limitation.

## Request Binding

Bind each receipt to the exact trusted execution request with HMAC-SHA256.

The HMAC input must be a deterministic canonical serialization containing only:

- A domain-separation/version label
- The request correlation ID
- The trusted registered tool name
- The trusted side-effect level
- The trusted execution boundary
- The validated argument model serialized in deterministic JSON form

Use a random 32-byte process-local key created during application construction and injected into the approval binding service. Do not persist or log the key.

Do not use an unkeyed argument hash. Low-entropy arguments must not be recoverable through offline guessing from the database.

Canonical serialization must use structured JSON, sorted keys, stable separators, and JSON-compatible Pydantic output. Reject non-finite or otherwise non-canonical values safely.

Because the HMAC key is process-local, every outstanding receipt must fail closed after restart. Restart invalidation is intentional for v0.10.

## Approval Contract

Create a frozen, extra-forbidden typed approval record containing only:

```text
approval_id
request_binding
status
created_at
expires_at
approved_at
consumed_at
```

Supported statuses:

- `pending`
- `approved`
- `consumed`

All timestamps are timezone-aware UTC. `approval_id` is a UUID. `request_binding` is exactly one lowercase 64-character hexadecimal HMAC digest.

Lifecycle invariants:

- New records are pending, unapproved, and unconsumed.
- Grant atomically changes `pending` to `approved` once, before expiry.
- Consume atomically changes `approved` to `consumed` once, before expiry and only for a constant-time matching request binding.
- Consumed, expired, mismatched, or unknown receipts cannot authorize execution.
- Expiry is derived from `expires_at`; no cleanup or background worker is added.

Use a fixed five-minute lifetime in this milestone. Do not add mutable configuration for the timeout yet.

## Direct API Flow

Keep `POST /v1/tools/execute` as the only execution endpoint. Add an optional, extra-forbidden `approval_id` to the typed tool request.

The direct route must call the coordinator through an explicit trusted direct-approval mode. Chat calls the same coordinator with approval disabled.

For a direct request when Sentinel returns `ASK`:

1. With no `approval_id`, create a pending receipt and return the existing HTTP 409 approval-required error plus a separate typed approval challenge containing only `approval_id` and `expires_at`.
2. With a pending receipt, return approval required without creating another receipt.
3. With an expired receipt, return a safe approval-expired error.
4. With an unknown, consumed, mismatched, or restart-invalidated receipt, return one indistinguishable safe approval-invalid error.
5. With a granted, unexpired, matching receipt, atomically consume it before tool execution, then execute through the existing coordinator path.

Add one grant endpoint:

```text
POST /v1/tool-approvals/{approval_id}/grant
```

It accepts no request body. It returns only `approval_id`, `status`, and `expires_at`. It never receives tool names or arguments and never executes a tool.

Use safe normalized 404/409/410/500 responses for unknown, unavailable, expired, and persistence-failure states. Do not reveal request bindings or database details.

Do not add list, search, revoke, delete, refresh, bulk-grant, or grant-by-correlation endpoints.

## Persistence

Add one recorded SQLite migration and one focused repository. The table must contain exactly the seven approval contract columns and appropriate CHECK constraints.

Repository requirements:

- Explicit transactions for create, grant, and consume
- No replace or upsert behavior
- No identity or binding mutation
- Atomic compare-and-transition updates for grant and consume
- Exactly one concurrent consumer can succeed
- Safe normalized persistence errors with no SQLite text or paths
- Deterministic read by approval ID only

Approval persistence must never receive raw arguments, results, prompts, messages, reasons, paths, native context, credentials, secrets, or raw exceptions.

## Tool Audit Integration

Keep the v0.9 ten-column tool audit allowlist unchanged. Never add approval IDs or request bindings to tool audit persistence.

Add only the normalized terminal outcomes and safe tool error codes needed to distinguish:

- Approval expired
- Approval invalid

The first attempt without a receipt remains `approval_required`. A later successful execution has a separate audit row with Sentinel decision `ask` and normal `succeeded` or `tool_failed` outcome.

If approval persistence fails, no tool may execute. Complete the current audit row as `internal_failure` when possible and return a safe internal error. Existing v0.9 audit-persistence failure precedence remains unchanged.

Consume the receipt before calling the tool. If the process crashes after consumption, the receipt remains spent and the audit row may remain `started`; this is the required fail-closed result. If the tool runs and final audit persistence fails, preserve the existing v0.9 behavior and never return success.

## Tests

Use fake write-capable tools only in tests. Add no production write or dangerous tool.

Automated coverage must verify:

- Frozen, extra-forbidden approval contracts and lifecycle validation
- Exact migration registration and exact table columns
- HMAC determinism within one process, domain separation, changed-field mismatch, and different-process-key mismatch
- No unkeyed raw or serialized arguments in persistence
- Direct `ASK` creates one pending challenge after registry lookup, validation, and Sentinel
- Chat `ASK` creates no challenge and exposes no approval capability
- Grant lifecycle, expiry, duplicate grant, unknown ID, and safe persistence failures
- Valid receipt executes once and is consumed before tool execution
- Replay, mismatch, expiry, pending state, process restart, and concurrent consumption all fail closed
- `DENY` cannot be overridden and dangerous tools remain denied
- Existing `ALLOW` tools execute unchanged and do not touch approval persistence
- Initial/final tool-audit failure behavior remains correct
- Approval IDs, bindings, arguments, and synthetic secrets are absent from logs, audit rows, conversations, provider messages, and normalized errors
- Direct API response shapes and safe status codes
- Existing Tool Fabric, Sentinel, audit, chat, context, persistence, and provider tests remain green

## Documentation And Version

- Update README with the direct two-step approval flow, privacy boundary, restart invalidation, and trusted-local-client limitation.
- Bump package, runtime, health, and test expectations consistently to `0.10.0`.
- Record actual validation results in this task document after implementation.
- Add no dependency.

## Out Of Scope

- Production write or dangerous tools
- Chat-, model-, provider-, prompt-, or voice-granted approval
- Authentication, multi-user identity, remote approval, or mobile approval
- Approval UI or notifications
- Configuration mutation or credential storage
- Revocation, extension, renewal, cleanup, retention, export, or deletion
- Persisting raw arguments or reversible request summaries
- Event-bus expansion, workers, scheduling, or autonomous retries
- Browser, desktop, shell, file, application, or computer-control actions

## Validation

Run:

- Focused approval, Tool Fabric, audit, chat, and persistence tests
- Complete pytest suite
- `python -m compileall -q src tests`
- `git diff --check`
- README/task relative-link checks
- Documented startup and `GET /v1/health` at `0.10.0`
- Direct execution smoke test for an existing read-only tool, proving behavior remains unchanged

Open a draft PR and report the branch, commit SHA, changed files, exact contracts, test totals, startup result, CI status, known limitations, and confirmation that no production side-effecting capability was added. Do not merge.

## Implementation Result

Implemented the direct-only Sentinel approval receipt foundation without adding a production write or dangerous tool. `ToolExecutionCoordinator` remains the sole execution choke point, Sentinel runs before receipt handling on every attempt, chat explicitly disables approval handling, and the direct grant endpoint never executes a tool.

The implementation adds:

- Frozen, extra-forbidden approval and challenge contracts
- Process-local HMAC-SHA256 request binding with restart invalidation
- One recorded SQLite migration and an exact seven-column approval table
- Atomic pending-to-approved and approved-to-consumed transitions
- Direct challenge, grant, exact-request retry, expiry, invalidation, and replay handling
- Approval-capability redaction for the grant path in structured access logs
- Payload-free `approval_expired` and `approval_invalid` audit outcomes while retaining the v0.9 ten-column audit schema
- README documentation for the trusted-local-client boundary and two-step flow
- Version `0.10.0` across package, runtime, health, and tests

Build Head validation completed on 2026-10-01:

- `479 passed, 1 warning` from the complete pytest suite
- Focused approval persistence, coordinator, API, audit, chat-isolation, migration-upgrade, concurrency, and privacy coverage passed
- `python -m compileall -q src tests` passed
- `git diff --check` passed
- README and task relative-link checks passed with zero broken links
- Documented startup succeeded on Windows with `GET /v1/health` returning `0.10.0`
- Direct `system.runtime_info` smoke execution succeeded with Sentinel `allow` and JARVIS version `0.10.0`
- A live unknown-ID grant request returned safe `404` while the uvicorn access log contained `[redacted]` instead of the approval UUID

The remaining known limitation is intentional: this is a loopback-local trusted-client bootstrap boundary without authentication, multi-user identity, remote approval, or an approval UI. No production side-effecting capability, provider feature, worker, voice feature, browser/desktop control, credential storage, or new dependency was added.
