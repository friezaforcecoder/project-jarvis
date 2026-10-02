# JARVIS Operator HUD v0.11

Status: implementation complete on `codex/operator-hud-v0.11`; pending draft
PR CI and Build Head review.

## Goal

Deliver the first comfortable, daily-usable interface for JARVIS Core without
moving memory, policy, tools, or privileged behavior out of Core.

The completed application version for this milestone is `0.11.0`.

## User Outcome

From a locally running JARVIS Core process, a user can open `/`, converse with
JARVIS, continue the current durable session after reopening the HUD, start a
new session, see connection and tool-activity state, and explicitly request the
existing system and desktop context capabilities without using curl commands.

## Implement

- Serve a responsive, packaged HUD from JARVIS Core at `/`.
- Use only same-origin Core APIs and locally packaged assets.
- Add a bounded read-only conversation transcript endpoint for one known
  session ID.
- Store only the current session ID in browser storage. Core remains the
  authoritative owner of conversation content.
- Render all user and provider text as text, never executable markup.
- Show service health, provider/model metadata, tool activity, busy state, and
  normalized errors.
- Provide explicit quick requests for system status, the foreground app, and
  visible applications. Do not inspect desktop context automatically.
- Provide a new-session control that clears only the HUD's local session
  pointer. This milestone does not delete durable Core history.
- Add a `jarvis` console command and an optional `--open` flag that opens the
  HUD after the local service becomes healthy.
- Update the README and version metadata.

## Security And Ownership

- The HUD is an interface into JARVIS Core, not a second assistant runtime.
- The HUD must not access SQLite directly or own durable messages or policy.
- The HUD must not execute operating-system actions directly.
- Existing Tool Fabric and Sentinel boundaries remain authoritative.
- No external scripts, fonts, analytics, CDNs, or remote UI resources.
- Apply a restrictive content security policy and safe response headers.
- Do not place prompts, responses, desktop context, or session transcripts in
  normal application logs.
- The local service remains intended for trusted loopback use only.

## Out Of Scope

- Voice input or speech output
- Wake words or continuous listening
- Streaming model responses
- New side-effecting tools
- General model-selected tool calling
- Session deletion, search, rename, or list-all APIs
- React, Tauri, Node, or a second web service
- Authentication, remote access, phone interfaces, or deployment

## Acceptance Criteria

- `/` returns the usable HUD and packaged CSS/JavaScript assets.
- Reopening the HUD restores a known durable transcript through Core.
- Unknown sessions produce a safe normalized error and can be abandoned from
  the HUD without corrupting Core state.
- Chat uses the existing `/v1/chat` contract and preserves session IDs.
- Context shortcuts are explicit user actions and route through existing chat
  tool behavior.
- User and assistant content is inserted with safe text rendering.
- The HUD remains usable at desktop and narrow mobile viewport sizes.
- Automated tests cover routes, headers, transcript bounds/errors, launcher
  behavior, and existing regressions.
- The complete test suite, compilation, whitespace, package build, startup,
  and desktop/mobile browser smoke checks pass.
- CI passes on Windows and Ubuntu before merge.

## Implementation Result

- The packaged HUD, bounded transcript API, and `jarvis --open` launcher are
  implemented without a new runtime dependency or external UI resource.
- `492` automated tests pass with one existing Starlette/httpx deprecation
  warning.
- Source/test compilation, whitespace checks, and seven relative
  documentation links pass.
- The wheel build includes `index.html`, `hud.css`, and `hud.js`.
- Real local startup at `0.11.0`, Ollama chat, deterministic active-window
  routing, durable transcript restoration, console inspection, and responsive
  browser checks at wide, 390px, and 320px viewports pass.
- GitHub CI remains pending until the draft PR runs.
