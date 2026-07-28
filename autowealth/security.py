"""Shared, deterministic security helpers for public research artifacts."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import PurePosixPath, PureWindowsPath
from typing import Mapping
from urllib.parse import unquote

SAFE_EXCEPTION_SUMMARY_MAX_LENGTH = 256
REDACTED_ABSOLUTE_PATH = "[redacted-absolute-path]"
REDACTED_SENSITIVE_VALUE = "[redacted-sensitive-value]"
REDACTED_HEADERS = "[redacted-headers]"
REDACTED_TRACEBACK = "[redacted-traceback]"
REDACTED_PROVIDER_RESPONSE = "[redacted-provider-response]"
REDACTED_UNSAFE_VALUE = "[redacted-unsafe-value]"


@dataclass(frozen=True)
class PublicSanitizationLimits:
    """Shared defensive limits for recursively publishing old artifact content."""

    max_depth: int = 8
    max_mapping_items: int = 64
    max_sequence_items: int = 64
    max_nodes: int = 4096
    max_string_length: int = 4096
    max_total_string_chars: int = 65536
    max_json_bytes: int = 262144

    def __post_init__(self) -> None:
        for field_name, value in self.__dict__.items():
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{field_name} must be a positive integer")


DEFAULT_PUBLIC_SANITIZATION_LIMITS = PublicSanitizationLimits()


class PublicSanitizationError(ValueError):
    """Raised when untrusted public content exceeds a deterministic safety bound."""


@dataclass
class _PublicSanitizationBudget:
    limits: PublicSanitizationLimits
    nodes: int = 0
    string_chars: int = 0

    def consume_node(self) -> None:
        self.nodes += 1
        if self.nodes > self.limits.max_nodes:
            raise PublicSanitizationError("public payload exceeds the node budget")

    def consume_string(self, value: str) -> None:
        self.consume_node()
        if len(value) > self.limits.max_string_length:
            raise PublicSanitizationError("public payload contains an oversized string")
        self.string_chars += len(value)
        if self.string_chars > self.limits.max_total_string_chars:
            raise PublicSanitizationError("public payload exceeds the cumulative string budget")


_ALLOWED_SECURITY_KEYS = {
    "authorization_status",
    "cookie_policy",
    "password_policy",
    "secret_rotation_status",
    "token_count",
    "token_usage",
}
_SENSITIVE_KEYS = {
    "api_key",
    "api_token",
    "access_token",
    "refresh_token",
    "client_secret",
    "authorization",
    "proxy_authorization",
    "cookie",
    "set_cookie",
    "password",
    "passwd",
    "bearer_token",
    "private_key",
    "secret",
    "token",
    "credential",
    "credentials",
}
_SENSITIVE_KEY_SUFFIXES = (
    "_api_key",
    "_api_token",
    "_access_token",
    "_refresh_token",
    "_client_secret",
    "_authorization",
    "_cookie",
    "_set_cookie",
    "_password",
    "_passwd",
    "_bearer_token",
    "_private_key",
    "_secret",
    "_token",
    "_credential",
    "_credentials",
)
_FORBIDDEN_PAYLOAD_KEYS = {
    "headers",
    "request_headers",
    "response_headers",
    "request_body",
    "raw_response",
    "response_body",
    "provider_response",
    "full_response",
    "payload",
    "raw_payload",
    "traceback",
    "stack_trace",
}
_FORBIDDEN_PAYLOAD_SUFFIXES = tuple(f"_{key}" for key in _FORBIDDEN_PAYLOAD_KEYS)
_EXCEPTION_VALUE_KEYS = {"exception", "exception_message", "raw_exception"}
_EXCEPTION_REASON_CODES = {
    "cache_unreadable",
    "provider_exception",
    "unsupported_endpoint",
}

_HTTP_URL = re.compile(r"(?i)https?://[^\s,;|<>\"')\]}]+")
_FILE_URI = re.compile(r"(?i)file://[^\s,;|<>\"']+")
_QUOTED_ABSOLUTE_PATH = re.compile(
    r"(?P<quote>[\"'])"
    r"(?P<path>"
    r"(?:[A-Za-z]:[\\/]|\\\\[^\\/\r\n\"']+[\\/]|/(?![/\s]))"
    r"[^\"'\r\n]*"
    r")"
    r"(?P=quote)"
)
_WINDOWS_PATH = re.compile(r"(?i)(?<![A-Za-z0-9])" r"[A-Z]:[\\/]" r"[^\s,;|<>\"')\]}!?]*")
_UNC_PATH = re.compile(r"(?<!\\)\\\\" r"[^\\/\s,;|<>\"']+[\\/]" r"[^\s,;|<>\"')\]}!?]*")
_POSIX_PATH = re.compile(r"(?<![:#A-Za-z0-9._~/-])" r"/(?![/\s])" r"[^,;\r\n\s|<>\"')\]}!?]*")
_WELL_FORMED_TRACEBACK_BLOCK = re.compile(
    r"(?im)^traceback\s*\(most recent call last\)\s*:\s*\r?\n"
    r"(?:(?:[ \t].*|)\r?\n)*"
    r"[A-Za-z_][A-Za-z0-9_.]*"
    r"(?:Error|Exception|Failure|Timeout)(?:[: ].*)?(?=\r?\n|$)"
)
_UNTERMINATED_TRACEBACK_BLOCK = re.compile(r"(?is)traceback\s*\(most recent call last\)\s*:.*")
_OBJECT_ADDRESS = re.compile(r"(?i)\bat\s+0x[0-9a-f]{6,}\b")
_URL_USERINFO = re.compile(r"(?i)(https?://)[^/@\s:]+:[^/@\s]+@")
_ASSIGNMENT_PREFIX = re.compile(
    r"(?ix)" r"\b(?P<key>[A-Za-z][A-Za-z0-9_.-]{0,127})" r"(?P<separator>\s*[:=]\s*)"
)
_AUTHORIZATION_HEADER_PREFIX = re.compile(
    r"(?i)\b(?P<header>Proxy-Authorization|Authorization)" r"(?P<separator>\s*:\s*)"
)
_COOKIE_HEADER_PREFIX = re.compile(r"(?i)\b(?P<header>Set-Cookie|Cookie)" r"(?P<separator>\s*:\s*)")
_AUTHORIZATION_SCHEME = re.compile(r"[A-Za-z][A-Za-z0-9._+-]*")
_COOKIE_PAIR = re.compile(
    r"(?s)(?P<leading>\s*)(?P<name>[^=;\s]+)"
    r"(?P<separator>\s*=\s*)(?P<value>.*?)(?P<trailing>\s*)\Z"
)
_BEARER_PREFIX = re.compile(r"(?i)\bbearer\s+")
_INTERNAL_TOKEN = re.compile(r"\x00AUTOWEALTH_[A-Z]+_\d+\x00")
_INTERNAL_TOKEN_PREFIX = "\x00AUTOWEALTH_"
_EXCEPTION_TYPE_PREFIX = re.compile(
    r"^([A-Za-z_][A-Za-z0-9_.-]{0,127}" r"(?:Error|Exception|Failure|Timeout))(?::|\s|$)"
)
_SAFE_EXCEPTION_TEXT = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]{0,127} \[details redacted\]$")
_SAFE_EXCEPTION_TYPE = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_]{0,127}" r"(?:Error|Exception|Failure|Timeout)$"
)
_SAFE_PLACEHOLDERS = (
    REDACTED_SENSITIVE_VALUE,
    REDACTED_ABSOLUTE_PATH,
    REDACTED_TRACEBACK,
    REDACTED_PROVIDER_RESPONSE,
    "[details redacted]",
    REDACTED_HEADERS,
    REDACTED_UNSAFE_VALUE,
)
_SAFE_SENTENCE_PUNCTUATION = ".)]}!?\"'"
_SAFE_SEPARATOR_PUNCTUATION = ",;"
_HEADER_ASSIGNMENT_KEYS = {
    "authorization",
    "proxy_authorization",
    "cookie",
    "set_cookie",
}


def normalize_security_key(value: str) -> str:
    """Normalize common key styles to deterministic snake_case."""
    candidate = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", str(value))
    candidate = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", candidate)
    candidate = re.sub(r"[^A-Za-z0-9]+", "_", candidate)
    return candidate.strip("_").lower()


def is_sensitive_key(value: str) -> bool:
    """Return whether a key names credential material, without substring matching."""
    normalized = normalize_security_key(value)
    if normalized in _ALLOWED_SECURITY_KEYS:
        return False
    return normalized in _SENSITIVE_KEYS or any(
        normalized.endswith(suffix) for suffix in _SENSITIVE_KEY_SUFFIXES
    )


def is_forbidden_payload_key(value: str) -> bool:
    """Return whether a key names raw transport or traceback material."""
    normalized = normalize_security_key(value)
    return normalized in _FORBIDDEN_PAYLOAD_KEYS or any(
        normalized.endswith(suffix) for suffix in _FORBIDDEN_PAYLOAD_SUFFIXES
    )


def _replace_text_spans(
    value: str,
    spans: list[tuple[int, int, str]],
) -> str:
    if not spans:
        return value
    result: list[str] = []
    cursor = 0
    for start, end, replacement in spans:
        if start < cursor:
            continue
        result.extend((value[cursor:start], replacement))
        cursor = end
    result.append(value[cursor:])
    return "".join(result)


def _safe_placeholder_end(value: str, start: int) -> int | None:
    internal_token = _INTERNAL_TOKEN.match(value, start)
    if internal_token is not None:
        return internal_token.end()
    for placeholder in _SAFE_PLACEHOLDERS:
        if value.startswith(placeholder, start):
            return start + len(placeholder)
    return None


def _complete_safe_placeholder_end(
    value: str,
    start: int,
    *,
    limit: int | None = None,
) -> int | None:
    boundary = len(value) if limit is None else limit
    token_end = _safe_placeholder_end(value, start)
    if token_end is None or token_end > boundary:
        return None
    if token_end == boundary or value[token_end].isspace():
        return token_end

    cursor = token_end
    while cursor < boundary and value[cursor] in _SAFE_SENTENCE_PUNCTUATION:
        cursor += 1
    if cursor > token_end:
        if cursor == boundary or value[cursor].isspace():
            return token_end
        if value[cursor] in _SAFE_SEPARATOR_PUNCTUATION:
            cursor += 1
            if cursor == boundary or value[cursor].isspace():
                return token_end
        return None

    if value[cursor] in _SAFE_SEPARATOR_PUNCTUATION:
        cursor += 1
        if cursor == boundary or value[cursor].isspace():
            return token_end
    return None


def _unsafe_placeholder_value_end(
    value: str,
    start: int,
    *,
    limit: int | None = None,
) -> int:
    boundary = len(value) if limit is None else limit
    end = start
    while end < boundary:
        character = value[end]
        if character in "\r\n" or character.isspace():
            break
        if character in _SAFE_SEPARATOR_PUNCTUATION:
            next_index = end + 1
            if next_index == boundary or value[next_index].isspace():
                break
        if character in _SAFE_SENTENCE_PUNCTUATION:
            next_index = end + 1
            if next_index == boundary or value[next_index].isspace():
                break
        end += 1
    return end


def _assignment_value_end(
    value: str,
    start: int,
    *,
    stop_at_whitespace: bool = False,
) -> int:
    if start >= len(value):
        return start
    if _safe_placeholder_end(value, start) is not None:
        if _complete_safe_placeholder_end(value, start) is not None:
            return start
        return _unsafe_placeholder_value_end(value, start)
    first = value[start]
    if first in {'"', "'"}:
        escaped = False
        for index in range(start + 1, len(value)):
            character = value[index]
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == first:
                return index + 1
        return len(value)
    closing = {"{": "}", "[": "]", "(": ")"}
    if first in closing:
        stack = [closing[first]]
        quote: str | None = None
        escaped = False
        for index in range(start + 1, len(value)):
            character = value[index]
            if quote is not None:
                if escaped:
                    escaped = False
                elif character == "\\":
                    escaped = True
                elif character == quote:
                    quote = None
                continue
            if character in {'"', "'"}:
                quote = character
            elif character in closing:
                stack.append(closing[character])
            elif stack and character == stack[-1]:
                stack.pop()
                if not stack:
                    return index + 1
        return len(value)
    end = start
    while (
        end < len(value)
        and value[end] not in ",;\r\n"
        and not (stop_at_whitespace and value[end].isspace())
    ):
        end += 1
    while end > start and value[end - 1].isspace():
        end -= 1
    return end


def _line_end(value: str, start: int) -> int:
    endings = [index for index in (value.find("\r", start), value.find("\n", start)) if index >= 0]
    return min(endings, default=len(value))


def _find_unquoted_semicolon(value: str, start: int, limit: int) -> int:
    quote: str | None = None
    escaped = False
    for index in range(start, limit):
        character = value[index]
        if quote is not None:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == quote:
                quote = None
            continue
        if character in {'"', "'"}:
            quote = character
        elif character == ";":
            return index
    return limit


def _credential_value_span(
    value: str,
    start: int,
    limit: int,
) -> tuple[int, int, str] | None:
    if start >= limit:
        return None
    if _complete_safe_placeholder_end(value, start, limit=limit) is not None:
        return None
    if _safe_placeholder_end(value, start) is not None:
        end = _unsafe_placeholder_value_end(value, start, limit=limit)
        return (start, end, REDACTED_SENSITIVE_VALUE) if end > start else None

    quote = value[start] if value[start] in {'"', "'"} else None
    if quote is not None:
        escaped = False
        end = start + 1
        while end < limit:
            character = value[end]
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == quote:
                break
            end += 1
        content_start = start + 1
        content_end = min(end, limit)
        if (
            _complete_safe_placeholder_end(
                value,
                content_start,
                limit=content_end,
            )
            is not None
        ):
            return None
        return (
            content_start,
            content_end,
            REDACTED_SENSITIVE_VALUE,
        )

    end = start
    terminal_characters = ",;!?)]}\"'"
    while end < limit:
        character = value[end]
        if character.isspace() or character in terminal_characters:
            break
        if character == ".":
            next_index = end + 1
            if next_index == limit or value[next_index].isspace():
                break
        end += 1
    return (start, end, REDACTED_SENSITIVE_VALUE) if end > start else None


def _authorization_header_spans(value: str) -> list[tuple[int, int, str]]:
    spans: list[tuple[int, int, str]] = []
    for match in _AUTHORIZATION_HEADER_PREFIX.finditer(value):
        value_start = match.end()
        line_end = _line_end(value, value_start)
        if (
            _complete_safe_placeholder_end(
                value,
                value_start,
                limit=line_end,
            )
            is not None
        ):
            continue

        scheme_match = _AUTHORIZATION_SCHEME.match(value, value_start, line_end)
        if scheme_match is None:
            span = _credential_value_span(value, value_start, line_end)
            if span is not None:
                spans.append(span)
            continue

        scheme_end = scheme_match.end()
        credential_start = scheme_end
        while credential_start < line_end and value[credential_start].isspace():
            credential_start += 1
        if credential_start == scheme_end or credential_start >= line_end:
            continue

        if scheme_match.group(0).lower() == "digest":
            if (
                _complete_safe_placeholder_end(
                    value,
                    credential_start,
                    limit=line_end,
                )
                is not None
            ):
                continue
            credential_end = _find_unquoted_semicolon(
                value,
                credential_start,
                line_end,
            )
            while credential_end > credential_start and value[credential_end - 1].isspace():
                credential_end -= 1
            if credential_end > credential_start:
                spans.append(
                    (
                        credential_start,
                        credential_end,
                        REDACTED_SENSITIVE_VALUE,
                    )
                )
            continue

        span = _credential_value_span(value, credential_start, line_end)
        if span is not None:
            spans.append(span)
    return spans


def _cookie_pair_value_span(
    value: str,
    segment_start: int,
    segment_end: int,
) -> tuple[int, int, str] | None:
    pair = _COOKIE_PAIR.fullmatch(value[segment_start:segment_end])
    if pair is None:
        return None
    value_start = segment_start + pair.start("value")
    value_end = segment_start + pair.end("value")
    if (
        value_end - value_start >= 2
        and value[value_start] in {'"', "'"}
        and value[value_end - 1] == value[value_start]
    ):
        content_start = value_start + 1
        content_end = value_end - 1
        if (
            _complete_safe_placeholder_end(
                value,
                content_start,
                limit=content_end,
            )
            is not None
        ):
            return (value_start, value_start, "")
        return (
            content_start,
            content_end,
            REDACTED_SENSITIVE_VALUE,
        )
    if (
        _complete_safe_placeholder_end(
            value,
            value_start,
            limit=value_end,
        )
        is not None
    ):
        return (value_start, value_start, "")
    return (
        value_start,
        value_end,
        REDACTED_SENSITIVE_VALUE,
    )


def _cookie_header_spans(value: str) -> list[tuple[int, int, str]]:
    spans: list[tuple[int, int, str]] = []
    for match in _COOKIE_HEADER_PREFIX.finditer(value):
        line_end = _line_end(value, match.end())
        segment_start = match.end()
        is_set_cookie = normalize_security_key(match.group("header")) == "set_cookie"
        pair_index = 0
        while segment_start < line_end:
            segment_end = _find_unquoted_semicolon(
                value,
                segment_start,
                line_end,
            )
            span = _cookie_pair_value_span(value, segment_start, segment_end)
            if span is None:
                break
            if span[0] != span[1]:
                spans.append(span)
            pair_index += 1
            if is_set_cookie or segment_end == line_end:
                break
            segment_start = segment_end + 1
        if pair_index == 0:
            continue
    return spans


def _standalone_bearer_spans(value: str) -> list[tuple[int, int, str]]:
    spans: list[tuple[int, int, str]] = []
    for match in _BEARER_PREFIX.finditer(value):
        span = _credential_value_span(
            value,
            match.end(),
            _line_end(value, match.end()),
        )
        if span is not None:
            spans.append(span)
    return spans


def _forbidden_assignment_spans(value: str) -> list[tuple[int, int, str]]:
    spans: list[tuple[int, int, str]] = []
    for match in _ASSIGNMENT_PREFIX.finditer(value):
        normalized = normalize_security_key(match.group("key"))
        if not is_forbidden_payload_key(normalized):
            continue
        end = _assignment_value_end(value, match.end())
        if end <= match.end():
            continue
        if normalized == "headers" or normalized.endswith("_headers"):
            marker = REDACTED_HEADERS
        elif normalized in {"traceback", "stack_trace"}:
            marker = REDACTED_TRACEBACK
        else:
            marker = REDACTED_PROVIDER_RESPONSE
        spans.append(
            (
                match.start(),
                end,
                f"{match.group('key')}{match.group('separator')}{marker}",
            )
        )
    return spans


def _sensitive_assignment_spans(value: str) -> list[tuple[int, int, str]]:
    spans: list[tuple[int, int, str]] = []
    for match in _ASSIGNMENT_PREFIX.finditer(value):
        normalized = normalize_security_key(match.group("key"))
        if ":" in match.group("separator") and normalized in _HEADER_ASSIGNMENT_KEYS:
            continue
        if not is_sensitive_key(normalized):
            continue
        value_start = match.end()
        bearer_match = _BEARER_PREFIX.match(value, value_start)
        bearer = ""
        if bearer_match is not None:
            bearer = bearer_match.group(0)
            value_start = bearer_match.end()
        end = _assignment_value_end(
            value,
            value_start,
            stop_at_whitespace=True,
        )
        if end <= value_start:
            continue
        spans.append(
            (
                match.start(),
                end,
                (
                    f"{match.group('key')}{match.group('separator')}"
                    f"{bearer}{REDACTED_SENSITIVE_VALUE}"
                ),
            )
        )
    return spans


def _redact_forbidden_assignments(value: str) -> str:
    return _replace_text_spans(value, _forbidden_assignment_spans(value))


def _redact_authorization_headers(value: str) -> str:
    return _replace_text_spans(value, _authorization_header_spans(value))


def _redact_cookie_headers(value: str) -> str:
    return _replace_text_spans(value, _cookie_header_spans(value))


def _redact_sensitive_assignments(value: str) -> str:
    return _replace_text_spans(value, _sensitive_assignment_spans(value))


def _redact_standalone_bearer_values(value: str) -> str:
    return _replace_text_spans(value, _standalone_bearer_spans(value))


def _protect_tokens(
    value: str,
    tokens: tuple[str, ...],
    namespace: str,
) -> tuple[str, list[str]]:
    protected = value
    found: list[str] = []
    for token in tokens:
        if token not in protected:
            continue
        marker = f"\x00AUTOWEALTH_{namespace}_{len(found)}\x00"
        protected = protected.replace(token, marker)
        found.append(token)
    return protected, found


def _restore_tokens(value: str, tokens: list[str], namespace: str) -> str:
    restored = value
    for index, token in enumerate(tokens):
        restored = restored.replace(f"\x00AUTOWEALTH_{namespace}_{index}\x00", token)
    return restored


def contains_absolute_path(value: str) -> bool:
    """Detect Windows, UNC, POSIX, and file URI paths while ignoring HTTP URLs."""
    text = _HTTP_URL.sub("", str(value))
    return bool(
        _FILE_URI.search(text)
        or _QUOTED_ABSOLUTE_PATH.search(text)
        or _WINDOWS_PATH.search(text)
        or _UNC_PATH.search(text)
        or _POSIX_PATH.search(text)
    )


def contains_sensitive_value(value: str) -> bool:
    """Detect explicit credential assignments and bearer values."""
    text = str(value).replace(_INTERNAL_TOKEN_PREFIX, REDACTED_UNSAFE_VALUE)
    protected, _ = _protect_tokens(text, _SAFE_PLACEHOLDERS, "SAFE")
    detected = bool(
        _authorization_header_spans(protected)
        or _cookie_header_spans(protected)
        or _forbidden_assignment_spans(protected)
        or _sensitive_assignment_spans(protected)
        or _standalone_bearer_spans(protected)
        or _URL_USERINFO.search(protected)
    )
    return detected


def _redact_unquoted_path(match: re.Match[str]) -> str:
    matched = match.group(0)
    suffix = ""
    while matched.endswith("."):
        matched = matched[:-1]
        suffix += "."
    if not matched:
        return match.group(0)
    return f"{REDACTED_ABSOLUTE_PATH}{suffix}"


def _redact_quoted_path(match: re.Match[str]) -> str:
    quote = match.group("quote")
    return f"{quote}{REDACTED_ABSOLUTE_PATH}{quote}"


def _replace_paths_outside_urls(value: str) -> str:
    protected, urls = _protect_tokens(value, tuple(_HTTP_URL.findall(value)), "URL")
    protected = _FILE_URI.sub(REDACTED_ABSOLUTE_PATH, protected)
    protected = _QUOTED_ABSOLUTE_PATH.sub(_redact_quoted_path, protected)
    protected = _WINDOWS_PATH.sub(_redact_unquoted_path, protected)
    protected = _UNC_PATH.sub(_redact_unquoted_path, protected)
    protected = _POSIX_PATH.sub(_redact_unquoted_path, protected)
    return _restore_tokens(protected, urls, "URL")


def sanitize_public_text(value: str) -> str:
    """Replace only recognized sensitive spans and do so idempotently."""
    raw_text = str(value).replace(_INTERNAL_TOKEN_PREFIX, REDACTED_UNSAFE_VALUE)
    text, placeholders = _protect_tokens(raw_text, _SAFE_PLACEHOLDERS, "SAFE")
    text = _WELL_FORMED_TRACEBACK_BLOCK.sub(REDACTED_TRACEBACK, text)
    text = _UNTERMINATED_TRACEBACK_BLOCK.sub(REDACTED_TRACEBACK, text)
    text = _URL_USERINFO.sub(rf"\1{REDACTED_SENSITIVE_VALUE}@", text)
    text = _redact_authorization_headers(text)
    text = _redact_cookie_headers(text)
    text = _redact_forbidden_assignments(text)
    text = _redact_sensitive_assignments(text)
    text = _redact_standalone_bearer_values(text)
    text = _replace_paths_outside_urls(text)
    text = _OBJECT_ADDRESS.sub("at [redacted-address]", text)
    sanitized = _restore_tokens(text, placeholders, "SAFE")
    if contains_sensitive_value(sanitized) or contains_absolute_path(sanitized):
        return REDACTED_UNSAFE_VALUE
    return sanitized


def _safe_exception_type_name(value: object) -> str:
    candidate = str(value)
    return (
        candidate
        if len(candidate) <= 128 and _SAFE_EXCEPTION_TYPE.fullmatch(candidate)
        else "Exception"
    )


def _persisted_exception_summary(
    value: object,
    container: Mapping[object, object],
) -> object:
    if value is None:
        return None
    if type(value) is not str:
        return REDACTED_UNSAFE_VALUE
    text = sanitize_public_text(value)
    if _SAFE_EXCEPTION_TEXT.fullmatch(text):
        return text[:SAFE_EXCEPTION_SUMMARY_MAX_LENGTH]
    exception_type = container.get("exception_type")
    if type(exception_type) is str and exception_type:
        safe_type = _safe_exception_type_name(exception_type)
    else:
        match = _EXCEPTION_TYPE_PREFIX.match(text)
        safe_type = _safe_exception_type_name(match.group(1) if match else "Exception")
    return f"{safe_type} [details redacted]"[:SAFE_EXCEPTION_SUMMARY_MAX_LENGTH]


def _is_exception_payload_field(
    key: str,
    container: Mapping[object, object],
) -> bool:
    normalized = normalize_security_key(key)
    if normalized in _EXCEPTION_VALUE_KEYS:
        return True
    status_value = container.get("status")
    status = status_value.lower() if type(status_value) is str else ""
    if normalized == "error":
        exception_type = container.get("exception_type")
        return status in {"failed", "unavailable"} or (
            type(exception_type) is str and bool(exception_type)
        )
    if normalized == "reason":
        reason_code = container.get("reason_code")
        return type(reason_code) is str and reason_code in _EXCEPTION_REASON_CODES
    return False


def sanitize_public_payload(
    value: object,
    *,
    limits: PublicSanitizationLimits = DEFAULT_PUBLIC_SANITIZATION_LIMITS,
) -> object:
    """Sanitize exact JSON content under one shared deterministic budget."""
    if not isinstance(limits, PublicSanitizationLimits):
        raise TypeError("limits must be PublicSanitizationLimits")
    budget = _PublicSanitizationBudget(limits)

    def walk(item: object, depth: int) -> object:
        if depth > limits.max_depth:
            raise PublicSanitizationError("public payload exceeds the nesting limit")
        if item is None:
            budget.consume_node()
            return None
        if type(item) in (bool, int):
            budget.consume_node()
            return item
        if type(item) is float:
            budget.consume_node()
            if not math.isfinite(item):
                raise PublicSanitizationError("public payload contains a non-finite number")
            return item
        if type(item) is str:
            budget.consume_string(item)
            return sanitize_public_text(item)
        if type(item) is list:
            budget.consume_node()
            if len(item) > limits.max_sequence_items:
                raise PublicSanitizationError("public payload exceeds the sequence width limit")
            return [walk(child, depth + 1) for child in item]
        if type(item) is dict:
            budget.consume_node()
            if len(item) > limits.max_mapping_items:
                raise PublicSanitizationError("public payload exceeds the mapping width limit")
            result: dict[str, object] = {}
            for key, child in item.items():
                if type(key) is not str:
                    raise PublicSanitizationError("public payload mapping keys must be strings")
                budget.consume_string(key)
                public_key = sanitize_public_text(key)
                if public_key in result:
                    suffix = 2
                    while f"{public_key}_{suffix}" in result:
                        suffix += 1
                    public_key = f"{public_key}_{suffix}"
                if is_sensitive_key(key):
                    budget.consume_node()
                    result[public_key] = REDACTED_SENSITIVE_VALUE
                elif is_forbidden_payload_key(key):
                    budget.consume_node()
                    result[public_key] = REDACTED_UNSAFE_VALUE
                elif _is_exception_payload_field(key, item):
                    if type(child) is str:
                        budget.consume_string(child)
                    else:
                        budget.consume_node()
                    result[public_key] = _persisted_exception_summary(child, item)
                else:
                    result[public_key] = walk(child, depth + 1)
            return result
        budget.consume_node()
        return REDACTED_UNSAFE_VALUE

    normalized = walk(value, 1)
    try:
        encoded = json.dumps(
            normalized,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, RecursionError) as exc:  # pragma: no cover
        raise PublicSanitizationError("public payload could not be serialized safely") from exc
    if len(encoded) > limits.max_json_bytes:
        raise PublicSanitizationError("public payload exceeds the JSON byte budget")
    return normalized


def validate_bounded_json(
    value: object,
    *,
    field_name: str,
    maximum_depth: int,
    maximum_mapping_keys: int,
    maximum_list_items: int,
    maximum_string_length: int,
    maximum_json_bytes: int,
) -> object:
    """Validate and normalize a deterministic, bounded JSON value."""

    def validate(item: object, path: str, depth: int) -> object:
        if item is None or type(item) in (bool, int):
            return item
        if type(item) is float:
            if not math.isfinite(item):
                raise ValueError(f"{path} must contain only finite floats")
            return item
        if type(item) is str:
            if len(item) > maximum_string_length:
                raise ValueError(
                    f"{path} strings exceed the {maximum_string_length}-character limit"
                )
            if contains_absolute_path(item):
                raise ValueError(f"{path} must not contain an absolute path")
            if contains_sensitive_value(item):
                raise ValueError(f"{path} must not contain credentials")
            return item
        if type(item) in (list, tuple):
            if depth > maximum_depth:
                raise ValueError(f"{field_name} exceeds the maximum nesting depth")
            if len(item) > maximum_list_items:
                raise ValueError(f"{path} lists exceed the {maximum_list_items}-item limit")
            return [
                validate(child, f"{path}[{index}]", depth + 1) for index, child in enumerate(item)
            ]
        if type(item) is dict:
            if depth > maximum_depth:
                raise ValueError(f"{field_name} exceeds the maximum nesting depth")
            if len(item) > maximum_mapping_keys:
                raise ValueError(f"{path} mappings exceed the {maximum_mapping_keys}-key limit")
            if not all(type(key) is str for key in item):
                raise TypeError(f"{path} keys must be strings")
            result: dict[str, object] = {}
            for key in sorted(item):
                if len(key) > maximum_string_length:
                    raise ValueError(
                        f"{path} keys exceed the {maximum_string_length}-character limit"
                    )
                if contains_absolute_path(key):
                    raise ValueError(f"{path} keys must not contain an absolute path")
                if contains_sensitive_value(key):
                    raise ValueError(f"{path} keys must not contain credentials")
                if is_sensitive_key(key):
                    raise ValueError(f"{path} contains a secret-like key")
                if (
                    is_forbidden_payload_key(key)
                    or normalize_security_key(key) in _EXCEPTION_VALUE_KEYS
                ):
                    raise ValueError(f"{path} contains raw transport, exception, or traceback data")
                result[key] = validate(item[key], f"{path}.{key}", depth + 1)
            return result
        raise TypeError(f"{path} contains a non-JSON-safe value: {type(item).__name__}")

    normalized = validate(value, field_name, 0)
    encoded = json.dumps(
        normalized,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    if len(encoded) > maximum_json_bytes:
        raise ValueError(f"{field_name} exceeds the {maximum_json_bytes}-byte JSON limit")
    return normalized


def safe_exception_summary(exc: BaseException) -> str:
    """Return a stable exception summary without copying exception text."""
    exception_type = _safe_exception_type_name(type(exc).__name__)
    return f"{exception_type} [details redacted]"[:SAFE_EXCEPTION_SUMMARY_MAX_LENGTH]


def safe_exception_record(
    exc: BaseException,
    reason_code: str,
) -> dict[str, str]:
    """Return the only exception fields allowed in persisted public diagnostics."""
    safe_reason = reason_code if type(reason_code) is str else "provider_exception"
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,127}", safe_reason):
        safe_reason = "provider_exception"
    return {
        "exception_type": _safe_exception_type_name(type(exc).__name__),
        "reason_code": safe_reason,
        "safe_summary": safe_exception_summary(exc),
    }


def safe_cache_reference(value: object, *, fallback: str = "cache") -> str:
    """Return a credential-safe basename without changing the cache I/O path."""

    candidate = _safe_cache_candidate(value)
    if candidate:
        return candidate
    fallback_candidate = _safe_cache_candidate(fallback)
    return fallback_candidate or "cache"


def _safe_cache_candidate(value: object) -> str:
    if type(value) is str:
        text = value
    elif isinstance(value, (PurePosixPath, PureWindowsPath)):
        text = str(value)
    else:
        return ""
    if not text or len(text) > 8192:
        return ""
    if "\\" in text or re.match(r"(?i)^[A-Z]:", text):
        name = PureWindowsPath(text).name
    else:
        name = PurePosixPath(text).name
    if not name:
        return ""
    trusted_extension = _trusted_cache_extension(name)
    if _cache_name_contains_credentials(name) or contains_absolute_path(name):
        return f"redacted-cache-reference{trusted_extension}"
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", name).strip("._")
    if len(safe_name) > 255:
        return f"redacted-cache-reference{trusted_extension}"
    if not safe_name:
        return ""
    if _cache_name_contains_credentials(safe_name) or contains_absolute_path(safe_name):
        return f"redacted-cache-reference{trusted_extension}"
    return safe_name


def _cache_name_contains_credentials(name: str) -> bool:
    candidates = [name]
    decoded = name
    for _ in range(2):
        next_value = unquote(decoded)
        if next_value == decoded:
            break
        candidates.append(next_value)
        decoded = next_value

    for candidate in candidates:
        if contains_sensitive_value(candidate):
            return True
        normalized = normalize_security_key(candidate)
        for allowed in sorted(_ALLOWED_SECURITY_KEYS, key=len, reverse=True):
            normalized = re.sub(
                rf"(?:(?<=^)|(?<=_)){re.escape(allowed)}(?=_|$)",
                "safe_metadata",
                normalized,
            )
        padded = f"_{normalized}_"
        if any(f"_{key}_" in padded for key in _SENSITIVE_KEYS):
            return True
    return False


def _trusted_cache_extension(name: str) -> str:
    suffixes = PurePosixPath(name).suffixes
    if not suffixes or len(suffixes) > 3:
        return ""
    if any(not re.fullmatch(r"\.[A-Za-z0-9]{1,10}", suffix) for suffix in suffixes):
        return ""
    extension = "".join(suffixes)
    if len(extension) > 32 or contains_sensitive_value(extension):
        return ""
    return extension
