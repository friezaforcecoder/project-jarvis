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
from jarvis_core.intelligence.contracts import (
    IntelligenceProvider,
    ProviderMessage,
    ProviderMessageRole,
    ProviderRequest,
)
from jarvis_core.intelligence.errors import ProviderError, ProviderErrorCode
from jarvis_core.intelligence.registry import ProviderRegistry

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
    ) -> None:
        self._settings = settings
        self._provider_registry = provider_registry
        self._conversation_repository = conversation_repository
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
        provider_request = ProviderRequest(
            messages=self._build_provider_messages(message, history),
            context={"session_id": session_id, "history_message_count": len(history)},
            correlation_id=correlation_id,
        )
        started_at = perf_counter()
        logger.info(
            "chat_request_started",
            extra={
                "correlation_id": correlation_id,
                "session_id": session_id,
                "provider": provider.provider_id,
                "history_message_count": len(history),
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
            },
        )
        return ChatResult(
            message=provider_response.output,
            provider=provider.provider_id,
            model=provider_response.model,
            correlation_id=correlation_id,
            session_id=session_id,
        )

    def _build_provider_messages(
        self,
        current_message: str,
        history: list[ConversationMessage],
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
