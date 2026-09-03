# Project J.A.R.V.I.S. Local System Context v0.5

Status: approved

## Goal

Give JARVIS its first useful awareness of the computer it is running on through one safe, deterministic, read-only system-status tool.

This milestone answers one question:

Can JARVIS return a small safe snapshot of local machine health through the existing Tool Fabric and Sentinel authorization path without building the full Context Engine, connecting chat to tools, or exposing sensitive identifiers?

This milestone makes the existing Tool Fabric genuinely useful while keeping chat/LLM tool calling out of scope.

The intended execution path remains:

```text
POST /v1/tools/execute
-> Tool Registry
-> typed arguments
-> Sentinel
-> system status collector
-> safe normalized result
```

The completed application version for this milestone is `0.5.0`, but version changes belong only in the implementation pass.

## Implement

- One new built-in tool: `system.status`
- `system.status` descriptor fixed to `SideEffectLevel.READ`
- `system.status` descriptor fixed to `ExecutionBoundary.CORE`
- Typed no-argument model for `system.status`
- Small deterministic local system-status collector outside the API route
- Typed collector/result models for CPU, memory, power, and system uptime
- Bounded CPU sampling that avoids meaningless first-call CPU percentages
- Blocking metric collection outside the async FastAPI event loop
- Safe normalized `ToolResult` data through the existing Tool Fabric response envelope
- Tests using mocks/patches for deterministic system metrics
- Documentation for manually verifying `system.status`
- Runtime dependency addition of `psutil`, justified below, during implementation only

## Do Not Implement

- Chat/LLM tool calling
- Automatic tool selection
- Agent loops
- Windows control
- PowerShell or shell commands
- Process enumeration
- Process termination
- Arbitrary filesystem access
- Disk or mount enumeration
- GPU monitoring
- Network monitoring
- Network-interface enumeration
- Browser automation
- Web search
- MCP
- Gmail, calendar, or GitHub integrations
- Approval UI
- WRITE tools
- DANGEROUS tools
- Background system monitoring
- Persistent telemetry or history
- Alerts
- Proactive behavior
- Screenshots
- Clipboard monitoring
- Window or application monitoring
- Desktop UI
- Voice
- Phone UI
- New database technology
- Queues
- Microservices

## Built-In Tool

Add one built-in tool:

```text
system.status
```

Descriptor requirements:

```text
side_effect_level = SideEffectLevel.READ
execution_boundary = ExecutionBoundary.CORE
```

The tool must:

- Be registered by default alongside `system.runtime_info`.
- Use the existing `POST /v1/tools/execute` endpoint.
- Use the existing Tool Registry.
- Use the existing typed argument validation path.
- Use the existing ToolExecutionCoordinator.
- Use the existing Sentinel authorization path.
- Be authorized by the existing default `READ -> ALLOW` policy.
- Accept no meaningful user-controlled arguments.
- Reject unexpected arguments through a Pydantic model with `extra="forbid"`.
- Return only a safe typed system-health snapshot.
- Return a normalized `ToolResult`.

The tool must not:

- Bypass ToolExecutionCoordinator.
- Bypass Sentinel.
- Trust caller-supplied side-effect or execution-boundary metadata.
- Return raw collector objects or raw `psutil` objects.
- Return raw exceptions.
- Execute shell, PowerShell, or arbitrary commands.
- Enumerate processes, disks, mounts, files, windows, clipboard, screenshots, applications, or network interfaces.

Keep the existing `system.runtime_info` tool unchanged and registered.

`system.runtime_info` answers:

```text
what JARVIS runtime am I using?
```

`system.status` answers:

```text
how is this computer doing right now?
```

Do not remove, rename, merge, or replace `system.runtime_info`.

## Safe Output Shape

`system.status` should return a typed, stable snapshot containing only useful non-sensitive machine-health information.

Required top-level sections:

```text
cpu
memory
power
system
```

Required CPU fields:

```text
usage_percent: float
logical_core_count: int
physical_core_count: int | null
```

Required memory fields:

```text
total_bytes: int
available_bytes: int
used_bytes: int
usage_percent: float
```

Required power fields:

```text
battery_present: bool
battery_percent: float | null
plugged_in: bool | null
```

Required system fields:

```text
uptime_seconds: float
```

Values that are unavailable on a platform must use explicit nullable fields rather than fabricated values.

Do not return:

- Username
- Hostname or computer name
- IP address
- MAC address
- Network interfaces
- Environment variables
- Process list
- Command lines
- Open files
- Filesystem paths
- Drive or mount names
- Serial numbers
- Device IDs
- Motherboard information
- Account information
- Secrets
- Clipboard
- Window titles
- Screenshots
- Installed application lists
- Arbitrary file contents

Do not add disk/storage enumeration in v0.5. Configured storage context can be handled separately later without leaking mount or path information.

## Representative API Example

Do not add a new endpoint.

Use the existing endpoint:

```text
POST /v1/tools/execute
```

Representative request:

```json
{
  "tool_name": "system.status",
  "arguments": {}
}
```

Representative success response:

```json
{
  "status": "success",
  "tool_name": "system.status",
  "correlation_id": "generated-or-supplied-correlation-id",
  "sentinel": {
    "decision": "allow",
    "reason": "Safe no-write tool execution is allowed."
  },
  "result": {
    "success": true,
    "data": {
      "cpu": {
        "usage_percent": 12.5,
        "logical_core_count": 16,
        "physical_core_count": 8
      },
      "memory": {
        "total_bytes": 34359738368,
        "available_bytes": 20000000000,
        "used_bytes": 14359738368,
        "usage_percent": 41.8
      },
      "power": {
        "battery_present": false,
        "battery_percent": null,
        "plugged_in": null
      },
      "system": {
        "uptime_seconds": 123456.0
      }
    },
    "error": null
  }
}
```

Exact formatting may follow the existing v0.4 response models, but names and sections must remain stable, typed, small, and understandable.

## Collection Architecture

Add a small deterministic local system-status collector owned outside the API route.

Suggested ownership:

```text
src/jarvis_core/context/
  __init__.py
  system_status.py
```

Alternative ownership inside a dedicated `tools` helper module is acceptable only if the collector remains separate from the FastAPI route and the tool wrapper remains small.

The collector should:

- Produce typed internal/output models.
- Collect CPU, memory, power, and uptime information.
- Convert platform-unavailable values into explicit `None` values.
- Avoid returning raw `psutil` objects.
- Avoid returning raw exceptions.
- Avoid logging sensitive values.
- Be deterministic in shape even when platform values vary.

The `system.status` built-in tool should call the collector and then return the collector's safe data through `ToolResult`.

Do not create:

- A service
- A daemon
- A queue
- A database table
- A background poller
- An event loop
- A cache
- A long-running Context Engine
- Persistent telemetry history

## psutil Dependency

It is acceptable and preferred for the implementation pass to add `psutil` as the single new runtime dependency.

Justification:

- `psutil` is a mature cross-platform library.
- It supports Windows and Linux CI.
- It avoids fragile platform-specific shell or PowerShell commands.
- It avoids building operating-system metric collection ourselves.
- It provides CPU, memory, battery, and boot-time information through a stable Python API.

Do not add any other new runtime dependency unless there is an exceptional documented reason.

No dependency changes should be made during this spec-only pass.

## CPU Sampling

Avoid returning a meaningless first-call CPU percentage.

Use a short fixed bounded CPU sampling interval, approximately:

```text
0.1 to 0.25 seconds
```

Because blocking CPU sampling should not stall the async FastAPI event loop, the implementation should perform blocking collection outside the event loop. A simple standard-library approach such as `asyncio.to_thread` is preferred.

Do not introduce background polling.

Do not introduce persistent sampling state.

## Privacy And Security

`system.status` must remain:

```text
SideEffectLevel.READ
ExecutionBoundary.CORE
```

All metrics must come from trusted implementation behavior, not caller-provided metadata.

The existing Sentinel path must remain unchanged:

```text
READ -> ALLOW
```

The tool must not bypass ToolExecutionCoordinator or Sentinel.

Any collection failure must flow through the existing normalized Tool Fabric failure behavior, such as `tool_execution_failed`, without exposing raw `psutil` exceptions or stack traces through the API.

Safe structured logs may include:

- Correlation ID
- Tool name
- Sentinel decision
- Side-effect level
- Execution boundary
- Success or failure
- Safe error code
- Timing

Logs must not include:

- Raw metric payloads
- Raw collector exceptions
- Username, hostname, IP, MAC, environment variables, process data, filesystem paths, serial numbers, device IDs, secrets, clipboard contents, window titles, or screenshots

## Tests

Tests must not require Ollama, network access, external services, credentials, secrets, browser automation, operating-system automation, or MCP.

Use mocks or patches for system metric collection where needed so CI is deterministic and does not depend on exact machine CPU, RAM, or battery values.

Add focused tests for:

- `system.status` is registered by default.
- `system.status` descriptor is exactly `SideEffectLevel.READ`.
- `system.status` descriptor is exactly `ExecutionBoundary.CORE`.
- `system.status` argument model rejects unexpected arguments.
- Sentinel authorizes `system.status` through the existing `READ -> ALLOW` policy.
- Successful CPU metrics are returned.
- Successful memory metrics are returned.
- Successful power metrics are returned when a battery exists.
- Stable power behavior is returned when no battery exists.
- Physical core count may be `null` when unavailable.
- Uptime is non-negative.
- Typed result structure is stable.
- Only approved top-level fields appear.
- Only approved section fields appear.
- Sensitive fields are not returned.
- No username is returned.
- No hostname is returned.
- No IP or network information is returned.
- No MAC address or network-interface information is returned.
- No environment variables are returned.
- No process data is returned.
- No command lines are returned.
- No filesystem paths are returned.
- No disk, drive, or mount information is returned.
- No serial or device identifiers are returned.
- Collector or `psutil` failure becomes the existing normalized `tool_execution_failed` behavior.
- Correlation IDs continue working for `system.status`.
- Existing `system.runtime_info` still works.
- Existing v0.1-v0.4 tests continue passing.

Include at least one lightweight real-platform sanity test only if it can remain reliable on both Ubuntu and Windows CI. Such a test may assert only broad invariants, such as section presence, non-negative uptime, and allowed field names.

Run the complete local suite:

```bash
python -m pytest
python -m compileall src tests
git diff --check
```

CI must continue passing on both Ubuntu and Windows.

If pytest fails specifically because it cannot access Windows temp or `.pytest_cache` directories, rerun it using an accessible temporary directory rather than modifying tests to hide the problem.

## Manual Acceptance Test

After implementation, start JARVIS Core and call:

```http
POST /v1/tools/execute
Content-Type: application/json
```

Request body:

```json
{
  "tool_name": "system.status",
  "arguments": {}
}
```

Expected behavior:

- HTTP 200.
- Sentinel decision is `allow`.
- CPU information is returned.
- Memory information is returned.
- Power section is returned.
- Uptime is returned.
- No sensitive identifiers or paths are returned.
- JARVIS continues running normally afterward.

Manual verification should also confirm that `system.runtime_info` still works.

## Documentation

Update documentation during implementation so another developer can:

1. Understand that v0.5 adds one local system-status tool.
2. Understand that chat does not call tools yet.
3. Understand that `system.status` uses the existing `POST /v1/tools/execute` endpoint.
4. Understand that `system.status` is `READ` + `CORE`.
5. Understand what safe fields are returned.
6. Understand which sensitive fields are intentionally excluded.
7. Understand why `psutil` is used.
8. Run tests without Ollama, network services, secrets, credentials, browser automation, or OS automation.

Documentation should include:

- One `curl` example for `system.status`.
- A representative response shape.
- A short note that no disk, process, network, screenshot, clipboard, or window context is collected in v0.5.
- A short note that this is not the full Context Engine and does not include background monitoring or persistent telemetry.

## Acceptance Criteria

- `system.status` is registered by default.
- `system.runtime_info` remains registered and unchanged.
- `system.status` uses `SideEffectLevel.READ`.
- `system.status` uses `ExecutionBoundary.CORE`.
- `system.status` accepts no meaningful user-controlled arguments.
- Unexpected `system.status` arguments are rejected by typed Pydantic validation.
- `system.status` executes only through ToolExecutionCoordinator.
- `system.status` executes only after Sentinel authorization.
- Sentinel authorizes `system.status` through the existing `READ -> ALLOW` policy.
- `POST /v1/tools/execute` successfully executes `system.status`.
- No new endpoint is added.
- CPU status includes usage percent, logical core count, and nullable physical core count.
- Memory status includes total bytes, available bytes, used bytes, and usage percent.
- Power status includes battery presence, nullable battery percent, and nullable plugged-in status.
- System status includes non-negative uptime seconds.
- Unavailable platform values are represented as `null`, not fabricated.
- CPU sampling uses a short bounded interval and avoids meaningless first-call CPU percentages.
- Blocking collection runs outside the async FastAPI event loop.
- Collector logic is owned outside the API route.
- Collector and result models are typed.
- `psutil` is the only new runtime dependency, and its use is documented.
- No shell, PowerShell, arbitrary command execution, process enumeration, disk enumeration, network enumeration, filesystem access, screenshots, clipboard access, or window monitoring is implemented.
- No username, hostname, IP address, MAC address, network interfaces, environment variables, process data, command lines, open files, filesystem paths, drive names, mount names, serial numbers, device IDs, account information, secrets, clipboard contents, window titles, screenshots, installed applications, or arbitrary file contents are returned.
- Collection failures become existing normalized Tool Fabric failure behavior.
- Correlation IDs continue to be preserved/generated and returned.
- Safe structured logging behavior remains consistent with v0.4 and does not include raw metric payloads.
- Existing health, chat, working-memory, persistence, provider, Tool Fabric, Sentinel, config, and logging tests remain passing.
- Tests require no Ollama, network access, external services, credentials, secrets, browser automation, OS automation, or MCP.
- CI passes on Windows and Ubuntu.
- JARVIS application/package/runtime version is updated to `0.5.0` only during implementation.
- No out-of-scope Context Engine, monitoring, telemetry, tool-calling, agent, UI, automation, MCP, or later milestone functionality is implemented.
- The structure follows `AGENTS.md`, `docs/MASTER_ARCHITECTURE.md`, `docs/tasks/TOOL_SENTINEL_V0.4.md`, and existing v0.1-v0.4 boundaries.

## Definition Of Done

Another developer should be able to perform these steps using README instructions without reverse-engineering the project:

1. Clone
2. Install
3. Test without Ollama or external services
4. Start JARVIS Core
5. Verify health
6. Call `POST /v1/tools/execute` with `system.runtime_info`
7. Call `POST /v1/tools/execute` with `system.status`
8. Confirm Sentinel allowed `system.status`
9. Confirm CPU, memory, power, and uptime sections are returned
10. Confirm sensitive identifiers and paths are absent

## Constraints

- Use Python 3.12+.
- Use type annotations.
- Use Pydantic for external and architectural contracts.
- Use pytest.
- Keep the implementation boring and maintainable.
- Keep JARVIS Core as a modular monolith.
- Use the existing Tool Fabric and Sentinel boundaries.
- Do not connect chat or the LLM to tools.
- Do not add a new database, queue, cache, vector store, agent framework, browser automation stack, service, daemon, or background worker.
- Do not add new runtime dependencies beyond `psutil` unless there is an exceptional documented reason.
- Do not expose arbitrary commands, arbitrary filesystem access, browser automation, Windows control, MCP, Home Assistant, external APIs, disk enumeration, process enumeration, network enumeration, screenshots, clipboard, window monitoring, or cloud integrations.
- Do not hide, delete, or weaken failing tests merely to claim completion.
- Do not silently change this task's acceptance criteria.

## Expected Completion Report

When implementation is complete, report:

- Branch
- Commit SHA
- Pull request link if one is opened in that pass
- Files changed
- Dependency changes
- `system.status` tool summary
- Collector architecture summary
- API request/response example
- Safe-output and excluded-data summary
- Sentinel authorization behavior
- Tests and actual results
- CI status for Ubuntu and Windows if available
- Manual startup verification
- Manual health-check verification
- Manual `system.runtime_info` verification
- Manual `system.status` verification
- Any remaining warnings or limitations
