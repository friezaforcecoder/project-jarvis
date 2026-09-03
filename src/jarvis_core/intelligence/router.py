"""Provider-neutral chat routing."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass
from time import perf_counter
from typing import AsyncIterator
from uuid import uuid4

from jarvis_core.conversations import (
    ConversationMessage,
    ConversationMessageRole,
    ConversationPersistenceError,
    ConversationRepository,
    ConversationSessionNotFoundError,
)
from jarvis_core.config import Settings
from jarvis_core.identity import resolve_system_instruction
from jarvis_core.intelligence.chat_tools import (
    ChatToolRoute,
    ChatToolRouter,
    build_trusted_tool_context_message,
    supported_chat_tool_names,
)
from jarvis_core.intelligence.contracts import (
    IntelligenceProvider,
    ProviderMessage,
    ProviderMessageRole,
    ProviderRequest,
)
from jarvis_core.intelligence.errors import ProviderError, ProviderErrorCode
from jarvis_core.intelligence.registry import ProviderRegistry
from jarvis_core.tools import (
    ExecutionBoundary,
    SideEffectLevel,
    ToolErrorCode,
    ToolExecutionError,
    ToolRegistry,
    ToolRequest,
)
from jarvis_core.tools.router import ToolExecutionCoordinator

logger = logging.getLogger(__name__)

_PROVIDER_ROLE_BY_CONVERSATION_ROLE = {
    ConversationMessageRole.USER: ProviderMessageRole.USER,
    ConversationMessageRole.ASSISTANT: ProviderMessageRole.ASSISTANT,
}


@dataclass(frozen=True)
class ChatResult:
    """Provider-normalized chat result returned to the API layer."""

    message: str
    provider: str
    model: str
    correlation_id: str
    session_id: str
    tools_used: list[str]


@dataclass
class _SessionLockEntry:
    """Ref-counted per-session lock entry."""

    lock: asyncio.Lock
    references: int = 0


class ChatService:
    """Route chat messages through the configured intelligence provider."""

    def __init__(
        self,
        settings: Settings,
        provider_registry: ProviderRegistry,
        conversation_repository: ConversationRepository,
        tool_registry: ToolRegistry | None = None,
        tool_execution_coordinator: ToolExecutionCoordinator | None = None,
        chat_tool_router: ChatToolRouter | None = None,
    ) -> None:
        self._settings = settings
        self._provider_registry = provider_registry
        self._conversation_repository = conversation_repository
        self._tool_registry = tool_registry
        self._tool_execution_coordinator = tool_execution_coordinator
        self._chat_tool_router = chat_tool_router or ChatToolRouter()
        self._session_locks: dict[str, _SessionLockEntry] = {}
        self._session_locks_guard = asyncio.Lock()

    async def chat(
        self,
        message: str,
        correlation_id: str,
        session_id: str | None = None,
    ) -> ChatResult:
        """Send one text message through the configured provider and session history."""

        resolved_session_id = session_id or str(uuid4())
        create_session = session_id is None
        provider = self._provider_registry.resolve_default(self._settings.intelligence_provider)

        async with self._session_lock(resolved_session_id):
            return await self._chat_with_session_lock(
                message=message,
                correlation_id=correlation_id,
                session_id=resolved_session_id,
                create_session=create_session,
                provider=provider,
            )

    async def _chat_with_session_lock(
        self,
        *,
        message: str,
        correlation_id: str,
        session_id: str,
        create_session: bool,
        provider: IntelligenceProvider,
    ) -> ChatResult:
        if not create_session and not self._conversation_repository.session_exists(session_id):
            raise ConversationSessionNotFoundError(session_id)

        history = (
            []
            if create_session
            else self._conversation_repository.load_recent_messages(
                session_id,
                self._settings.chat_history_limit,
            )
        )
        started_at = perf_counter()
        route = self._chat_tool_router.route(message)
        trusted_tool_context: ProviderMessage | None = None
        tools_used: list[str] = []
        if route is None:
            logger.info(
                "chat_tool_route_not_matched",
                extra={
                    "correlation_id": correlation_id,
                    "session_id": session_id,
                    "route_matched": False,
                },
            )
        else:
            trusted_tool_context = await self._execute_routed_tool(
                route=route,
                correlation_id=correlation_id,
                session_id=session_id,
                started_at=started_at,
            )
            tools_used = [route.tool_name]

        provider_request = ProviderRequest(
            messages=self._build_provider_messages(message, history, trusted_tool_context),
            context={
                "session_id": session_id,
                "history_message_count": len(history),
                "tools_used": tools_used,
                "tool_route_intent": route.intent.value if route else None,
            },
            correlation_id=correlation_id,
        )
        logger.info(
            "chat_request_started",
            extra={
                "correlation_id": correlation_id,
                "session_id": session_id,
                "provider": provider.provider_id,
                "history_message_count": len(history),
                "tools_used_count": len(tools_used),
            },
        )

        try:
            provider_response = await provider.generate(provider_request)
            if not provider_response.output.strip():
                raise ProviderError(
                    ProviderErrorCode.INVALID_RESPONSE,
                    "Intelligence provider returned an invalid response.",
                    provider_id=provider.provider_id,
                    model=provider_response.model,
                )
        except ProviderError as exc:
            elapsed_ms = round((perf_counter() - started_at) * 1000, 3)
            logger.warning(
                "chat_request_failed",
                extra={
                    "correlation_id": correlation_id,
                    "session_id": session_id,
                    "provider": exc.provider_id or provider.provider_id,
                    "model": exc.model,
                    "elapsed_ms": elapsed_ms,
                    "error_code": exc.code.value,
                    "history_message_count": len(history),
                    "tools_used_count": len(tools_used),
                    **exc.safe_metadata,
                },
            )
            raise

        try:
            self._conversation_repository.append_successful_turn(
                session_id=session_id,
                user_content=message,
                assistant_content=provider_response.output,
                correlation_id=correlation_id,
                create_session=create_session,
            )
        except (ConversationPersistenceError, ConversationSessionNotFoundError) as exc:
            elapsed_ms = round((perf_counter() - started_at) * 1000, 3)
            logger.warning(
                "chat_persistence_failed",
                extra={
                    "correlation_id": correlation_id,
                    "session_id": session_id,
                    "provider": provider.provider_id,
                    "model": provider_response.model,
                    "elapsed_ms": elapsed_ms,
                    "error_code": exc.code.value,
                    "history_message_count": len(history),
                    "tools_used_count": len(tools_used),
                },
            )
            raise

        elapsed_ms = round((perf_counter() - started_at) * 1000, 3)
        logger.info(
            "chat_request_succeeded",
            extra={
                "correlation_id": correlation_id,
                "session_id": session_id,
                "provider": provider.provider_id,
                "model": provider_response.model,
                "elapsed_ms": elapsed_ms,
                "history_message_count": len(history),
                "tools_used_count": len(tools_used),
            },
        )
        return ChatResult(
            message=provider_response.output,
            provider=provider.provider_id,
            model=provider_response.model,
            correlation_id=correlation_id,
            session_id=session_id,
            tools_used=tools_used,
        )

    async def _execute_routed_tool(
        self,
        *,
        route: ChatToolRoute,
        correlation_id: str,
        session_id: str,
        started_at: float,
    ) -> ProviderMessage:
        if self._tool_registry is None or self._tool_execution_coordinator is None:
            raise ToolExecutionError(
                ToolErrorCode.INTERNAL_ERROR,
                "Chat tool execution is not configured.",
                tool_name=route.tool_name,
                correlation_id=correlation_id,
            )
        if route.tool_name not in supported_chat_tool_names():
            raise ToolExecutionError(
                ToolErrorCode.DENIED,
                "Tool is not allowed from chat.",
                tool_name=route.tool_name,
                correlation_id=correlation_id,
            )

        descriptor = self._tool_registry.descriptor(route.tool_name)
        logger.info(
            "chat_tool_route_matched",
            extra={
                "correlation_id": correlation_id,
                "session_id": session_id,
                "route_matched": True,
                "tool_name": descriptor.name,
                "intent": route.intent.value,
                "side_effect_level": descriptor.side_effect_level.value,
                "execution_boundary": descriptor.execution_boundary.value,
            },
        )

        if (
            descriptor.side_effect_level is not SideEffectLevel.READ
            or descriptor.execution_boundary is not ExecutionBoundary.CORE
        ):
            elapsed_ms = round((perf_counter() - started_at) * 1000, 3)
            logger.warning(
                "chat_tool_route_rejected",
                extra={
                    "correlation_id": correlation_id,
                    "session_id": session_id,
                    "tool_name": descriptor.name,
                    "intent": route.intent.value,
                    "side_effect_level": descriptor.side_effect_level.value,
                    "execution_boundary": descriptor.execution_boundary.value,
                    "error_code": ToolErrorCode.DENIED.value,
                    "elapsed_ms": elapsed_ms,
                },
            )
            raise ToolExecutionError(
                ToolErrorCode.DENIED,
                "Tool is not allowed from chat.",
                tool_name=descriptor.name,
                correlation_id=correlation_id,
            )

        try:
            outcome = await self._tool_execution_coordinator.execute(
                ToolRequest(
                    tool_name=descriptor.name,
                    arguments={},
                    correlation_id=correlation_id,
                )
            )
        except ToolExecutionError as exc:
            elapsed_ms = round((perf_counter() - started_at) * 1000, 3)
            logger.warning(
                "chat_tool_route_failed",
                extra={
                    "correlation_id": exc.correlation_id or correlation_id,
                    "session_id": session_id,
                    "tool_name": exc.tool_name or descriptor.name,
                    "intent": route.intent.value,
                    "sentinel_decision": None,
                    "side_effect_level": descriptor.side_effect_level.value,
                    "execution_boundary": descriptor.execution_boundary.value,
                    "error_code": exc.code.value,
                    "elapsed_ms": elapsed_ms,
                    **exc.safe_metadata,
                },
            )
            raise
        if not outcome.result.success:
            raise ToolExecutionError(
                ToolErrorCode.EXECUTION_FAILED,
                "Tool execution failed.",
                tool_name=descriptor.name,
                correlation_id=correlation_id,
            )

        elapsed_ms = round((perf_counter() - started_at) * 1000, 3)
        logger.info(
            "chat_tool_route_succeeded",
            extra={
                "correlation_id": correlation_id,
                "session_id": session_id,
                "tool_name": outcome.tool_name,
                "intent": route.intent.value,
                "sentinel_decision": outcome.sentinel_decision.action.value,
                "side_effect_level": descriptor.side_effect_level.value,
                "execution_boundary": descriptor.execution_boundary.value,
                "elapsed_ms": elapsed_ms,
            },
        )
        return build_trusted_tool_context_message(
            tool_name=outcome.tool_name,
            correlation_id=correlation_id,
            data=outcome.result.data,
        )

    def _build_provider_messages(
        self,
        current_message: str,
        history: list[ConversationMessage],
        trusted_tool_context: ProviderMessage | None = None,
    ) -> list[ProviderMessage]:
        messages = [
            ProviderMessage(
                role=ProviderMessageRole.SYSTEM,
                content=resolve_system_instruction(self._settings.system_instruction),
            )
        ]
        messages.extend(
            ProviderMessage(
                role=_PROVIDER_ROLE_BY_CONVERSATION_ROLE[history_message.role],
                content=history_message.content,
            )
            for history_message in history
        )
        if trusted_tool_context is not None:
            messages.append(trusted_tool_context)
        messages.append(ProviderMessage(role=ProviderMessageRole.USER, content=current_message))
        return messages

    @asynccontextmanager
    async def _session_lock(self, session_id: str) -> AsyncIterator[None]:
        entry = await self._reserve_session_lock(session_id)
        acquired = False
        try:
            await entry.lock.acquire()
            acquired = True
            yield
        finally:
            if acquired:
                entry.lock.release()
            await asyncio.shield(self._release_session_lock(session_id, entry))

    async def _reserve_session_lock(self, session_id: str) -> _SessionLockEntry:
        async with self._session_locks_guard:
            entry = self._session_locks.get(session_id)
            if entry is None:
                entry = _SessionLockEntry(lock=asyncio.Lock())
                self._session_locks[session_id] = entry
            entry.references += 1
            return entry

    async def _release_session_lock(
        self,
        session_id: str,
        entry: _SessionLockEntry,
    ) -> None:
        async with self._session_locks_guard:
            entry.references -= 1
            if entry.references == 0 and self._session_locks.get(session_id) is entry:
                del self._session_locks[session_id]
