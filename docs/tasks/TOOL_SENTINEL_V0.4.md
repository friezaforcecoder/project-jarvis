# Project J.A.R.V.I.S. Tool Fabric And Sentinel v0.4

Status: proposed

## Goal

Create the first real tool execution pipeline for JARVIS Core.

This milestone answers one question:

Can JARVIS execute a deterministic registered tool through trusted tool metadata, typed argument validation, Sentinel authorization, normalized results, and safe logs without connecting tools to chat or autonomous agents?

This is a Tool Fabric and Sentinel safe-execution foundation only. It is not LLM tool calling, automatic tool selection, agent execution, operating-system automation, browser automation, MCP, or an approval UI.

The completed application version for this milestone is `0.4.0`, but version changes belong only in the implementation pass.

## Implement

- Tool registry for registered tool implementations
- Exact-name tool lookup
- Duplicate tool registration rejection
- Stable unknown-tool behavior
- Trusted tool descriptors exposed by the registry
- Tool execution coordinator/router
- Typed Pydantic argument validation per concrete tool
- Sentinel authorization before tool execution
- Concrete deterministic Sentinel policy implementation
- One harmless built-in proof tool: `system.runtime_info`
- Direct API endpoint: `POST /v1/tools/execute`
- Stable API request, response, and error contracts
- Correlation ID preservation and generation
- Normalized tool, Sentinel, validation, and internal failures
- Safe structured logging for tool execution lifecycle
- Tests for registry, coordinator, Sentinel policy, built-in tool, API behavior, and logging
- Documentation for manual `system.runtime_info` verification

## Do Not Implement

- LLM/model tool calling
- Automatic tool selection from chat
- Chat-to-tool integration
- Agent loops
- Windows control
- PowerShell or shell execution
- Arbitrary command execution
- Arbitrary filesystem access
- Browser automation
- Web search
- Gmail
- Google Calendar
- GitHub integrations
- MCP
- Home Assistant
- Approval UI
- Approval persistence
- Voice
- Speech recognition
- Semantic memory
- Vector databases
- Background or proactive agents
- Desktop UI
- Phone UI
- New database technology
- Queues
- Microservices
- Deployment
- Releases

## Required Execution Path

The conceptual execution path must be:

```text
API request
-> Tool Registry lookup
-> trusted ToolDescriptor metadata
-> typed argument validation
-> Sentinel authorization
-> Tool execution only if authorized
-> normalized ToolResult
-> safe structured logging
```

The caller must not be able to override trusted registered tool metadata, including:

- `side_effect_level`
- `execution_boundary`
- permissions or policy metadata

Those values must come from the registered tool descriptor itself.

If the API request contains fields that attempt to spoof descriptor or Sentinel metadata, the request should either reject those fields through strict request validation or ignore them because they are not part of the API contract. Prefer strict rejection using Pydantic `extra="forbid"` for external contracts.

## Tool Registry

Add a small registry owned by the `tools` module.

The registry should:

- Register tool implementations by stable exact tool name.
- Reject duplicate tool names with a stable typed error.
- Retrieve a tool by exact name.
- Return a stable typed error for unknown tool names.
- Expose trusted descriptors from registered tools.
- Preserve registered descriptor metadata as trusted internal state.
- Avoid importing or initializing tools with network, credential, or operating-system side effects.

Suggested ownership:

```text
src/jarvis_core/tools/
  contracts.py      typed Tool, ToolDescriptor, ToolRequest, ToolResult contracts
  registry.py       ToolRegistry and registry errors
  router.py         ToolExecutionCoordinator or ToolRouter
  builtins.py       harmless built-in tool registrations, or a builtins/ package
```

The exact file names may differ, but ownership must remain clear.

## Tool Contract Evolution

Bootstrap v0.1 already includes minimal `Tool`, `ToolDescriptor`, `ToolRequest`, and `ToolResult` contracts.

For v0.4, evolve those contracts only as needed to support real safe execution.

Required contract direction:

- Each concrete tool must own or expose a typed Pydantic argument model.
- The execution coordinator must validate raw `arguments` against that model before Sentinel authorization.
- The descriptor `input_schema` may be generated from the typed model or kept explicitly compatible with it.
- Runtime argument validation must not rely only on `descriptor.input_schema`.
- Tool execution should receive validated arguments, not unvalidated caller data.
- Tool result data must be normalized into a `ToolResult` or endpoint response.
- Tool exceptions must be normalized and must not leak stack traces or raw local details through the API.

One acceptable small contract change is:

```text
Tool.argument_model -> type[pydantic.BaseModel]
Tool.execute(validated_arguments, context) -> ToolResult
```

Another acceptable approach is to preserve the existing `Tool.execute(request)` shape while adding an explicit argument model and ensuring the `ToolRequest` passed to the tool contains only validated arguments. The implementation should choose the smallest maintainable shape.

Because there are no production tools yet, small internal compatibility changes to the bootstrap Tool protocol are acceptable if tests and documentation explain why.

## Tool Execution Coordinator

Add a coordinator owned by the Tool Fabric boundary.

The coordinator should:

- Accept a typed `ToolRequest`.
- Preserve a caller-supplied correlation ID or generate one when omitted.
- Resolve the registered tool by exact `tool_name`.
- Retrieve trusted `ToolDescriptor` metadata from the registered tool.
- Validate `arguments` against the registered tool's typed Pydantic argument model.
- Fail invalid arguments before Sentinel authorization.
- Fail invalid arguments before tool execution.
- Construct a Sentinel `AuthorizationRequest` using trusted descriptor metadata.
- Call Sentinel before execution.
- Execute the tool only when Sentinel returns `ALLOW`.
- Return an approval-required result or error when Sentinel returns `ASK`.
- Return a denied result or error when Sentinel returns `DENY`.
- Normalize tool execution exceptions.
- Normalize Sentinel exceptions.
- Log safe lifecycle metadata.

The coordinator must not:

- Trust side-effect or execution-boundary values supplied by the caller.
- Execute a tool before Sentinel authorization.
- Execute a tool when Sentinel returns `ASK`.
- Execute a tool when Sentinel returns `DENY`.
- Log raw arguments or raw tool results by default.
- Route chat messages to tools.
- Ask an LLM to select tools.

## Sentinel Policy

Add one concrete deterministic Sentinel policy implementation.

The default v0.4 policy is:

```text
SideEffectLevel.NONE      -> ALLOW
SideEffectLevel.READ      -> ALLOW
SideEffectLevel.WRITE     -> ASK
SideEffectLevel.DANGEROUS -> DENY
```

`ASK` must not execute the tool.

For v0.4, `ASK` means the API returns a stable approval-required response or error. There is no approval UI, approval persistence, approval token, or retry-after-approval flow in this milestone.

The policy implementation should:

- Be deterministic.
- Require no external services.
- Require no secrets.
- Avoid reading user files, environment variables, or system state.
- Return a typed `AuthorizationDecision` with an action and safe reason.

Suggested ownership:

```text
src/jarvis_core/sentinel/
  contracts.py      existing authorization contracts
  policy.py         DefaultSentinelPolicy or DefaultSentinel
```

## Built-In Proof Tool

Add one harmless deterministic built-in tool:

```text
system.runtime_info
```

The tool must:

- Use Python standard library only.
- Require no network access.
- Require no credentials.
- Have side-effect level `READ` or `NONE`.
- Execute inside the `CORE` boundary.
- Accept no meaningful user-controlled arguments.
- Return only safe runtime metadata.

Allowed response data:

```text
platform_family = broad OS/platform family such as Windows, Linux, Darwin, or Java
python_version = Python version string
jarvis_version = JARVIS application version
```

The tool must not return:

- Username
- Hostname
- IP addresses
- Environment variables
- Process list
- File contents
- Serial numbers or device IDs
- Secrets
- Full filesystem paths
- Machine-specific identifiers

The argument model should reject unexpected arguments. For example, an empty Pydantic model with `extra="forbid"` is sufficient.

## API Endpoint

Add:

```text
POST /v1/tools/execute
```

Expected request semantics:

```text
tool_name = exact registered tool name
arguments = JSON object, defaulting to empty object when omitted if the implementation chooses
correlation_id = optional caller-supplied request/correlation ID
```

The exact JSON shape may be chosen by the implementation engineer, but it must be typed with Pydantic and tests must verify these semantics.

Recommended request shape:

```json
{
  "tool_name": "system.runtime_info",
  "arguments": {},
  "correlation_id": "optional-correlation-id"
}
```

Expected successful response semantics:

```text
status = success
tool_name = executed tool name
correlation_id = supplied or generated correlation ID
sentinel_decision = allow
result = normalized ToolResult or equivalent result object
```

Recommended successful response shape:

```json
{
  "status": "success",
  "tool_name": "system.runtime_info",
  "correlation_id": "generated-or-supplied-id",
  "sentinel": {
    "decision": "allow",
    "reason": "Safe read-only tool."
  },
  "result": {
    "success": true,
    "data": {
      "platform_family": "Windows",
      "python_version": "3.12.x",
      "jarvis_version": "0.4.0"
    },
    "error": null
  }
}
```

The response may use a slightly different stable shape if it follows existing API conventions and remains typed, safe, and tested.

## Stable API Errors

The API should return stable JSON error envelopes with appropriate HTTP status codes.

At minimum, support:

```text
unknown tool = 404, code tool_not_found
invalid arguments = 422, code tool_invalid_arguments
approval required = 403 or 409, code tool_approval_required
denied by Sentinel = 403, code tool_denied
tool execution failure = 500, code tool_execution_failed
Sentinel execution failure = 500, code sentinel_authorization_failed
internal execution failure = 500, code tool_internal_error
```

Error responses must include the correlation ID and safe error message. They may include the tool name when known.

Error responses must not expose:

- Raw tool arguments
- Raw tool result payloads
- Stack traces
- Environment variables
- Secrets
- Hostnames, usernames, IP addresses, or local filesystem paths
- Internal exception messages unless they have been explicitly normalized as safe

## Typed Argument Validation

Do not rely only on `ToolDescriptor.input_schema` at runtime.

Each concrete tool should own or expose a typed Pydantic argument model. The coordinator must use that model to validate incoming arguments.

Invalid arguments must fail before:

- Sentinel authorization
- Tool execution

Tests must prove both conditions.

The descriptor schema may be:

- Generated from the Pydantic argument model.
- Stored explicitly but tested for compatibility with the model.

For v0.4, prefer generating descriptor schema from the model if doing so keeps the code simpler.

## Logging And Auditability

Add safe structured logs around the tool execution lifecycle.

Logs may include:

- Correlation ID
- Tool name
- Sentinel decision
- Side-effect level from trusted descriptor metadata
- Execution boundary from trusted descriptor metadata
- Success or failure
- Safe error code
- Timing

Logs must not include:

- Raw tool arguments
- Raw tool result data
- Secrets
- Environment variables
- Stack traces in normal request logs
- Sensitive system identifiers

Sentinel decisions must be logged in a way that can later grow into a fuller audit trail without adding that full audit system in v0.4.

## Tests

Tests must not require Ollama, external network access, secrets, credentials, operating-system automation, browser automation, or MCP.

Add focused tests for:

- Successful tool registration.
- Duplicate tool registration rejection.
- Exact tool lookup.
- Unknown tool behavior.
- Trusted descriptor metadata exposure.
- Successful `system.runtime_info` execution.
- `system.runtime_info` response contains safe runtime metadata.
- `system.runtime_info` response excludes username, hostname, IP addresses, environment variables, process lists, file contents, serial numbers, and secrets.
- Typed argument validation.
- Invalid arguments do not call Sentinel.
- Invalid arguments do not execute the tool.
- `SideEffectLevel.NONE` policy returns `ALLOW`.
- `SideEffectLevel.READ` policy returns `ALLOW`.
- `SideEffectLevel.WRITE` policy returns `ASK`.
- `SideEffectLevel.DANGEROUS` policy returns `DENY`.
- `ASK` does not execute the tool.
- `DENY` does not execute the tool.
- Caller cannot spoof side-effect metadata.
- Caller cannot spoof execution-boundary metadata.
- Tool exception becomes a normalized failure.
- Sentinel exception becomes a normalized failure.
- Correlation ID is preserved when supplied.
- Correlation ID is generated when omitted.
- `POST /v1/tools/execute` success for `system.runtime_info`.
- `POST /v1/tools/execute` stable unknown-tool error.
- `POST /v1/tools/execute` stable invalid-arguments error.
- `POST /v1/tools/execute` stable approval-required behavior.
- `POST /v1/tools/execute` stable denied behavior.
- Logs omit raw arguments and raw results.
- Existing health tests remain passing.
- Existing chat, working-memory, persistence, provider, config, and logging tests remain passing.

Run the complete local suite:

```bash
python -m pytest
python -m compileall src tests
git diff --check
```

CI must continue passing on both Ubuntu and Windows.

## Manual Acceptance Test

After implementation, manually verify:

```http
POST /v1/tools/execute
Content-Type: application/json
```

Request body:

```json
{
  "tool_name": "system.runtime_info",
  "arguments": {}
}
```

Expected behavior:

- Request succeeds.
- Correlation ID is generated and returned.
- Tool registry resolves `system.runtime_info`.
- Sentinel authorizes the tool.
- Tool executes.
- Response contains safe runtime metadata.
- No sensitive system information appears.
- Logs include safe metadata and omit raw arguments/results.

The response must not include username, hostname, IP addresses, environment variables, process lists, file contents, serial numbers, device IDs, secrets, or arbitrary filesystem paths.

## Documentation

Update documentation during implementation so another developer can:

1. Understand that v0.4 adds direct deterministic tool execution only.
2. Understand that chat does not call tools yet.
3. Understand the default Sentinel policy table.
4. Understand how to manually call `POST /v1/tools/execute`.
5. Understand the safe metadata returned by `system.runtime_info`.
6. Run tests without Ollama, network services, secrets, credentials, browser automation, or OS automation.

Documentation should include:

- One `curl` example for `system.runtime_info`.
- A short note that `WRITE` returns approval-required in v0.4 because approval UI/persistence is not built yet.
- A short note that `DANGEROUS` is denied by default.

## Acceptance Criteria

- Tool registry exists and is covered by tests.
- Tool registry registers tool implementations by exact stable name.
- Tool registry rejects duplicate names.
- Tool registry returns stable unknown-tool behavior.
- Tool registry exposes trusted registered descriptors.
- Tool execution coordinator accepts typed tool requests.
- Coordinator preserves supplied correlation IDs.
- Coordinator generates correlation IDs when omitted.
- Coordinator validates arguments against the registered tool's typed Pydantic argument model.
- Invalid arguments fail before Sentinel authorization.
- Invalid arguments fail before tool execution.
- Coordinator constructs Sentinel authorization from trusted descriptor metadata.
- Caller cannot override a registered tool's side-effect level.
- Caller cannot override a registered tool's execution boundary.
- Sentinel is called before execution.
- Tools execute only when Sentinel returns `ALLOW`.
- `ASK` returns stable approval-required behavior and does not execute the tool.
- `DENY` returns stable denied behavior and does not execute the tool.
- Default Sentinel policy maps `NONE` and `READ` to `ALLOW`.
- Default Sentinel policy maps `WRITE` to `ASK`.
- Default Sentinel policy maps `DANGEROUS` to `DENY`.
- `system.runtime_info` is registered as a built-in tool.
- `system.runtime_info` is deterministic, harmless, and standard-library-only.
- `system.runtime_info` returns only safe runtime metadata.
- `system.runtime_info` accepts no meaningful user-controlled arguments.
- `POST /v1/tools/execute` exists and uses typed Pydantic contracts.
- `POST /v1/tools/execute` successfully executes `system.runtime_info`.
- Stable API errors exist for unknown tool, invalid arguments, approval required, denied by Sentinel, tool execution failure, Sentinel execution failure, and internal execution failure if needed.
- Tool exceptions are normalized.
- Sentinel exceptions are normalized.
- Safe structured logs are emitted for tool execution lifecycle.
- Logs do not include raw arguments or raw tool results by default.
- Existing chat, working-memory, health, persistence, provider, config, and logging tests remain passing.
- Tests require no Ollama, network access, external services, credentials, secrets, browser automation, OS automation, or MCP.
- CI passes on Windows and Ubuntu.
- JARVIS application/package/runtime version is updated to `0.4.0` only during implementation.
- No out-of-scope tool integrations or later milestone functionality are implemented.
- The structure follows `AGENTS.md`, `docs/MASTER_ARCHITECTURE.md`, and existing v0.1/v0.2/v0.3 boundaries.

## Definition Of Done

Another developer should be able to perform these steps using README instructions without reverse-engineering the project:

1. Clone
2. Install
3. Test without Ollama or external services
4. Start JARVIS Core
5. Verify health
6. Call `POST /v1/tools/execute` with `system.runtime_info`
7. Confirm Sentinel allowed the safe tool
8. Confirm only safe runtime metadata was returned

## Constraints

- Use Python 3.12+.
- Use type annotations.
- Use Pydantic for external and architectural contracts.
- Use pytest.
- Keep the implementation boring and maintainable.
- Keep JARVIS Core as a modular monolith.
- Do not add a new database, queue, cache, vector store, agent framework, browser automation stack, or service.
- Do not add Alembic or another migration framework.
- Do not add new runtime dependencies unless absolutely necessary and documented.
- Do not place tool execution logic in the chat route or intelligence provider layer.
- Do not connect chat to tools.
- Do not expose arbitrary commands, arbitrary filesystem access, browser automation, Windows control, MCP, Home Assistant, external APIs, or cloud integrations.
- Do not hide, delete, or weaken failing tests merely to claim completion.
- Do not silently change this task's acceptance criteria.

## Expected Completion Report

When implementation is complete, report:

- Branch
- Commit SHA
- Pull request link
- Files changed
- Tool registry summary
- Tool execution coordinator summary
- Sentinel policy summary
- Built-in `system.runtime_info` behavior
- API request/response examples
- Stable error behavior
- Logging/auditability behavior
- Tests and actual results
- CI status for Ubuntu and Windows
- Manual startup verification
- Manual health-check verification
- Manual `POST /v1/tools/execute` verification
- Any remaining warnings or limitations
