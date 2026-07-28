"""Offline tests for public artifact security helpers."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import textwrap
from collections.abc import Mapping, Sequence

import pytest

import autowealth.security as security_module
from autowealth.security import (
    DEFAULT_PUBLIC_SANITIZATION_LIMITS,
    PublicSanitizationError,
    PublicSanitizationLimits,
    REDACTED_ABSOLUTE_PATH,
    REDACTED_HEADERS,
    REDACTED_PROVIDER_RESPONSE,
    REDACTED_SENSITIVE_VALUE,
    REDACTED_TRACEBACK,
    REDACTED_UNSAFE_VALUE,
    contains_absolute_path,
    is_sensitive_key,
    normalize_security_key,
    safe_cache_reference,
    safe_exception_record,
    safe_exception_summary,
    sanitize_public_payload,
    sanitize_public_text,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("apiKey", "api_key"),
        ("AccessToken", "access_token"),
        ("client-secret", "client_secret"),
        ("proxy.authorization", "proxy_authorization"),
        ("SET_COOKIE", "set_cookie"),
    ],
)
def test_security_key_normalization(value: str, expected: str) -> None:
    assert normalize_security_key(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "apiKey",
        "serviceApiToken",
        "accessToken",
        "clientSecret",
        "proxy-authorization",
        "session_cookie",
        "databasePassword",
        "private.secret",
    ],
)
def test_sensitive_key_detection_covers_explicit_credentials(value: str) -> None:
    assert is_sensitive_key(value) is True


@pytest.mark.parametrize(
    "value",
    [
        "token_count",
        "tokenUsage",
        "authorization_status",
        "cookie-policy",
        "passwordPolicy",
        "secretRotationStatus",
    ],
)
def test_sensitive_key_detection_allows_documented_status_fields(value: str) -> None:
    assert is_sensitive_key(value) is False


@pytest.mark.parametrize(
    "value",
    [
        r"C:\Users\researcher\cache.parquet",
        "D:/research/cache.parquet",
        r"\\server\share\cache.parquet",
        "/tmp/research/cache.parquet",
        "provider failed at /home/service/cache.parquet",
    ],
)
def test_absolute_path_detection_covers_supported_path_styles(value: str) -> None:
    assert contains_absolute_path(value) is True
    assert REDACTED_ABSOLUTE_PATH in sanitize_public_text(value)


@pytest.mark.parametrize(
    "value",
    [
        "https://example.com/research/cache.parquet",
        "http://127.0.0.1:8001/research/runs",
        "benchmark_diagnostics.json",
        "docs/research-api.md",
        "warnings.json#/structured_warnings/0",
        "#/benchmarks/000300",
        "annualized return / volatility",
    ],
)
def test_path_detection_does_not_reject_urls_relative_refs_or_json_pointers(
    value: str,
) -> None:
    assert contains_absolute_path(value) is False
    assert sanitize_public_text(value) == value


def test_public_text_redacts_credentials_headers_traceback_and_object_addresses() -> None:
    value = (
        "provider failed request_headers={'Authorization': 'Bearer header-secret'} "
        "apiKey=key-secret accessToken=access-secret clientSecret=client-secret "
        "DEEPSEEK_API_KEY=deepseek-secret service_access_token=service-secret "
        "Cookie: session=cookie-secret\n"
        "Traceback (most recent call last):\n"
        '  File "C:\\private\\provider.py", line 1\n'
        "RuntimeError at 0x7FFABCDEF123"
    )

    sanitized = sanitize_public_text(value)

    assert "header-secret" not in sanitized
    assert "key-secret" not in sanitized
    assert "access-secret" not in sanitized
    assert "client-secret" not in sanitized
    assert "deepseek-secret" not in sanitized
    assert "service-secret" not in sanitized
    assert "cookie-secret" not in sanitized
    assert "C:\\private" not in sanitized
    assert "0x7FFABCDEF123" not in sanitized
    assert REDACTED_HEADERS in sanitized
    assert REDACTED_SENSITIVE_VALUE in sanitized
    assert REDACTED_TRACEBACK in sanitized


def test_public_payload_recursively_redacts_without_changing_safe_values() -> None:
    payload = {
        "status": "partial_success",
        "source": {
            "cache_path": r"D:\private\benchmark.parquet",
            "apiToken": "token-secret",
            "authorization_status": "not_required",
        },
        "warnings": ["ordinary warning"],
    }

    sanitized = sanitize_public_payload(payload)

    assert sanitized == {
        "status": "partial_success",
        "source": {
            "cache_path": REDACTED_ABSOLUTE_PATH,
            "apiToken": REDACTED_SENSITIVE_VALUE,
            "authorization_status": "not_required",
        },
        "warnings": ["ordinary warning"],
    }
    assert payload["source"]["cache_path"] == r"D:\private\benchmark.parquet"


def test_public_payload_sanitizes_path_keys_and_old_exception_fields() -> None:
    payload = {
        r"C:\private\field": "value",
        "provider": {
            "status": "failed",
            "reason_code": "provider_exception",
            "exception_type": "RuntimeError",
            "reason": "RuntimeError: confidential provider response",
            "exception": "RuntimeError: another confidential response",
            "error": "a third confidential response",
        },
    }

    sanitized = sanitize_public_payload(payload)
    serialized = json.dumps(sanitized, ensure_ascii=False)

    assert r"C:\private" not in serialized
    assert "confidential provider response" not in serialized
    assert "another confidential response" not in serialized
    assert "a third confidential response" not in serialized
    assert sanitized[REDACTED_ABSOLUTE_PATH] == "value"
    assert sanitized["provider"]["reason"] == "RuntimeError [details redacted]"
    assert sanitized["provider"]["exception"] == "RuntimeError [details redacted]"
    assert sanitized["provider"]["error"] == "RuntimeError [details redacted]"


def test_public_payload_preserves_non_exception_business_reason_text() -> None:
    payload = {
        "status": "failed",
        "reason_code": "insufficient_coverage",
        "reason": "coverage is below the configured threshold",
        "business_note": "ordinary warning",
    }

    assert sanitize_public_payload(payload) == payload


def test_safe_exception_record_never_copies_exception_text() -> None:
    exc = RuntimeError(
        "token=secret D:\\private\\cache.parquet\n"
        "Traceback (most recent call last): provider response"
    )

    record = safe_exception_record(exc, "provider_exception")

    assert record == {
        "exception_type": "RuntimeError",
        "reason_code": "provider_exception",
        "safe_summary": "RuntimeError [details redacted]",
    }
    assert len(record["safe_summary"]) <= 256
    assert json.dumps(record, ensure_ascii=False)
    assert safe_exception_summary(exc) == record["safe_summary"]


def test_safe_exception_record_rejects_untrusted_exception_type_name() -> None:
    class ProviderFailure(RuntimeError):
        pass

    ProviderFailure.__name__ = r"C:\private\apiKey=type-secret"

    record = safe_exception_record(ProviderFailure("details"), "provider_exception")

    assert record["exception_type"] == "Exception"
    assert record["safe_summary"] == "Exception [details redacted]"


@pytest.mark.parametrize(
    "value",
    [
        REDACTED_SENSITIVE_VALUE,
        REDACTED_ABSOLUTE_PATH,
        REDACTED_TRACEBACK,
        REDACTED_PROVIDER_RESPONSE,
        REDACTED_HEADERS,
        REDACTED_UNSAFE_VALUE,
        "[details redacted]",
        "RuntimeError at [redacted-address]",
        f"Authorization: Bearer {REDACTED_SENSITIVE_VALUE}; retry succeeded",
        "Bearer [details redacted]; retry succeeded",
        f"apiKey={REDACTED_SENSITIVE_VALUE}; retry succeeded",
    ],
)
def test_public_text_sanitizer_is_idempotent_for_safe_placeholders(value: str) -> None:
    once = sanitize_public_text(value)

    assert sanitize_public_text(once) == once


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (
            f"apiKey={REDACTED_SENSITIVE_VALUE}appended-secret",
            f"apiKey={REDACTED_SENSITIVE_VALUE}",
        ),
        (
            f"Bearer {REDACTED_SENSITIVE_VALUE}appended-secret; retry succeeded",
            f"Bearer {REDACTED_SENSITIVE_VALUE}; retry succeeded",
        ),
        (
            "apiKey=\x00AUTOWEALTH_SAFE_0\x00injected-secret",
            f"apiKey={REDACTED_SENSITIVE_VALUE}",
        ),
    ],
)
def test_public_text_does_not_trust_mixed_or_forged_internal_placeholders(
    value: str,
    expected: str,
) -> None:
    sanitized = sanitize_public_text(value)

    assert sanitized == expected
    assert sanitize_public_text(sanitized) == sanitized


@pytest.mark.parametrize(
    "placeholder",
    [
        REDACTED_SENSITIVE_VALUE,
        REDACTED_ABSOLUTE_PATH,
        REDACTED_TRACEBACK,
        REDACTED_PROVIDER_RESPONSE,
        "[details redacted]",
    ],
)
@pytest.mark.parametrize(
    "suffix",
    [
        "",
        ".",
        ". retry succeeded",
        "; retry succeeded",
        ", retry succeeded",
    ],
)
def test_public_text_accepts_only_complete_safe_placeholder_boundaries(
    placeholder: str,
    suffix: str,
) -> None:
    value = f"apiKey={placeholder}{suffix}"

    sanitized = sanitize_public_text(value)

    assert sanitized == value
    assert sanitize_public_text(sanitized) == sanitized


@pytest.mark.parametrize(
    "suffix",
    [
        ".abc123",
        ")abc123",
        "!abc123",
        "_abc123",
        "-abc123",
        "/abc123",
    ],
)
def test_public_text_rejects_sensitive_suffix_after_safe_placeholder(
    suffix: str,
) -> None:
    value = f"apiKey={REDACTED_SENSITIVE_VALUE}{suffix}; retry succeeded"

    sanitized = sanitize_public_text(value)

    assert sanitized == f"apiKey={REDACTED_SENSITIVE_VALUE}; retry succeeded"
    assert "abc123" not in sanitized
    assert sanitize_public_text(sanitized) == sanitized


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("Bearer abc123.", f"Bearer {REDACTED_SENSITIVE_VALUE}."),
        (
            "Bearer abc123. retry succeeded",
            f"Bearer {REDACTED_SENSITIVE_VALUE}. retry succeeded",
        ),
        (
            "Bearer abc123, retry succeeded",
            f"Bearer {REDACTED_SENSITIVE_VALUE}, retry succeeded",
        ),
        (
            "Bearer abc123; retry succeeded",
            f"Bearer {REDACTED_SENSITIVE_VALUE}; retry succeeded",
        ),
        (
            'Bearer "abc123"; retry succeeded',
            f'Bearer "{REDACTED_SENSITIVE_VALUE}"; retry succeeded',
        ),
        ("Bearer aaa.bbb.ccc", f"Bearer {REDACTED_SENSITIVE_VALUE}"),
        (
            "Bearer aaa.bbb.ccc. retry succeeded",
            f"Bearer {REDACTED_SENSITIVE_VALUE}. retry succeeded",
        ),
        ("Bearer YWJjZA==", f"Bearer {REDACTED_SENSITIVE_VALUE}"),
        (
            f"Bearer {REDACTED_SENSITIVE_VALUE}.abc123",
            f"Bearer {REDACTED_SENSITIVE_VALUE}",
        ),
        (
            "Bearer abc123! retry succeeded",
            f"Bearer {REDACTED_SENSITIVE_VALUE}! retry succeeded",
        ),
        (
            "Bearer abc123? retry succeeded",
            f"Bearer {REDACTED_SENSITIVE_VALUE}? retry succeeded",
        ),
        (
            "Bearer abc123) retry succeeded",
            f"Bearer {REDACTED_SENSITIVE_VALUE}) retry succeeded",
        ),
    ],
)
def test_public_text_redacts_bearer_token_without_losing_punctuation(
    value: str,
    expected: str,
) -> None:
    sanitized = sanitize_public_text(value)

    assert sanitized == expected
    assert sanitize_public_text(sanitized) == sanitized


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (
            "Authorization: Basic base64-value",
            f"Authorization: Basic {REDACTED_SENSITIVE_VALUE}",
        ),
        (
            "Authorization: Basic base64-value; retry succeeded",
            f"Authorization: Basic {REDACTED_SENSITIVE_VALUE}; retry succeeded",
        ),
        (
            "Authorization: Bearer abc123; retry succeeded",
            f"Authorization: Bearer {REDACTED_SENSITIVE_VALUE}; retry succeeded",
        ),
        (
            "Authorization: CustomScheme abc123; retry succeeded",
            f"Authorization: CustomScheme {REDACTED_SENSITIVE_VALUE}; retry succeeded",
        ),
        (
            "Proxy-Authorization: Basic abc123",
            f"Proxy-Authorization: Basic {REDACTED_SENSITIVE_VALUE}",
        ),
        (
            'Authorization: Digest username="a", response="b", nonce="c"',
            f"Authorization: Digest {REDACTED_SENSITIVE_VALUE}",
        ),
        (
            'Authorization: Digest username="a", response="b"; retry succeeded',
            f"Authorization: Digest {REDACTED_SENSITIVE_VALUE}; retry succeeded",
        ),
        ("authorization_status=success", "authorization_status=success"),
        ("proxy_authorization_status=success", "proxy_authorization_status=success"),
        ("authorization_policy=strict", "authorization_policy=strict"),
    ],
)
def test_public_text_redacts_authorization_headers_by_scheme(
    value: str,
    expected: str,
) -> None:
    sanitized = sanitize_public_text(value)

    assert sanitized == expected
    assert sanitize_public_text(sanitized) == sanitized


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (
            "Cookie: session=a",
            f"Cookie: session={REDACTED_SENSITIVE_VALUE}",
        ),
        (
            "Cookie: session=a; csrftoken=b",
            (
                f"Cookie: session={REDACTED_SENSITIVE_VALUE}; "
                f"csrftoken={REDACTED_SENSITIVE_VALUE}"
            ),
        ),
        (
            "Cookie: session=a; csrftoken=b; retry succeeded",
            (
                f"Cookie: session={REDACTED_SENSITIVE_VALUE}; "
                f"csrftoken={REDACTED_SENSITIVE_VALUE}; retry succeeded"
            ),
        ),
        (
            'Cookie: session="a b"; csrftoken="c"',
            (
                f'Cookie: session="{REDACTED_SENSITIVE_VALUE}"; '
                f'csrftoken="{REDACTED_SENSITIVE_VALUE}"'
            ),
        ),
        (
            "Set-Cookie: session=a; Path=/; HttpOnly; Secure",
            (
                f"Set-Cookie: session={REDACTED_SENSITIVE_VALUE}; "
                f"Path={REDACTED_ABSOLUTE_PATH}; HttpOnly; Secure"
            ),
        ),
        (
            "Set-Cookie: session=a; Domain=example.com; SameSite=Lax",
            (
                f"Set-Cookie: session={REDACTED_SENSITIVE_VALUE}; "
                "Domain=example.com; SameSite=Lax"
            ),
        ),
        ("cookie_policy=strict", "cookie_policy=strict"),
        ("cookie_count=2", "cookie_count=2"),
        ("set_cookie_status=disabled", "set_cookie_status=disabled"),
    ],
)
def test_public_text_redacts_cookie_headers_without_losing_safe_segments(
    value: str,
    expected: str,
) -> None:
    sanitized = sanitize_public_text(value)

    assert sanitized == expected
    assert sanitize_public_text(sanitized) == sanitized


@pytest.mark.parametrize(
    ("value", "suffix"),
    [
        ("Authorization: Bearer abc123; retry succeeded", "; retry succeeded"),
        ("Cookie: session=abc123; retry succeeded", "; retry succeeded"),
        ("Bearer abc123; retry succeeded", "; retry succeeded"),
        (
            "benchmark failed: apiKey=abc123; retry succeeded",
            "; retry succeeded",
        ),
        (r"failed C:\private\file.json; retry succeeded", "; retry succeeded"),
        (r"failed \\server\share\file.json; retry succeeded", "; retry succeeded"),
        ("failed /tmp/private.json; retry succeeded", "; retry succeeded"),
        (
            'failed "C:\\Program Files\\private.json"; retry succeeded',
            "; retry succeeded",
        ),
    ],
)
def test_public_text_redacts_exact_span_and_preserves_safe_suffix(
    value: str,
    suffix: str,
) -> None:
    sanitized = sanitize_public_text(value)

    assert sanitized.endswith(suffix)
    assert sanitized != value
    assert sanitize_public_text(sanitized) == sanitized


def test_public_text_keeps_http_url_and_redacts_adjacent_local_path() -> None:
    sanitized = sanitize_public_text("https://example.com/a; failed,/tmp/private.json")

    assert sanitized == (f"https://example.com/a; failed,{REDACTED_ABSOLUTE_PATH}")


def test_public_text_preserves_url_structure_while_redacting_userinfo() -> None:
    sanitized = sanitize_public_text(
        "https://researcher:credential-secret@example.com/report; retry succeeded"
    )

    assert sanitized == (f"https://{REDACTED_SENSITIVE_VALUE}@example.com/report; retry succeeded")
    assert sanitize_public_text(sanitized) == sanitized


def test_public_text_final_validation_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(security_module, "contains_sensitive_value", lambda value: True)

    assert sanitize_public_text("ordinary warning") == REDACTED_UNSAFE_VALUE


@pytest.mark.parametrize(
    ("label", "payload", "marker"),
    [
        (
            "provider_response",
            '{"meta":{"token":"abc"},"rows":[1,2]}',
            REDACTED_PROVIDER_RESPONSE,
        ),
        ("raw_response", '{"body":{"secret":"abc"}}', REDACTED_PROVIDER_RESPONSE),
        ("headers", '{"Authorization":"Bearer abc"}', REDACTED_HEADERS),
        ("response_headers", '{"Set-Cookie":"session=abc"}', REDACTED_HEADERS),
        (
            "traceback",
            '{"frames":["C:\\\\private\\\\provider.py"],"error":"secret"}',
            REDACTED_TRACEBACK,
        ),
    ],
)
def test_public_text_redacts_transport_payload_without_eating_suffix(
    label: str,
    payload: str,
    marker: str,
) -> None:
    sanitized = sanitize_public_text(f"{label}={payload}; retry succeeded")

    assert sanitized == f"{label}={marker}; retry succeeded"
    assert sanitize_public_text(sanitized) == sanitized


def test_public_text_redacts_well_formed_traceback_and_keeps_following_note() -> None:
    value = (
        "Traceback (most recent call last):\n"
        '  File "C:\\private\\provider.py", line 1\n'
        "    raise RuntimeError('provider secret')\n"
        "RuntimeError: provider secret\n"
        "retry succeeded with cached data"
    )

    sanitized = sanitize_public_text(value)

    assert sanitized == (f"{REDACTED_TRACEBACK}\nretry succeeded with cached data")
    assert sanitize_public_text(sanitized) == sanitized


def test_public_text_keeps_unseparated_note_after_credential_token() -> None:
    sanitized = sanitize_public_text(
        "benchmark failed: Authorization: Bearer abc123 retry succeeded"
    )

    assert sanitized == (
        "benchmark failed: " f"Authorization: Bearer {REDACTED_SENSITIVE_VALUE} retry succeeded"
    )


@pytest.mark.parametrize(
    "value",
    [
        "https://example.com/path",
        "docs/structured-warnings.md",
        "warnings.json#/structured_warnings/0",
        "pe_ttm/pb",
        "authorization_status",
        "token_count",
        "cookie_policy",
    ],
)
def test_public_text_does_not_redact_documented_safe_tokens(value: str) -> None:
    assert sanitize_public_text(value) == value


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (
            r"C:\cache\apiKey=abc123.parquet",
            "redacted-cache-reference.parquet",
        ),
        (
            "/tmp/cache/accessToken=abc123.json",
            "redacted-cache-reference.json",
        ),
        (
            r"\\server\cache\clientSecret=abc123.parquet",
            "redacted-cache-reference.parquet",
        ),
        (
            r"C:\cache\Bearer abc123.parquet",
            "redacted-cache-reference.parquet",
        ),
        (
            r"C:\cache\Cookie=session-abc.json",
            "redacted-cache-reference.json",
        ),
        (
            "/tmp/cache/credential=credential-secret.csv",
            "redacted-cache-reference.csv",
        ),
        (
            r"C:\cache\Authorization=Bearer auth-secret.parquet",
            "redacted-cache-reference.parquet",
        ),
        (r"C:\cache\prices.parquet", "prices.parquet"),
        ("/tmp/cache/prices", "prices"),
        ("/tmp/cache/prices.data.parquet", "prices.data.parquet"),
        (
            "/tmp/cache/apiKey=abc123.parquet.$secret",
            "redacted-cache-reference",
        ),
        (
            "/tmp/cache/apiKey%3Dencoded-secret.parquet",
            "redacted-cache-reference.parquet",
        ),
        (
            "/tmp/cache/cache-api-key-encoded-secret.parquet",
            "redacted-cache-reference.parquet",
        ),
        ("/tmp/cache/token_count.parquet", "token_count.parquet"),
        (
            "/tmp/cache/authorization_status.json",
            "authorization_status.json",
        ),
    ],
)
def test_safe_cache_reference_checks_raw_basename_before_normalization(
    value: str,
    expected: str,
) -> None:
    public_reference = safe_cache_reference(value)

    assert public_reference == expected
    assert "abc123" not in public_reference


def test_safe_cache_reference_validates_fallback_without_exposing_it() -> None:
    public_reference = safe_cache_reference(
        "",
        fallback="apiKey=fallback-secret.json",
    )

    assert public_reference == "redacted-cache-reference.json"
    assert "fallback-secret" not in public_reference


@pytest.mark.parametrize(
    "value",
    [
        {f"key_{index}": index for index in range(65)},
        list(range(65)),
    ],
)
def test_public_payload_rejects_container_width_over_default_limit(
    value: object,
) -> None:
    with pytest.raises(PublicSanitizationError):
        sanitize_public_payload(value)


def test_public_payload_rejects_node_string_and_json_budgets() -> None:
    node_limits = PublicSanitizationLimits(max_nodes=3)
    string_limits = PublicSanitizationLimits(max_total_string_chars=4)
    json_limits = PublicSanitizationLimits(max_json_bytes=6)

    with pytest.raises(PublicSanitizationError, match="node"):
        sanitize_public_payload({"a": [1, 2]}, limits=node_limits)
    with pytest.raises(PublicSanitizationError, match="string"):
        sanitize_public_payload({"a": "1234"}, limits=string_limits)
    with pytest.raises(PublicSanitizationError, match="JSON"):
        sanitize_public_payload({"a": 1}, limits=json_limits)


def test_public_payload_rejects_depth_without_returning_input() -> None:
    value: dict[str, object] = {}
    cursor = value
    for _ in range(DEFAULT_PUBLIC_SANITIZATION_LIMITS.max_depth + 1):
        child: dict[str, object] = {}
        cursor["nested"] = child
        cursor = child

    with pytest.raises(PublicSanitizationError, match="nesting"):
        sanitize_public_payload(value)


class _UnboundedMapping(Mapping):
    def __getitem__(self, key):
        raise AssertionError("custom mapping must not be indexed")

    def __iter__(self):
        raise AssertionError("custom mapping must not be iterated")

    def __len__(self):
        raise AssertionError("custom mapping length must not be trusted")


class _UnsafeObject:
    def __str__(self) -> str:
        raise AssertionError("unsafe objects must not be stringified")


class _UnboundedSequence(Sequence):
    def __getitem__(self, index):
        raise AssertionError("custom sequence must not be indexed")

    def __len__(self):
        raise AssertionError("custom sequence length must not be trusted")


class _ListSubclass(list):
    def __iter__(self):
        raise AssertionError("list subclasses must not be iterated")


def test_public_payload_does_not_expand_custom_containers_or_generator() -> None:
    assert sanitize_public_payload(_UnboundedMapping()) == REDACTED_UNSAFE_VALUE
    assert sanitize_public_payload(_UnboundedSequence()) == REDACTED_UNSAFE_VALUE
    assert sanitize_public_payload(_ListSubclass([1, 2])) == REDACTED_UNSAFE_VALUE
    assert sanitize_public_payload((1, 2)) == REDACTED_UNSAFE_VALUE
    assert sanitize_public_payload({1, 2}) == REDACTED_UNSAFE_VALUE
    assert sanitize_public_payload(frozenset({1, 2})) == REDACTED_UNSAFE_VALUE
    assert sanitize_public_payload((item for item in range(3))) == REDACTED_UNSAFE_VALUE
    assert sanitize_public_payload(_UnsafeObject()) == REDACTED_UNSAFE_VALUE


def test_public_payload_non_finite_numbers_are_not_silently_changed_to_null() -> None:
    for value in (float("nan"), float("inf"), float("-inf")):
        with pytest.raises(PublicSanitizationError, match="non-finite"):
            sanitize_public_payload({"metric": value})


def test_security_module_import_is_isolated_and_has_no_side_effects() -> None:
    repository_root = Path(__file__).resolve().parents[1]
    script = textwrap.dedent(r"""
        import ast
        import builtins
        import importlib
        import os
        from pathlib import Path
        import socket
        import sys
        import types

        repository_root = Path(sys.argv[1]).resolve()
        security_path = repository_root / "autowealth" / "security.py"
        environment_before = dict(os.environ)
        network_attempts = []
        write_attempts = []
        sys.dont_write_bytecode = True

        def is_repository_path(value):
            if not isinstance(value, (str, bytes, os.PathLike)):
                return False
            try:
                Path(value).resolve().relative_to(repository_root)
            except (OSError, RuntimeError, ValueError):
                return False
            return True

        original_open = builtins.open

        def guarded_open(file, mode="r", *args, **kwargs):
            if is_repository_path(file) and any(flag in mode for flag in "wax+"):
                write_attempts.append(str(file))
                raise AssertionError("security import attempted a repository write")
            return original_open(file, mode, *args, **kwargs)

        original_os_open = os.open
        write_flags = os.O_WRONLY | os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_TRUNC

        def guarded_os_open(path, flags, mode=0o777, *, dir_fd=None):
            if is_repository_path(path) and flags & write_flags:
                write_attempts.append(str(path))
                raise AssertionError("security import attempted a repository write")
            if dir_fd is None:
                return original_os_open(path, flags, mode)
            return original_os_open(path, flags, mode, dir_fd=dir_fd)

        def reject_network(*args, **kwargs):
            network_attempts.append((args, kwargs))
            raise AssertionError("security import attempted a network connection")

        original_write_text = Path.write_text
        original_write_bytes = Path.write_bytes

        def guarded_write_text(path, *args, **kwargs):
            if is_repository_path(path):
                write_attempts.append(str(path))
                raise AssertionError("security import attempted a repository write")
            return original_write_text(path, *args, **kwargs)

        def guarded_write_bytes(path, *args, **kwargs):
            if is_repository_path(path):
                write_attempts.append(str(path))
                raise AssertionError("security import attempted a repository write")
            return original_write_bytes(path, *args, **kwargs)

        builtins.open = guarded_open
        os.open = guarded_os_open
        Path.write_text = guarded_write_text
        Path.write_bytes = guarded_write_bytes
        socket.socket.connect = reject_network
        socket.create_connection = reject_network

        tree = ast.parse(security_path.read_text(encoding="utf-8"))
        import_roots = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                import_roots.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                import_roots.add(node.module.split(".", 1)[0])
        allowed_roots = {
            "__future__",
            "dataclasses",
            "json",
            "math",
            "pathlib",
            "re",
            "typing",
            "urllib",
        }
        assert import_roots <= allowed_roots, sorted(import_roots - allowed_roots)

        package = types.ModuleType("autowealth")
        package.__path__ = [str(repository_root / "autowealth")]
        sys.modules["autowealth"] = package
        module = importlib.import_module("autowealth.security")

        assert module.sanitize_public_payload({"status": "ok"}) == {"status": "ok"}
        assert dict(os.environ) == environment_before
        assert network_attempts == []
        assert write_attempts == []
        print("security-import-ok")
        """)

    completed = subprocess.run(
        [sys.executable, "-B", "-c", script, str(repository_root)],
        cwd=repository_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert completed.stdout.strip() == "security-import-ok"
    assert isinstance(DEFAULT_PUBLIC_SANITIZATION_LIMITS, PublicSanitizationLimits)
    assert sanitize_public_payload({"status": "ok"}) == {"status": "ok"}

    from autowealth.data.index_provider_chain import ProviderAttempt

    attempt = ProviderAttempt(
        provider="fake",
        endpoint="offline",
        canonical_symbol="000300",
        provider_symbol="000300",
        status="failed",
        started_at="2025-01-01T00:00:00+00:00",
        completed_at="2025-01-01T00:00:01+00:00",
    )
    assert attempt.to_dict()["provider"] == "fake"
