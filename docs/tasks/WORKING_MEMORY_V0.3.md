# Project J.A.R.V.I.S. Working Memory v0.3

Status: proposed

## Goal

Add simple persistent multi-turn conversation sessions to the existing text intelligence loop.

This milestone answers one question:

Can JARVIS preserve recent chat turns for a named session across process restarts, include bounded session history in provider-neutral model requests, and avoid pretending a failed provider call produced an assistant response?

This is working-memory/session persistence only. It is not semantic memory, long-term knowledge, user preference storage, retrieval, summarization, or autonomous behavior.

The proposed completed application version for this milestone is `0.3.0`. Do not change the application version until this milestone is implemented.

## Implement

- Extend `POST /v1/chat` with optional `session_id`
- Generate and return a `session_id` when the caller does not supply one
- Load recent persisted conversation turns when an existing `session_id` is supplied
- Include bounded recent conversation history in provider requests
- Persist successful user/assistant exchanges in SQLite
- Preserve sessions across JARVIS Core restarts
- Preserve correlation IDs separately from session IDs
- Add typed conversation, session, and message contracts
- Add a small conversation persistence/repository boundary
- Add schema migration/version handling for conversation tables
- Add configurable bounded context history
- Add deterministic per-session message ordering
- Serialize concurrent chat operations for the same session within one JARVIS Core process
- Preserve the provider-neutral intelligence boundary
- Keep Ollama conversation-state-free by passing normalized messages from Core
- Keep normal structured logs free of raw prompt and response contents
- Add tests using fake providers and temporary SQLite databases
- Update documentation for session configuration and manual verification

## Do Not Implement

- Semantic long-term memory
- Preference extraction
- Fact extraction
- Episodic memory intelligence
- Vector search
- Embeddings
- Conversation summarization
- Memory consolidation
- Contradiction detection
- Automatic memory promotion
- User/profile memory
- Project memory
- Tool calling
- Sentinel execution
- Windows control
- Browser control
- Voice
- Speech recognition
- MCP
- Autonomous workers
- Proactive monitoring
- Desktop UI
- Phone UI
- Deployment
- Releases
- New external services

## Chat Endpoint

Extend the existing endpoint:

`POST /v1/chat`

Expected request semantics:

```text
message = user text message
correlation_id = optional caller-supplied request/correlation ID
session_id = optional JARVIS conversation session ID
```

Expected response semantics:

```text
message = assistant text response
provider = selected provider identifier
model = selected provider model
correlation_id = request correlation ID, generated when not supplied
session_id = conversation session ID, generated when not supplied
```

The exact JSON shape may be chosen by the implementation engineer, but it must be typed with Pydantic and tests must verify these semantics.

Correlation IDs and session IDs are different concepts:

- `correlation_id` identifies one API/provider request for tracing.
- `session_id` identifies a durable conversation session across turns and restarts.

## Session IDs

Use generated UUID strings for new session IDs.

When no `session_id` is supplied:

- Generate a new UUID session ID.
- Create a new session record.
- Route the chat request with no prior conversation history.
- Return the generated `session_id`.

When a valid existing `session_id` is supplied:

- Load that session.
- Load up to the configured number of recent messages for that session.
- Include those messages in the normalized provider request before the current user message.
- Return the same `session_id`.

When a malformed `session_id` is supplied:

- Reject the request before provider execution.
- Do not create a session.
- Do not persist a message.
- Return a stable client error such as HTTP 422 with safe validation details.

When a well-formed but unknown `session_id` is supplied:

- Do not silently create a session.
- Do not call the provider.
- Do not persist a message.
- Return a stable error such as HTTP 404 with code `session_not_found`.

This avoids hiding caller bugs and prevents accidental fragmentation of conversation history.

## Conversation Persistence

Add a small repository boundary for conversation storage. The API route should not contain raw SQL.

Suggested ownership:

```text
src/jarvis_core/
  conversations/    typed session/message contracts and repository-facing models
  persistence/      SQLite schema initialization, migration helpers, and SQLite repository implementation
```

The implementation may choose the exact package names, but ownership must remain clear:

- API validates request/response shapes.
- Chat service coordinates session lookup, bounded history, provider calls, and persistence.
- Provider router remains provider-neutral.
- SQLite persistence is isolated behind a small repository interface.
- Ollama does not own session lookup, context selection, or storage.

Persist only successful user/assistant exchanges.

For a successful chat request:

1. Validate and load the existing session, or reserve a generated session ID in memory if no session was supplied.
2. Load bounded recent history.
3. Send normalized provider input.
4. Persist the durable session record when needed, the current user message, and the assistant response in one successful transaction.
6. Return the normalized chat response.

Atomic successful-turn persistence is required:

- A successful user/assistant exchange must be committed atomically.
- For a newly generated session, creation of the durable session record plus both messages must occur in the same successful persistence transaction after provider execution.
- For an existing session, the user and assistant messages must be committed together.
- If persistence fails, roll back the entire turn rather than leaving a partial exchange.

## SQLite Schema

Keep the SQLite schema deliberately simple.

Reasonable tables:

```text
conversation_sessions
  id TEXT PRIMARY KEY
  created_at TEXT NOT NULL
  updated_at TEXT NOT NULL

conversation_messages
  id TEXT PRIMARY KEY
  session_id TEXT NOT NULL
  sequence INTEGER NOT NULL
  role TEXT NOT NULL
  content TEXT NOT NULL
  correlation_id TEXT
  created_at TEXT NOT NULL
  FOREIGN KEY(session_id) REFERENCES conversation_sessions(id)
```

Reasonable constraints and indexes:

- `role` should be constrained to supported chat roles such as `user` and `assistant`.
- Message ordering must be deterministic, using a monotonically increasing integer sequence or equivalent order value within each session.
- Do not rely primarily on timestamps plus UUID ordering.
- Enforce uniqueness for `(session_id, sequence)` or an equivalent deterministic ordering invariant.
- Index messages by `session_id` and ordering fields used for recent-history retrieval.
- Recent-history retrieval must return messages in their original conversational order.

Use proper schema migration/version handling consistent with the existing bootstrap persistence.

Required migration behavior:

- Preserve existing databases.
- Keep the existing `schema_migrations` table.
- Add a new migration entry such as `working-memory-v0.3`.
- Create missing conversation tables idempotently.
- Introduce only a small, maintainable migration mechanism, not an external migration framework.
- Record a migration in `schema_migrations` only after that migration has completed successfully.
- Apply migrations transactionally where SQLite permits.
- Do not delete, recreate, or wipe the database.
- Do not assume a fresh database in runtime code.
- Test creation of a fresh v0.3 database.
- Test in-place upgrade of a database containing the existing v0.2/bootstrap schema.

## Provider-Neutral Conversation Input

Intentionally evolve the current single-prompt provider contract into a normalized ordered message representation.

Extend the provider-neutral intelligence contract so providers receive normalized conversation messages from Core.

Required normalized message shape:

```text
role = system | user | assistant
content = message text
```

Use typed provider-neutral roles such as `system`, `user`, and `assistant`.

The normalized ordered message list should be the single source of conversational provider input. Do not keep duplicate representations where the current user message or history exists simultaneously in both a legacy `prompt` field and a message list.

Core should build the provider input in this order:

1. JARVIS system instruction from the identity boundary
2. Bounded recent session history
3. Current user message

Ollama may translate normalized messages into the Ollama request payload, but it must not:

- Query SQLite
- Decide how much history to include
- Create or validate sessions
- Persist messages
- Own conversation-state logic

The provider registry and chat endpoint must remain provider-neutral so another provider can be added later without changing session persistence behavior.

## Bounded Context History

Add a configurable context-history limit so an unlimited conversation is never sent to a provider.

Suggested environment variable:

```text
JARVIS_CHAT_HISTORY_LIMIT
```

Suggested default:

```text
10
```

The limit means the maximum number of prior persisted conversation messages included in the provider request. It does not include the system instruction or current user message.

When conversation history exceeds the configured limit:

- Load only the most recent `JARVIS_CHAT_HISTORY_LIMIT` messages.
- After selecting the recent window, do not send an orphaned assistant message as the first historical message.
- If truncation would make the first history item an assistant response whose user message was excluded, drop that leading assistant message.
- The effective number of included history messages may therefore be smaller than the configured limit.
- Keep persisted older messages in SQLite.
- Do not summarize, delete, vectorize, compress, or promote older messages.
- Preserve deterministic ordering of the included messages.

The setting must reject negative values. The implementation may allow `0` to mean no prior messages are included.

## Same-Session Concurrency

Within the current single JARVIS Core process, concurrent chat operations for the same `session_id` must not race and corrupt conversational ordering.

The simplest acceptable behavior is:

- Serialize chat operations for the same session.
- Allow different sessions to proceed concurrently.
- Allocate message sequence values inside the successful persistence transaction or under the same per-session serialization boundary.

Cross-process and multi-worker session coordination is explicitly out of scope for v0.3 and must be documented as a limitation.

## Failure Behavior

Provider failures must preserve the existing normalized error behavior from Intelligence v0.2.

When provider execution fails:

- Return the existing stable provider error response.
- Preserve the request correlation ID in the error response.
- If a new session ID was generated but the provider fails before anything is persisted, do not return that generated ID as though it represents a durable usable session.
- Existing provider-error response semantics may remain unchanged.
- Do not persist an assistant message.
- Avoid leaving a misleading successful exchange in history.
- Do not log raw user prompts or raw provider responses.

Recommended persistence behavior:

- For a new generated session, avoid creating a durable session if the provider fails.
- For an existing session, leave prior history unchanged if the provider fails.
- If the caller supplied an existing session ID, that session remains unchanged after the failed turn.
- If the implementation records failed user attempts, it must mark them explicitly as failed and must not include them as normal successful history in future provider requests.

For v0.3, the simplest acceptable behavior is to persist nothing from the failed turn.

When session lookup fails:

- Do not call the provider.
- Do not persist messages.
- Return a stable session error response.

When SQLite persistence fails:

- Do not call the provider if the session cannot be prepared safely.
- If persistence of the successful exchange fails after provider execution, return a stable server error rather than claiming the exchange was saved.
- Do not expose raw SQLite exceptions, file paths beyond safe configuration metadata, or stack traces in API responses.

## Restart Behavior

Sessions must survive JARVIS Core restarts.

Manual verification should demonstrate:

1. Start JARVIS Core with a configured SQLite database path.
2. Send a chat request without `session_id`.
3. Capture the returned `session_id`.
4. Stop JARVIS Core.
5. Start JARVIS Core again using the same database path.
6. Send a chat request with the captured `session_id`.
7. Verify the fake or real provider receives recent history for that session, or verify behavior through a deterministic test route/service test.

Automated tests should cover the restart behavior by creating a repository, writing a successful exchange, creating a new repository instance pointed at the same SQLite file, and loading the session history.

## Logging

Continue avoiding raw user prompts and assistant responses in normal structured logs.

Logs may include:

- Correlation ID
- Session ID
- Provider
- Model
- Timing
- Success or failure
- Safe error code
- Safe persistence error category
- Number of history messages included

Logs must not include:

- Raw user message content
- Raw assistant response content
- Full provider payloads
- Secrets
- Stack traces in normal request logs

## Tests

Tests must not require Ollama, external network access, secrets, or credentials.

Add focused tests for:

- `POST /v1/chat` generates and returns `session_id` when omitted.
- `POST /v1/chat` reuses an existing `session_id`.
- Successful user/assistant exchanges are persisted.
- Successful user/assistant exchanges are committed atomically.
- Session history survives a new repository/app instance using the same SQLite database.
- Existing `session_id` loads bounded recent history into the provider request.
- History exceeding `JARVIS_CHAT_HISTORY_LIMIT` sends only the most recent messages.
- Bounded-history truncation drops a leading orphaned assistant message.
- `JARVIS_CHAT_HISTORY_LIMIT=0` sends no prior history.
- Malformed `session_id` is rejected before provider execution.
- Well-formed unknown `session_id` returns `session_not_found` before provider execution.
- Provider failure does not persist an assistant message.
- Provider failure does not add the failed turn to normal future history.
- Same-session concurrent chat requests do not corrupt message ordering within one process.
- Correlation ID remains separate from session ID.
- Provider-neutral message contracts reject unknown fields.
- Ollama adapter receives normalized messages and does not own session-state logic.
- Existing provider error tests continue to pass.
- Existing `/v1/health` behavior continues to report the current application version.

Run the complete local suite:

```bash
python -m pytest
python -m compileall src tests
git diff --check
```

CI must continue passing on both Ubuntu and Windows.

## Documentation

Update documentation so another developer can:

1. Understand the difference between `correlation_id` and `session_id`.
2. Start a new conversation session.
3. Continue an existing conversation session.
4. Configure bounded history with `JARVIS_CHAT_HISTORY_LIMIT`.
5. Understand that sessions persist in SQLite across restarts.
6. Understand that this is working memory only, not semantic long-term memory.
7. Run tests without Ollama, network services, secrets, or credentials.

Documentation should include a small `curl` example for:

- First chat request without `session_id`
- Follow-up chat request using returned `session_id`
- Unknown session error behavior

## Acceptance Criteria

- `POST /v1/chat` accepts optional `session_id`.
- If no `session_id` is supplied, JARVIS generates one and returns it.
- If a valid existing `session_id` is supplied, JARVIS loads bounded recent history for that session.
- Successful user/assistant exchanges are persisted in SQLite.
- Successful user/assistant exchanges are committed atomically without partial turns.
- Sessions survive JARVIS Core restarts.
- Provider input includes JARVIS identity instructions, bounded recent history, and current user message.
- Provider input remains normalized and provider-neutral.
- Provider input uses a normalized ordered message list as the single source of conversational input.
- Ollama receives normalized conversation messages from Core and does not own conversation-state logic.
- Configurable bounded history prevents unlimited conversations from being sent to providers.
- Bounded-history truncation never sends a leading orphaned assistant message.
- Correlation IDs remain separate from session IDs.
- Malformed session IDs are rejected before provider execution.
- Well-formed unknown session IDs return a stable `session_not_found` error before provider execution.
- Provider failures preserve existing normalized provider error behavior.
- Provider failures do not persist misleading half-completed assistant exchanges.
- A generated session ID is not returned as a durable usable session when provider execution fails before persistence.
- Same-session chat operations are serialized within the current JARVIS Core process.
- Cross-process and multi-worker session coordination is documented as out of scope.
- Normal structured logs do not include raw prompts or raw assistant responses.
- SQLite schema migration preserves existing databases and records a v0.3 migration.
- SQLite migration records are written only after successful migration completion.
- Fresh v0.3 database creation and in-place v0.2/bootstrap schema upgrade are tested.
- Tests require no Ollama, external network, secrets, or credentials.
- Existing local tests pass.
- CI passes on Windows and Ubuntu.
- JARVIS application/package/runtime version is updated to `0.3.0` only during implementation.
- No out-of-scope memory intelligence or later milestone functionality is implemented.
- The structure follows `AGENTS.md`, `docs/MASTER_ARCHITECTURE.md`, and existing v0.1/v0.2 boundaries.

## Definition Of Done

Another developer should be able to perform these steps using README instructions without reverse-engineering the project:

1. Clone
2. Install
3. Test without Ollama
4. Start JARVIS Core
5. Verify health
6. Send a first chat request and receive a `session_id`
7. Send a follow-up chat request with the same `session_id`
8. Restart JARVIS Core
9. Continue the same session

## Constraints

- Use Python 3.12+.
- Use type annotations.
- Use Pydantic for external and architectural contracts.
- Use pytest.
- Keep the implementation boring and maintainable.
- Keep JARVIS Core provider-neutral outside provider adapters.
- Do not place session persistence logic in the Ollama adapter.
- Do not persist chat history outside SQLite.
- Do not add a new database, queue, cache, vector store, agent framework, or service.
- Do not add Redis, PostgreSQL, Docker, Celery, LangGraph, vector databases, message brokers, React, Tauri, or microservices.
- Do not implement semantic memory, summarization, embeddings, retrieval, tools, UI, automation, MCP, voice, or proactive behavior.
- Do not hide, delete, or weaken failing tests merely to claim completion.
- Do not silently change this task's acceptance criteria.

## Expected Completion Report

When implementation is complete, report:

- Branch
- Commit SHA
- Pull request link
- Files changed
- Schema migration summary
- Configuration added
- Tests and actual results
- CI status for Ubuntu and Windows
- Manual startup verification
- Manual health-check verification
- Manual new-session chat verification
- Manual continued-session chat verification
- Restart persistence verification
- Provider-failure persistence behavior
- Exact `POST /v1/chat` request/response examples
- Any remaining warnings or limitations
