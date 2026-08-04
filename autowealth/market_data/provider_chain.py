"""Deterministic, side-effect-free fallback orchestration for EOD providers."""

from __future__ import annotations

from dataclasses import dataclass, replace
import inspect
import json
import re
from typing import Optional, Tuple

from autowealth.security import contains_absolute_path, contains_sensitive_value

from .providers import (
    EODProvider,
    EODProviderCapability,
    EODProviderError,
    EODProviderErrorCode,
    EODProviderRequest,
    EODProviderResult,
    EODProviderResultStatus,
    validate_eod_provider_request,
)
from .schemas import EODDateRange

_MAX_EOD_PROVIDER_ATTEMPTS = 32
_MACHINE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_VERSION_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,255}$")
_WARNING_CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,127}$")

_RESULT_STATUS_NAMES = {
    EODProviderResultStatus.SUCCESS: "success",
    EODProviderResultStatus.PARTIAL_SUCCESS: "partial",
    EODProviderResultStatus.EMPTY: "empty",
}
_ERROR_STATUS_NAMES = {
    EODProviderErrorCode.UNSUPPORTED_REQUEST: "unsupported",
    EODProviderErrorCode.PROVIDER_UNAVAILABLE: "unavailable",
    EODProviderErrorCode.TEMPORARY_PROVIDER_FAILURE: "temporary_failure",
    EODProviderErrorCode.PERMANENT_PROVIDER_FAILURE: "permanent_failure",
    EODProviderErrorCode.MALFORMED_PROVIDER_PAYLOAD: "malformed",
}
_FINAL_MESSAGES = {
    EODProviderErrorCode.UNSUPPORTED_REQUEST: ("No EOD provider supports the requested dataset."),
    EODProviderErrorCode.PROVIDER_UNAVAILABLE: (
        "No EOD provider returned usable data for the request."
    ),
    EODProviderErrorCode.TEMPORARY_PROVIDER_FAILURE: (
        "The EOD provider chain encountered a temporary failure."
    ),
    EODProviderErrorCode.PERMANENT_PROVIDER_FAILURE: (
        "The EOD provider chain encountered a permanent provider failure."
    ),
    EODProviderErrorCode.MALFORMED_PROVIDER_PAYLOAD: (
        "The EOD provider chain rejected malformed provider data."
    ),
}


def _json_text(payload: dict[str, object]) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _safe_identifier(value: object, field_name: str, pattern: re.Pattern[str]) -> str:
    if type(value) is not str or pattern.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be a safe stable identifier")
    if contains_absolute_path(value) or contains_sensitive_value(value):
        raise ValueError(f"{field_name} must not contain paths or credentials")
    return value


def _safe_message(value: object) -> str:
    if type(value) is not str or not value or len(value) > 512:
        raise ValueError("safe_message must be non-empty text of at most 512 characters")
    if "Traceback (most recent call last)" in value:
        raise ValueError("safe_message must not contain traceback text")
    if contains_absolute_path(value) or contains_sensitive_value(value):
        raise ValueError("safe_message must not contain paths or credentials")
    return value


def _warning_codes(result: EODProviderResult) -> Tuple[str, ...]:
    return tuple(sorted({warning.code for warning in result.warnings}))


@dataclass(frozen=True)
class EODProviderAttempt:
    """Immutable, bounded diagnostics for one provider evaluation."""

    position: int
    provider_name: str
    provider_version: str
    endpoint_name: Optional[str]
    result_status: Optional[EODProviderResultStatus]
    error_code: Optional[EODProviderErrorCode]
    row_count: int
    effective_range: Optional[EODDateRange]
    warning_codes: Tuple[str, ...]
    selected: bool
    safe_message: str

    def __post_init__(self) -> None:
        if type(self.position) is not int or self.position < 0:
            raise ValueError("position must be a non-negative exact integer")
        provider_name = _safe_identifier(
            self.provider_name,
            "provider_name",
            _MACHINE_NAME_PATTERN,
        )
        provider_version = _safe_identifier(
            self.provider_version,
            "provider_version",
            _VERSION_PATTERN,
        )
        endpoint_name = self.endpoint_name
        if endpoint_name is not None:
            endpoint_name = _safe_identifier(
                endpoint_name,
                "endpoint_name",
                _MACHINE_NAME_PATTERN,
            )
        has_result = type(self.result_status) is EODProviderResultStatus
        has_error = type(self.error_code) is EODProviderErrorCode
        if has_result == has_error:
            raise ValueError("exactly one of result_status and error_code must be provided")
        if type(self.row_count) is not int or self.row_count < 0:
            raise ValueError("row_count must be a non-negative exact integer")
        if self.effective_range is not None and type(self.effective_range) is not EODDateRange:
            raise TypeError("effective_range must be an exact EODDateRange or None")
        if type(self.warning_codes) not in (list, tuple):
            raise TypeError("warning_codes must be an exact list or exact tuple")
        warning_codes = tuple(self.warning_codes)
        if any(
            type(code) is not str or _WARNING_CODE_PATTERN.fullmatch(code) is None
            for code in warning_codes
        ):
            raise ValueError("warning_codes must contain safe machine identifiers")
        warning_codes = tuple(sorted(set(warning_codes)))
        if type(self.selected) is not bool:
            raise ValueError("selected must be a strict boolean")

        if has_result:
            if self.result_status is EODProviderResultStatus.EMPTY:
                if self.row_count != 0 or self.effective_range is not None:
                    raise ValueError("an empty attempt cannot contain rows or an effective range")
                if self.selected:
                    raise ValueError("an empty attempt cannot be selected")
            elif self.row_count <= 0 or self.effective_range is None:
                raise ValueError("a non-empty result attempt requires rows and an effective range")
        else:
            if self.row_count != 0 or self.effective_range is not None:
                raise ValueError("an error attempt cannot contain rows or an effective range")
            if warning_codes:
                raise ValueError("an error attempt cannot contain warning codes")
            if self.selected:
                raise ValueError("an error attempt cannot be selected")

        object.__setattr__(self, "provider_name", provider_name)
        object.__setattr__(self, "provider_version", provider_version)
        object.__setattr__(self, "endpoint_name", endpoint_name)
        object.__setattr__(self, "warning_codes", warning_codes)
        object.__setattr__(self, "safe_message", _safe_message(self.safe_message))

    @property
    def role(self) -> str:
        """Return the stable primary or fallback role."""

        return "primary" if self.position == 0 else "fallback"

    @property
    def status(self) -> str:
        """Return one finite flattened attempt status."""

        if self.result_status is not None:
            return _RESULT_STATUS_NAMES[self.result_status]
        if self.error_code is None:  # pragma: no cover - guarded by construction.
            raise RuntimeError("attempt status is unavailable")
        return _ERROR_STATUS_NAMES[self.error_code]

    @property
    def reason_code(self) -> str:
        """Return the underlying provider result or error code."""

        if self.result_status is not None:
            return self.result_status.value
        if self.error_code is None:  # pragma: no cover - guarded by construction.
            raise RuntimeError("attempt reason code is unavailable")
        return self.error_code.value

    @property
    def retryable(self) -> bool:
        """Return whether a later retry layer may repeat this provider."""

        return self.error_code is EODProviderErrorCode.TEMPORARY_PROVIDER_FAILURE

    def to_dict(self) -> dict[str, object]:
        """Return deterministic JSON-safe attempt diagnostics."""

        return {
            "position": self.position,
            "role": self.role,
            "provider_name": self.provider_name,
            "provider_version": self.provider_version,
            "endpoint_name": self.endpoint_name,
            "status": self.status,
            "result_status": (None if self.result_status is None else self.result_status.value),
            "error_code": None if self.error_code is None else self.error_code.value,
            "retryable": self.retryable,
            "row_count": self.row_count,
            "effective_range": (
                None if self.effective_range is None else self.effective_range.to_dict()
            ),
            "warning_codes": list(self.warning_codes),
            "selected": self.selected,
            "reason_code": self.reason_code,
            "safe_message": self.safe_message,
        }

    def to_json(self) -> str:
        """Serialize attempt diagnostics deterministically."""

        return _json_text(self.to_dict())


@dataclass(frozen=True)
class EODProviderChainResult:
    """One selected complete or partial provider result plus all attempts."""

    request: EODProviderRequest
    selected_result: EODProviderResult
    selected_position: int
    attempts: Tuple[EODProviderAttempt, ...]

    def __post_init__(self) -> None:
        if type(self.request) is not EODProviderRequest:
            raise TypeError("request must be an exact EODProviderRequest")
        if type(self.selected_result) is not EODProviderResult:
            raise TypeError("selected_result must be an exact EODProviderResult")
        if self.selected_result.request != self.request:
            raise ValueError("selected_result request must match the chain request")
        if self.selected_result.status not in (
            EODProviderResultStatus.SUCCESS,
            EODProviderResultStatus.PARTIAL_SUCCESS,
        ):
            raise ValueError("selected_result must be successful or partial")
        if type(self.selected_position) is not int or self.selected_position < 0:
            raise ValueError("selected_position must be a non-negative exact integer")
        if type(self.attempts) not in (list, tuple):
            raise TypeError("attempts must be an exact list or exact tuple")
        attempts = tuple(self.attempts)
        if not attempts:
            raise ValueError("attempts cannot be empty")
        if len(attempts) > _MAX_EOD_PROVIDER_ATTEMPTS:
            raise ValueError("attempts exceed the provider chain limit")
        if any(type(attempt) is not EODProviderAttempt for attempt in attempts):
            raise TypeError("attempts must contain exact EODProviderAttempt values")
        if tuple(attempt.position for attempt in attempts) != tuple(range(len(attempts))):
            raise ValueError("attempt positions must be contiguous from zero")
        if self.selected_position >= len(attempts):
            raise ValueError("selected_position must identify an attempt")
        selected_attempts = tuple(attempt for attempt in attempts if attempt.selected)
        if len(selected_attempts) != 1:
            raise ValueError("exactly one attempt must be selected")
        selected_attempt = selected_attempts[0]
        if selected_attempt.position != self.selected_position:
            raise ValueError("selected attempt position does not match selected_position")
        if (
            selected_attempt.provider_name != self.selected_result.provider_name
            or selected_attempt.provider_version != self.selected_result.provider_version
        ):
            raise ValueError("selected attempt provider identity does not match the result")
        if selected_attempt.result_status is not self.selected_result.status:
            raise ValueError("selected attempt status does not match the result")
        if selected_attempt.row_count != len(self.selected_result.bars):
            raise ValueError("selected attempt row_count does not match the result")
        if selected_attempt.effective_range != self.selected_result.effective_range:
            raise ValueError("selected attempt effective_range does not match the result")
        if selected_attempt.warning_codes != _warning_codes(self.selected_result):
            raise ValueError("selected attempt warning_codes do not match the result")
        object.__setattr__(self, "attempts", attempts)

    @property
    def selected_provider_name(self) -> str:
        """Return the selected provider's stable name."""

        return self.selected_result.provider_name

    @property
    def selected_provider_version(self) -> str:
        """Return the selected provider's stable version."""

        return self.selected_result.provider_version

    @property
    def result_status(self) -> EODProviderResultStatus:
        """Return the selected provider result status."""

        return self.selected_result.status

    @property
    def is_complete(self) -> bool:
        """Return true only for a complete successful result."""

        return self.selected_result.status is EODProviderResultStatus.SUCCESS

    def to_dict(self) -> dict[str, object]:
        """Return the selected result and all diagnostics as JSON-safe data."""

        return {
            "request": self.request.to_dict(),
            "selected_result": self.selected_result.to_dict(),
            "selected_provider_name": self.selected_provider_name,
            "selected_provider_version": self.selected_provider_version,
            "selected_position": self.selected_position,
            "result_status": self.result_status.value,
            "is_complete": self.is_complete,
            "attempts": [attempt.to_dict() for attempt in self.attempts],
        }

    def to_json(self) -> str:
        """Serialize the chain result deterministically."""

        return _json_text(self.to_dict())


class EODProviderChainError(RuntimeError):
    """Raised after every provider fails to return complete or partial data."""

    def __init__(
        self,
        request: EODProviderRequest,
        attempts: Tuple[EODProviderAttempt, ...],
        final_code: EODProviderErrorCode,
        message: str,
    ) -> None:
        if type(request) is not EODProviderRequest:
            raise TypeError("request must be an exact EODProviderRequest")
        if type(attempts) not in (list, tuple):
            raise TypeError("attempts must be an exact list or exact tuple")
        normalized_attempts = tuple(attempts)
        if not normalized_attempts:
            raise ValueError("attempts cannot be empty")
        if len(normalized_attempts) > _MAX_EOD_PROVIDER_ATTEMPTS:
            raise ValueError("attempts exceed the provider chain limit")
        if any(type(attempt) is not EODProviderAttempt for attempt in normalized_attempts):
            raise TypeError("attempts must contain exact EODProviderAttempt values")
        if any(attempt.selected for attempt in normalized_attempts):
            raise ValueError("failed chain attempts cannot be selected")
        if tuple(attempt.position for attempt in normalized_attempts) != tuple(
            range(len(normalized_attempts))
        ):
            raise ValueError("attempt positions must be contiguous from zero")
        if type(final_code) is not EODProviderErrorCode:
            raise TypeError("final_code must be an exact EODProviderErrorCode")
        safe_message = _safe_message(message)

        self.request = request
        self.attempts = normalized_attempts
        self.final_code = final_code
        self.message = safe_message
        super().__init__(safe_message)

    @property
    def retryable(self) -> bool:
        """Return whether a later retry layer may repeat the whole request."""

        return self.final_code is EODProviderErrorCode.TEMPORARY_PROVIDER_FAILURE

    def to_dict(self) -> dict[str, object]:
        """Return deterministic public error diagnostics without exception causes."""

        return {
            "request": self.request.to_dict(),
            "attempts": [attempt.to_dict() for attempt in self.attempts],
            "final_code": self.final_code.value,
            "message": self.message,
            "retryable": self.retryable,
        }

    def to_json(self) -> str:
        """Serialize the chain error deterministically."""

        return _json_text(self.to_dict())


class EODProviderChain:
    """Try immutable EOD providers once each in their declared order."""

    def __init__(self, providers: Tuple[EODProvider, ...]) -> None:
        if type(providers) not in (list, tuple):
            raise TypeError("providers must be an exact list or exact tuple")
        normalized = tuple(providers)
        if not normalized:
            raise ValueError("provider chain cannot be empty")
        if len(normalized) > _MAX_EOD_PROVIDER_ATTEMPTS:
            raise ValueError("provider chain cannot contain more than 32 providers")

        identities = []
        object_ids = set()
        for provider in normalized:
            if isinstance(provider, EODProviderChain) or not _has_provider_contract(provider):
                raise TypeError("providers must implement the EODProvider contract")
            object_id = id(provider)
            if object_id in object_ids:
                raise ValueError("provider chain cannot contain the same object twice")
            object_ids.add(object_id)
            try:
                provider_name = _safe_identifier(
                    getattr(provider, "provider_name"),
                    "provider_name",
                    _MACHINE_NAME_PATTERN,
                )
                provider_version = _safe_identifier(
                    getattr(provider, "provider_version"),
                    "provider_version",
                    _VERSION_PATTERN,
                )
            except Exception as exc:
                raise TypeError("provider identity must be safe and readable") from exc
            identity = (provider_name, provider_version)
            if identity in identities:
                raise ValueError("provider chain cannot contain duplicate provider identities")
            identities.append(identity)

        self._providers = normalized
        self._provider_identities = tuple(identities)

    def fetch(self, request: EODProviderRequest) -> EODProviderChainResult:
        """Return the first complete result or the deterministic best partial result."""

        if type(request) is not EODProviderRequest:
            raise TypeError("request must be an exact EODProviderRequest")

        attempts = []
        partial_candidates = []
        last_cause: Optional[Exception] = None
        for position, provider in enumerate(self._providers):
            provider_name, provider_version = self._provider_identities[position]
            capability_code, capability_error = _precheck_capabilities(provider, request)
            if capability_code is not None:
                attempts.append(
                    _error_attempt(
                        position,
                        provider_name,
                        provider_version,
                        None,
                        capability_code,
                        (
                            "The EOD provider does not support the requested dataset."
                            if capability_code is EODProviderErrorCode.UNSUPPORTED_REQUEST
                            else "The EOD provider capabilities are malformed."
                        ),
                    )
                )
                if capability_error is not None:
                    last_cause = capability_error
                continue

            endpoint_name, endpoint_error = _read_endpoint_name(provider)
            if endpoint_error is not None:
                attempts.append(
                    _error_attempt(
                        position,
                        provider_name,
                        provider_version,
                        None,
                        EODProviderErrorCode.MALFORMED_PROVIDER_PAYLOAD,
                        "The EOD provider endpoint identity is malformed.",
                    )
                )
                last_cause = endpoint_error
                continue

            try:
                result = provider.fetch(request)
            except EODProviderError as exc:
                attempts.append(
                    _error_attempt(
                        position,
                        provider_name,
                        provider_version,
                        endpoint_name,
                        exc.code,
                        exc.message,
                    )
                )
                last_cause = exc
                continue
            except Exception as exc:
                attempts.append(
                    _error_attempt(
                        position,
                        provider_name,
                        provider_version,
                        endpoint_name,
                        EODProviderErrorCode.PROVIDER_UNAVAILABLE,
                        "The EOD provider is unavailable for this request.",
                    )
                )
                last_cause = exc
                continue

            if not _result_identity_matches(
                result,
                request,
                provider_name,
                provider_version,
            ):
                attempts.append(
                    _error_attempt(
                        position,
                        provider_name,
                        provider_version,
                        endpoint_name,
                        EODProviderErrorCode.MALFORMED_PROVIDER_PAYLOAD,
                        "The EOD provider returned an inconsistent result identity.",
                    )
                )
                continue

            if result.status is EODProviderResultStatus.SUCCESS:
                attempts.append(_result_attempt(position, endpoint_name, result, selected=True))
                return EODProviderChainResult(
                    request=request,
                    selected_result=result,
                    selected_position=position,
                    attempts=tuple(attempts),
                )

            attempts.append(_result_attempt(position, endpoint_name, result, selected=False))
            if result.status is EODProviderResultStatus.PARTIAL_SUCCESS:
                partial_candidates.append((position, result))

        if partial_candidates:
            selected_position, selected_result = max(
                partial_candidates,
                key=lambda item: _partial_rank(item[0], item[1]),
            )
            selected_attempts = tuple(
                replace(attempt, selected=attempt.position == selected_position)
                for attempt in attempts
            )
            return EODProviderChainResult(
                request=request,
                selected_result=selected_result,
                selected_position=selected_position,
                attempts=selected_attempts,
            )

        normalized_attempts = tuple(attempts)
        final_code = _aggregate_final_code(normalized_attempts)
        chain_error = EODProviderChainError(
            request,
            normalized_attempts,
            final_code,
            _FINAL_MESSAGES[final_code],
        )
        if last_cause is not None:
            raise chain_error from last_cause
        raise chain_error


def _has_provider_contract(provider: object) -> bool:
    for attribute in ("provider_name", "provider_version", "capabilities", "fetch"):
        try:
            static_value = inspect.getattr_static(provider, attribute)
        except AttributeError:
            return False
        if attribute == "fetch" and not callable(static_value):
            return False
    return True


def _read_endpoint_name(provider: object) -> tuple[Optional[str], Optional[Exception]]:
    try:
        endpoint_name = getattr(provider, "endpoint_name", None)
        if endpoint_name is None:
            return None, None
        return (
            _safe_identifier(endpoint_name, "endpoint_name", _MACHINE_NAME_PATTERN),
            None,
        )
    except Exception as exc:
        return None, exc


def _precheck_capabilities(
    provider: object,
    request: EODProviderRequest,
) -> tuple[Optional[EODProviderErrorCode], Optional[Exception]]:
    try:
        capabilities = getattr(provider, "capabilities")
        if type(capabilities) not in (list, tuple):
            raise TypeError("provider capabilities must be an exact list or exact tuple")
        normalized = tuple(capabilities)
        if any(type(item) is not EODProviderCapability for item in normalized):
            raise TypeError("provider capabilities contain an invalid entry")
        if len(set(normalized)) != len(normalized):
            raise ValueError("provider capabilities contain duplicate entries")
        matches = tuple(item for item in normalized if item.matches(request.dataset))
        if not matches:
            return EODProviderErrorCode.UNSUPPORTED_REQUEST, None
        if len(matches) != 1:
            raise ValueError("provider capabilities contain ambiguous matches")
        validate_eod_provider_request(request, normalized)
    except EODProviderError as exc:
        return EODProviderErrorCode.MALFORMED_PROVIDER_PAYLOAD, exc
    except Exception as exc:
        return EODProviderErrorCode.MALFORMED_PROVIDER_PAYLOAD, exc
    return None, None


def _result_identity_matches(
    result: object,
    request: EODProviderRequest,
    provider_name: str,
    provider_version: str,
) -> bool:
    return (
        type(result) is EODProviderResult
        and result.request == request
        and result.provider_name == provider_name
        and result.provider_version == provider_version
    )


def _result_attempt(
    position: int,
    endpoint_name: Optional[str],
    result: EODProviderResult,
    *,
    selected: bool,
) -> EODProviderAttempt:
    messages = {
        EODProviderResultStatus.SUCCESS: ("The EOD provider returned a complete validated result."),
        EODProviderResultStatus.PARTIAL_SUCCESS: (
            "The EOD provider returned a partial validated result."
        ),
        EODProviderResultStatus.EMPTY: "The EOD provider returned no rows.",
    }
    return EODProviderAttempt(
        position=position,
        provider_name=result.provider_name,
        provider_version=result.provider_version,
        endpoint_name=endpoint_name,
        result_status=result.status,
        error_code=None,
        row_count=len(result.bars),
        effective_range=result.effective_range,
        warning_codes=_warning_codes(result),
        selected=selected,
        safe_message=messages[result.status],
    )


def _error_attempt(
    position: int,
    provider_name: str,
    provider_version: str,
    endpoint_name: Optional[str],
    error_code: EODProviderErrorCode,
    safe_message: str,
) -> EODProviderAttempt:
    return EODProviderAttempt(
        position=position,
        provider_name=provider_name,
        provider_version=provider_version,
        endpoint_name=endpoint_name,
        result_status=None,
        error_code=error_code,
        row_count=0,
        effective_range=None,
        warning_codes=(),
        selected=False,
        safe_message=safe_message,
    )


def _partial_rank(position: int, result: EODProviderResult) -> tuple[int, int, int, int]:
    effective_range = result.effective_range
    if effective_range is None:  # pragma: no cover - result construction prevents this.
        raise RuntimeError("a partial result must have an effective range")
    return (
        len(result.bars),
        -effective_range.start_date.toordinal(),
        effective_range.end_date.toordinal(),
        -position,
    )


def _aggregate_final_code(
    attempts: Tuple[EODProviderAttempt, ...],
) -> EODProviderErrorCode:
    if attempts and all(
        attempt.error_code is EODProviderErrorCode.UNSUPPORTED_REQUEST for attempt in attempts
    ):
        return EODProviderErrorCode.UNSUPPORTED_REQUEST
    error_codes = {attempt.error_code for attempt in attempts if attempt.error_code is not None}
    for code in (
        EODProviderErrorCode.MALFORMED_PROVIDER_PAYLOAD,
        EODProviderErrorCode.PERMANENT_PROVIDER_FAILURE,
        EODProviderErrorCode.TEMPORARY_PROVIDER_FAILURE,
    ):
        if code in error_codes:
            return code
    return EODProviderErrorCode.PROVIDER_UNAVAILABLE


__all__ = [
    "EODProviderAttempt",
    "EODProviderChain",
    "EODProviderChainError",
    "EODProviderChainResult",
]
