# Project J.A.R.V.I.S. Intelligence v0.2

Status: approved

## Goal

Implement the first usable text intelligence loop for JARVIS Core.

This milestone answers one question:

Can JARVIS accept a local text chat request, route it through a replaceable intelligence provider, apply JARVIS identity instructions, and return a normalized response without building memory, tools, agents, or UI?

## Implement

- `POST /v1/chat`
- Typed chat request and response contracts
- Intelligence provider registry
- Simple provider routing to the configured default provider
- Ollama intelligence provider adapter
- Configurable Ollama base URL
- Configurable Ollama model
- Configurable provider timeout
- JARVIS identity/system instruction support
- Normalized provider errors
- Timeout handling distinguishable from general provider failures
- Generated correlation ID when the caller does not provide one
- Structured logs for chat request lifecycle and provider failures
- Tests using fake or mocked providers
- Documentation for configuring, testing, and manually verifying Ollama

## Do Not Implement

- Long-term memory
- Conversation persistence
- Vector search
- Voice
- Speech recognition
- Text-to-speech
- Windows automation
- Browser automation
- MCP
- Home Assistant
- Autonomous agents
- Background workers
- Research workers
- Codex workers
- Proactive monitoring
- Desktop UI
- Phone UI
- Streaming responses
- Tool calling
- Complex authentication
- Production deployment

## Chat Endpoint

`POST /v1/chat`

Expected request semantics:

```text
message = user text message
correlation_id = optional caller-supplied request/correlation ID
```

The exact JSON shape may be chosen by the implementation engineer, but it must be typed with Pydantic and tests must verify these semantics.

Expected response semantics:

```text
message = assistant text response
provider = selected provider identifier
model = selected provider model
correlation_id = request correlation ID, generated when not supplied
```

The endpoint should not persist conversation history. Any multi-turn context support is out of scope unless it is supplied entirely inside one request and is not stored.

## Provider Registry And Routing

Add a minimal provider registry owned by the intelligence module.

The registry should:

- Register provider instances by stable provider identifier.
- Resolve the configured default provider.
- Return a typed error when the configured provider is missing.
- Keep provider selection deterministic.
- Remain provider-neutral so another provider can be added later without changing the chat endpoint.

Routing should remain simple for v0.2:

- Route every chat request to the configured default provider.
- Do not implement model selection policy, cost policy, fallback chains, load balancing, or agent planning.
- Keep vendor-specific behavior out of core routing and inside provider adapters.

## Ollama Provider

Add one provider adapter for Ollama.

The adapter should:

- Use the configured Ollama base URL.
- Use the configured Ollama model.
- Send non-streaming chat requests to Ollama.
- Receive normalized provider input from JARVIS Core.
- Include the JARVIS system instruction from the normalized provider input as a system message or the closest Ollama-supported equivalent.
- Normalize Ollama connection failures, timeout failures, invalid responses, and non-success HTTP responses.
- Avoid logging raw prompts, raw model responses, secrets, or full provider payloads.

Configuration should include environment variables for:

```text
JARVIS_INTELLIGENCE_PROVIDER
JARVIS_OLLAMA_BASE_URL
JARVIS_OLLAMA_MODEL
JARVIS_PROVIDER_TIMEOUT_SECONDS
JARVIS_SYSTEM_INSTRUCTION
```

The implementation may choose safe defaults, but the README must document them. JARVIS Core must start successfully without Ollama running. Startup must not require an Ollama network call. Failures should occur only when a chat request needs the unavailable provider.

Allowed dependency change:

- `httpx` may be a runtime dependency for provider HTTP calls.

Do not add an Ollama SDK, LangChain, LangGraph, a queue, a database, or any agent framework for this milestone.

## Identity/System Instruction

JARVIS identity belongs to JARVIS Core and the identity boundary, not to the Ollama adapter.

Add minimal identity support that:

- Provides a default JARVIS system instruction.
- Allows overriding that instruction through configuration.
- Passes the resolved instruction into normalized provider requests.
- Does not store user preferences, relationship memory, or durable identity history.

Tests must verify that chat routing includes the resolved system instruction in the provider request.

## Error Handling

Provider failures must be normalized before reaching the API layer.

At minimum, represent:

- Provider unavailable
- Provider timeout
- Provider rejected request or returned a non-success response
- Provider returned an invalid response
- Unknown provider configuration

If Ollama is unavailable when `/v1/chat` is called, return a stable normalized provider error rather than crashing or exposing raw internal exceptions. Provider timeout errors must be distinguishable from general provider-unavailable/provider-failure errors.

The API should return consistent JSON error responses with appropriate HTTP status codes. Suggested mapping:

```text
unknown provider = 500
provider unavailable = 502
provider invalid response = 502
provider non-success response = 502
provider timeout = 504
```

Error responses must be safe for users and logs. They must not expose raw provider payloads, stack traces, local secrets, or full prompts.

## Logging

Do not log raw user prompts or assistant responses by default.

Logs may include:

- Correlation ID
- Provider
- Model
- Timing
- Success or failure
- Safe error code
- Safe HTTP status metadata

## Tests

Tests must not require Ollama, network access, or external credentials.

Add focused tests for:

- `POST /v1/chat` success using a fake provider
- Generated correlation ID when the caller does not provide one
- Provider registry registration and default-provider resolution
- Unknown default provider failure
- System instruction included in provider request
- Ollama adapter request construction using a mocked HTTP transport/client
- Ollama adapter timeout normalization
- Ollama adapter connection/error normalization
- Ollama adapter invalid-response normalization
- API error responses for normalized provider failures
- Existing `GET /v1/health` behavior remains unchanged

Run the complete test suite when practical.

## Documentation

Update startup/configuration documentation so another developer can:

1. Install the project.
2. Run tests without Ollama.
3. Install or start Ollama outside this repository.
4. Pull or configure a local model.
5. Configure JARVIS to use the Ollama URL and model.
6. Start JARVIS Core.
7. Manually verify `POST /v1/chat`.

Documentation must clearly state that CI and normal tests use fake or mocked providers and do not require Ollama.

## Acceptance Criteria

- Fresh clone can be installed using documented steps.
- Existing health endpoint still returns success.
- JARVIS Core starts successfully without Ollama running.
- Startup does not require an Ollama network call.
- `POST /v1/chat` exists and is covered by tests.
- Chat requests route through the intelligence provider registry.
- The configured default provider is used deterministically.
- The provider registry remains provider-neutral.
- Ollama provider URL and model are configurable.
- JARVIS system instruction is applied by JARVIS Core before provider execution.
- Provider errors and timeouts are normalized.
- Timeout errors are distinguishable from unavailable/failure errors.
- API error responses are safe and consistent.
- Correlation IDs are generated when omitted and returned in responses.
- Tests pass without Ollama installed or running.
- Tests require no network access or external credentials.
- Ollama manual verification is documented.
- No raw user prompts or assistant responses are logged by default.
- No secrets are committed.
- No later milestone functionality is implemented.
- The structure follows `docs/MASTER_ARCHITECTURE.md`.

## Definition Of Done

Another developer should be able to perform these steps using README instructions without reverse-engineering the project:

1. Clone
2. Install
3. Test without Ollama
4. Optionally configure Ollama
5. Run JARVIS Core
6. Verify health
7. Verify chat

## Constraints

- Use Python 3.12+.
- Use type annotations.
- Use Pydantic for external and architectural contracts.
- Use pytest.
- Keep the implementation boring and maintainable.
- Keep JARVIS Core provider-neutral outside provider adapters.
- Do not place Ollama-specific logic in the API route or core router.
- Do not persist chat history.
- Do not add memory intelligence, vector search, tool calling, workers, UI, automation, MCP, or smart-home integrations.
- Do not add Redis, PostgreSQL, Docker, Celery, LangGraph, vector databases, message brokers, React, Tauri, or microservices.
- Do not hide, delete, or weaken failing tests merely to claim completion.
- Do not silently change this task's acceptance criteria.

## Expected Completion Report

When implementation is complete, report:

- What was created
- Tests and actual results
- Manual startup verification
- Manual health-check verification
- Manual chat verification
- Whether Ollama verification was run locally
- Dependencies added or moved
- Architecture decisions or compromises
- Anything incomplete
- Exact command to start JARVIS Core
- Example `curl` command for `POST /v1/chat`
