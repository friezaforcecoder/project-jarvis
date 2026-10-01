"""Focused tests for Sentinel approval contracts and binding service."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone, tzinfo

import pytest
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from jarvis_core.sentinel.approval import (
    APPROVAL_LIFETIME,
    ToolApprovalBindingError,
    ToolApprovalBindingService,
    ToolApprovalCanonicalizationError,
    ToolApprovalAlreadyConsumedError,
    ToolApprovalError,
    ToolApprovalExpiredError,
    ToolApprovalMismatchError,
    ToolApprovalNotFoundError,
    ToolApprovalPersistenceError,
    ToolApprovalRecord,
    ToolApprovalStatus,
)
from jarvis_core.tools.contracts import ExecutionBoundary, SideEffectLevel


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


class _TestArgs(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1)
    count: int = 0


class _TestArgsReordered(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    count: int = 0
    name: str = Field(min_length=1)


def _make_record(
    status: ToolApprovalStatus = ToolApprovalStatus.PENDING,
    binding: str | None = None,
) -> ToolApprovalRecord:
    created = datetime(2025, 1, 1, tzinfo=timezone.utc)
    return ToolApprovalRecord(
        approval_id=uuid.uuid4(),
        request_binding=binding or "a" * 64,
        status=status,
        created_at=created,
        expires_at=created + APPROVAL_LIFETIME,
        approved_at=created + timedelta(seconds=1) if status is not ToolApprovalStatus.PENDING else None,
        consumed_at=created + timedelta(seconds=2) if status is ToolApprovalStatus.CONSUMED else None,
    )


class _OffsetlessTZ(tzinfo):
    """A tzinfo whose utcoffset returns None, simulating an invalid offset."""

    def utcoffset(self, dt):
        return None

    def dst(self, dt):
        return None

    def tzname(self, dt):
        return "offsetless"


# ---------------------------------------------------------------------------
# Contract invariants
# ---------------------------------------------------------------------------


class TestToolApprovalRecordContract:
    def test_frozen(self) -> None:
        record = _make_record()
        with pytest.raises(ValidationError):
            record.approval_id = uuid.uuid4()  # type: ignore[misc]

    def test_extra_forbidden(self) -> None:
        with pytest.raises(ValidationError):
            ToolApprovalRecord(
                approval_id=uuid.uuid4(),
                request_binding="a" * 64,
                status=ToolApprovalStatus.PENDING,
                created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
                expires_at=datetime(2025, 1, 1, tzinfo=timezone.utc) + APPROVAL_LIFETIME,
                extra_field="x",  # type: ignore[call-arg]
            )

    def test_binding_must_be_64_lowercase_hex(self) -> None:
        with pytest.raises(ValidationError):
            _make_record(binding="A" * 64)  # uppercase
        with pytest.raises(ValidationError):
            _make_record(binding="a" * 63)  # too short
        with pytest.raises(ValidationError):
            _make_record(binding="a" * 65)  # too long
        with pytest.raises(ValidationError):
            _make_record(binding="g" * 64)  # invalid char

    def test_pending_requires_no_approved_or_consumed(self) -> None:
        created = datetime(2025, 1, 1, tzinfo=timezone.utc)
        with pytest.raises(ValidationError):
            ToolApprovalRecord(
                approval_id=uuid.uuid4(),
                request_binding="a" * 64,
                status=ToolApprovalStatus.PENDING,
                created_at=created,
                expires_at=created + APPROVAL_LIFETIME,
                approved_at=created,
            )

    def test_approved_requires_approved_at(self) -> None:
        created = datetime(2025, 1, 1, tzinfo=timezone.utc)
        with pytest.raises(ValidationError):
            ToolApprovalRecord(
                approval_id=uuid.uuid4(),
                request_binding="a" * 64,
                status=ToolApprovalStatus.APPROVED,
                created_at=created,
                expires_at=created + APPROVAL_LIFETIME,
                approved_at=None,
            )

    def test_consumed_requires_both_timestamps(self) -> None:
        created = datetime(2025, 1, 1, tzinfo=timezone.utc)
        with pytest.raises(ValidationError):
            ToolApprovalRecord(
                approval_id=uuid.uuid4(),
                request_binding="a" * 64,
                status=ToolApprovalStatus.CONSUMED,
                created_at=created,
                expires_at=created + APPROVAL_LIFETIME,
                approved_at=created,
                consumed_at=None,
            )

    def test_expires_must_be_after_created(self) -> None:
        created = datetime(2025, 1, 1, tzinfo=timezone.utc)
        with pytest.raises(ValidationError):
            ToolApprovalRecord(
                approval_id=uuid.uuid4(),
                request_binding="a" * 64,
                status=ToolApprovalStatus.PENDING,
                created_at=created,
                expires_at=created,
            )

    def test_naive_timestamp_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ToolApprovalRecord(
                approval_id=uuid.uuid4(),
                request_binding="a" * 64,
                status=ToolApprovalStatus.PENDING,
                created_at=datetime(2025, 1, 1),
                expires_at=datetime(2025, 1, 1, tzinfo=timezone.utc) + APPROVAL_LIFETIME,
            )

    def test_offsetless_tzinfo_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ToolApprovalRecord(
                approval_id=uuid.uuid4(),
                request_binding="a" * 64,
                status=ToolApprovalStatus.PENDING,
                created_at=datetime(2025, 1, 1, tzinfo=_OffsetlessTZ()),
                expires_at=datetime(2025, 1, 1, tzinfo=timezone.utc) + APPROVAL_LIFETIME,
            )

    def test_utc_normalization(self) -> None:
        """Timestamps in non-UTC timezones are normalized to UTC."""
        created = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone(timedelta(hours=5)))
        record = ToolApprovalRecord(
            approval_id=uuid.uuid4(),
            request_binding="a" * 64,
            status=ToolApprovalStatus.PENDING,
            created_at=created,
            expires_at=created + APPROVAL_LIFETIME,
        )
        assert record.created_at.tzinfo is not None
        assert record.created_at.utcoffset() == timedelta(0)
        assert record.created_at == datetime(2025, 1, 1, 7, 0, 0, tzinfo=timezone.utc)

    def test_approved_after_expiry_rejected(self) -> None:
        created = datetime(2025, 1, 1, tzinfo=timezone.utc)
        expires = created + APPROVAL_LIFETIME
        with pytest.raises(ValidationError):
            ToolApprovalRecord(
                approval_id=uuid.uuid4(),
                request_binding="a" * 64,
                status=ToolApprovalStatus.APPROVED,
                created_at=created,
                expires_at=expires,
                approved_at=expires + timedelta(seconds=1),
            )

    def test_consumed_after_expiry_rejected(self) -> None:
        created = datetime(2025, 1, 1, tzinfo=timezone.utc)
        expires = created + APPROVAL_LIFETIME
        with pytest.raises(ValidationError):
            ToolApprovalRecord(
                approval_id=uuid.uuid4(),
                request_binding="a" * 64,
                status=ToolApprovalStatus.CONSUMED,
                created_at=created,
                expires_at=expires,
                approved_at=created + timedelta(seconds=1),
                consumed_at=expires + timedelta(seconds=1),
            )

    def test_consumed_rejects_approval_before_creation(self) -> None:
        created = datetime(2025, 1, 1, tzinfo=timezone.utc)
        with pytest.raises(ValidationError):
            ToolApprovalRecord(
                approval_id=uuid.uuid4(),
                request_binding="a" * 64,
                status=ToolApprovalStatus.CONSUMED,
                created_at=created,
                expires_at=created + APPROVAL_LIFETIME,
                approved_at=created - timedelta(seconds=1),
                consumed_at=created,
            )


# ---------------------------------------------------------------------------
# Binding service
# ---------------------------------------------------------------------------


class TestToolApprovalBindingService:
    def test_default_key_requests_32_random_bytes(self, monkeypatch) -> None:
        calls: list[int] = []

        def fake_token_bytes(length: int) -> bytes:
            calls.append(length)
            return b"r" * length

        monkeypatch.setattr(
            "jarvis_core.sentinel.approval.secrets.token_bytes",
            fake_token_bytes,
        )
        generated = ToolApprovalBindingService()
        injected = ToolApprovalBindingService(key=b"r" * 32)
        args = _TestArgs(name="alpha", count=1)
        request = {
            "correlation_id": "corr-1",
            "tool_name": "test.tool",
            "side_effect_level": SideEffectLevel.WRITE,
            "execution_boundary": ExecutionBoundary.CORE,
            "arguments": args,
        }

        assert calls == [32]
        assert generated.compute_binding(**request) == injected.compute_binding(**request)

    def test_injected_key_respected(self) -> None:
        key = b"\x01" * 32
        first = ToolApprovalBindingService(key=key)
        second = ToolApprovalBindingService(key=key)
        args = _TestArgs(name="alpha", count=1)

        assert first.compute_binding(
            correlation_id="corr-1",
            tool_name="test.tool",
            side_effect_level=SideEffectLevel.WRITE,
            execution_boundary=ExecutionBoundary.CORE,
            arguments=args,
        ) == second.compute_binding(
            correlation_id="corr-1",
            tool_name="test.tool",
            side_effect_level=SideEffectLevel.WRITE,
            execution_boundary=ExecutionBoundary.CORE,
            arguments=args,
        )

    def test_invalid_key_length_too_short(self) -> None:
        with pytest.raises(ToolApprovalBindingError):
            ToolApprovalBindingService(key=b"\x01" * 16)

    def test_invalid_key_length_too_long(self) -> None:
        with pytest.raises(ToolApprovalBindingError):
            ToolApprovalBindingService(key=b"\x01" * 33)

    def test_invalid_key_length_zero(self) -> None:
        with pytest.raises(ToolApprovalBindingError):
            ToolApprovalBindingService(key=b"")

    def test_deterministic_within_process(self) -> None:
        service = ToolApprovalBindingService(key=b"k" * 32)
        args = _TestArgs(name="alpha", count=1)
        b1 = service.compute_binding(
            correlation_id="corr-1",
            tool_name="test.tool",
            side_effect_level=SideEffectLevel.WRITE,
            execution_boundary=ExecutionBoundary.CORE,
            arguments=args,
        )
        b2 = service.compute_binding(
            correlation_id="corr-1",
            tool_name="test.tool",
            side_effect_level=SideEffectLevel.WRITE,
            execution_boundary=ExecutionBoundary.CORE,
            arguments=args,
        )
        assert b1 == b2
        assert len(b1) == 64
        assert b1 == b1.lower()

    def test_correlation_id_mismatch(self) -> None:
        service = ToolApprovalBindingService(key=b"k" * 32)
        args = _TestArgs(name="alpha", count=1)
        base = dict(
            tool_name="test.tool",
            side_effect_level=SideEffectLevel.WRITE,
            execution_boundary=ExecutionBoundary.CORE,
            arguments=args,
        )
        b1 = service.compute_binding(correlation_id="a", **base)
        b2 = service.compute_binding(correlation_id="b", **base)
        assert b1 != b2

    def test_tool_name_mismatch(self) -> None:
        service = ToolApprovalBindingService(key=b"k" * 32)
        args = _TestArgs(name="alpha", count=1)
        base = dict(
            correlation_id="corr-1",
            side_effect_level=SideEffectLevel.WRITE,
            execution_boundary=ExecutionBoundary.CORE,
            arguments=args,
        )
        b1 = service.compute_binding(tool_name="tool.a", **base)
        b2 = service.compute_binding(tool_name="tool.b", **base)
        assert b1 != b2

    def test_side_effect_level_mismatch(self) -> None:
        service = ToolApprovalBindingService(key=b"k" * 32)
        args = _TestArgs(name="alpha", count=1)
        base = dict(
            correlation_id="corr-1",
            tool_name="test.tool",
            execution_boundary=ExecutionBoundary.CORE,
            arguments=args,
        )
        b1 = service.compute_binding(side_effect_level=SideEffectLevel.READ, **base)
        b2 = service.compute_binding(side_effect_level=SideEffectLevel.WRITE, **base)
        assert b1 != b2

    def test_execution_boundary_mismatch(self) -> None:
        service = ToolApprovalBindingService(key=b"k" * 32)
        args = _TestArgs(name="alpha", count=1)
        base = dict(
            correlation_id="corr-1",
            tool_name="test.tool",
            side_effect_level=SideEffectLevel.WRITE,
            arguments=args,
        )
        b1 = service.compute_binding(execution_boundary=ExecutionBoundary.CORE, **base)
        b2 = service.compute_binding(execution_boundary=ExecutionBoundary.EXTERNAL_SERVICE, **base)
        assert b1 != b2

    def test_argument_value_mismatch(self) -> None:
        service = ToolApprovalBindingService(key=b"k" * 32)
        base = dict(
            correlation_id="corr-1",
            tool_name="test.tool",
            side_effect_level=SideEffectLevel.WRITE,
            execution_boundary=ExecutionBoundary.CORE,
        )
        b1 = service.compute_binding(arguments=_TestArgs(name="alpha", count=1), **base)
        b2 = service.compute_binding(arguments=_TestArgs(name="alpha", count=2), **base)
        assert b1 != b2

    def test_dictionary_key_order_normalization(self) -> None:
        """Two models with equal values but different field declaration order produce identical bindings."""
        service = ToolApprovalBindingService(key=b"k" * 32)
        args_a = _TestArgs(name="alpha", count=1)
        args_b = _TestArgsReordered(name="alpha", count=1)
        b1 = service.compute_binding(
            correlation_id="corr-1",
            tool_name="test.tool",
            side_effect_level=SideEffectLevel.WRITE,
            execution_boundary=ExecutionBoundary.CORE,
            arguments=args_a,
        )
        b2 = service.compute_binding(
            correlation_id="corr-1",
            tool_name="test.tool",
            side_effect_level=SideEffectLevel.WRITE,
            execution_boundary=ExecutionBoundary.CORE,
            arguments=args_b,
        )
        assert b1 == b2

    def test_different_process_keys_produce_different_bindings(self) -> None:
        service_a = ToolApprovalBindingService(key=b"a" * 32)
        service_b = ToolApprovalBindingService(key=b"b" * 32)
        args = _TestArgs(name="alpha", count=1)
        base = dict(
            correlation_id="corr-1",
            tool_name="test.tool",
            side_effect_level=SideEffectLevel.WRITE,
            execution_boundary=ExecutionBoundary.CORE,
            arguments=args,
        )
        assert service_a.compute_binding(**base) != service_b.compute_binding(**base)

    def test_non_finite_float_rejected(self) -> None:
        class _BadArgs(BaseModel):
            model_config = ConfigDict(frozen=True, extra="forbid")
            value: float

        service = ToolApprovalBindingService(key=b"k" * 32)
        with pytest.raises(ToolApprovalCanonicalizationError):
            service.compute_binding(
                correlation_id="corr-1",
                tool_name="test.tool",
                side_effect_level=SideEffectLevel.WRITE,
                execution_boundary=ExecutionBoundary.CORE,
                arguments=_BadArgs(value=float("nan")),
            )

    def test_positive_infinity_rejected(self) -> None:
        class _BadArgs(BaseModel):
            model_config = ConfigDict(frozen=True, extra="forbid")
            value: float

        service = ToolApprovalBindingService(key=b"k" * 32)
        with pytest.raises(ToolApprovalCanonicalizationError):
            service.compute_binding(
                correlation_id="corr-1",
                tool_name="test.tool",
                side_effect_level=SideEffectLevel.WRITE,
                execution_boundary=ExecutionBoundary.CORE,
                arguments=_BadArgs(value=float("inf")),
            )

    def test_negative_infinity_rejected(self) -> None:
        class _BadArgs(BaseModel):
            model_config = ConfigDict(frozen=True, extra="forbid")
            value: float

        service = ToolApprovalBindingService(key=b"k" * 32)
        with pytest.raises(ToolApprovalCanonicalizationError):
            service.compute_binding(
                correlation_id="corr-1",
                tool_name="test.tool",
                side_effect_level=SideEffectLevel.WRITE,
                execution_boundary=ExecutionBoundary.CORE,
                arguments=_BadArgs(value=float("-inf")),
            )

    def test_raw_argument_values_absent_from_digest(self) -> None:
        """The 64-char hex digest must not contain the raw argument string."""
        service = ToolApprovalBindingService(key=b"k" * 32)
        secret_value = "synthetic-secret-xyz-12345"
        args = _TestArgs(name=secret_value, count=99)
        binding = service.compute_binding(
            correlation_id="corr-1",
            tool_name="test.tool",
            side_effect_level=SideEffectLevel.WRITE,
            execution_boundary=ExecutionBoundary.CORE,
            arguments=args,
        )
        assert secret_value not in binding

    def test_record_has_exactly_seven_fields_and_no_raw_secret(self) -> None:
        """A record stores only the binding digest, not raw arguments."""
        service = ToolApprovalBindingService(key=b"k" * 32)
        secret_value = "synthetic-secret-xyz-12345"
        args = _TestArgs(name=secret_value, count=99)
        binding = service.compute_binding(
            correlation_id="corr-1",
            tool_name="test.tool",
            side_effect_level=SideEffectLevel.WRITE,
            execution_boundary=ExecutionBoundary.CORE,
            arguments=args,
        )
        record = _make_record(binding=binding)
        dumped = record.model_dump(mode="json")
        expected_fields = {
            "approval_id",
            "request_binding",
            "status",
            "created_at",
            "expires_at",
            "approved_at",
            "consumed_at",
        }
        assert set(dumped.keys()) == expected_fields
        assert secret_value not in str(dumped)

    def test_compare_bindings_equal(self) -> None:
        service = ToolApprovalBindingService(key=b"k" * 32)
        assert service.compare_bindings("a" * 64, "a" * 64) is True

    def test_compare_bindings_unequal(self) -> None:
        service = ToolApprovalBindingService(key=b"k" * 32)
        assert service.compare_bindings("a" * 64, "b" * 64) is False

    def test_compare_bindings_wrong_length(self) -> None:
        service = ToolApprovalBindingService(key=b"k" * 32)
        assert service.compare_bindings("a" * 63, "a" * 63) is False
        assert service.compare_bindings("a" * 65, "a" * 65) is False

    def test_compare_bindings_non_lowercase_hex(self) -> None:
        service = ToolApprovalBindingService(key=b"k" * 32)
        assert service.compare_bindings("A" * 64, "A" * 64) is False
        assert service.compare_bindings("a" * 63 + "g", "a" * 63 + "g") is False

    def test_compare_bindings_non_ascii(self) -> None:
        service = ToolApprovalBindingService(key=b"k" * 32)
        assert service.compare_bindings("a" * 63 + "\u00e9", "a" * 63 + "\u00e9") is False


# ---------------------------------------------------------------------------
# Safe error messages
# ---------------------------------------------------------------------------


class TestSafeErrorMessages:
    def test_base_error_safe_message(self) -> None:
        err = ToolApprovalError()
        assert err.safe_message == "Tool approval operation failed."
        assert str(err) == "Tool approval operation failed."

    def test_binding_error_safe_message(self) -> None:
        err = ToolApprovalBindingError()
        assert err.safe_message == "Tool approval binding computation failed."
        assert str(err) == "Tool approval binding computation failed."

    def test_canonicalization_error_safe_message(self) -> None:
        err = ToolApprovalCanonicalizationError()
        assert err.safe_message == "Tool approval arguments cannot be canonically serialized."
        assert str(err) == "Tool approval arguments cannot be canonically serialized."

    def test_not_found_error_safe_message(self) -> None:
        err = ToolApprovalNotFoundError()
        assert err.safe_message == "Tool approval receipt not found."
        assert str(err) == "Tool approval receipt not found."

    def test_already_consumed_error_safe_message(self) -> None:
        err = ToolApprovalAlreadyConsumedError()
        assert err.safe_message == "Tool approval receipt already consumed."
        assert str(err) == "Tool approval receipt already consumed."

    def test_expired_error_safe_message(self) -> None:
        err = ToolApprovalExpiredError()
        assert err.safe_message == "Tool approval receipt has expired."
        assert str(err) == "Tool approval receipt has expired."

    def test_mismatch_error_safe_message(self) -> None:
        err = ToolApprovalMismatchError()
        assert err.safe_message == "Tool approval request binding mismatch."
        assert str(err) == "Tool approval request binding mismatch."

    def test_persistence_error_safe_message(self) -> None:
        err = ToolApprovalPersistenceError()
        assert err.safe_message == "Tool approval persistence failed."
        assert str(err) == "Tool approval persistence failed."
