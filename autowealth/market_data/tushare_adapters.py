"""Tushare Pro adapter for canonical unadjusted A-share equity EOD bars."""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from importlib import import_module
from typing import Callable, Optional, Protocol, Tuple

import pandas as pd

from .calendar import TradingCalendar, validate_trading_days
from .providers import (
    EODProviderCapability,
    EODProviderError,
    EODProviderErrorCode,
    EODProviderRequest,
    EODProviderResult,
    EODProviderResultStatus,
    EODRevisionStrategy,
    validate_eod_provider_request,
    validate_eod_provider_result,
)
from .schemas import (
    AdjustmentType,
    AssetType,
    BarFrequency,
    EODBar,
    Market,
    Venue,
)

_OS = import_module("os")
TUSHARE_TOKEN_ENVIRONMENT_VARIABLE = "TUSHARE_TOKEN"
_REQUIRED_COLUMNS = (
    "ts_code",
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "vol",
    "amount",
)
_FIELDS = ",".join(_REQUIRED_COLUMNS)
_VOLUME_LOTS_TO_SHARES = Decimal("100")
_AMOUNT_THOUSAND_CNY_TO_CNY = Decimal("1000")


class _TushareClient(Protocol):
    def daily(self, **kwargs: object) -> object: ...


TokenResolver = Callable[[], str]
ClientFactory = Callable[[str], _TushareClient]


_CAPABILITIES = (
    EODProviderCapability(
        Market.CN,
        Venue.SSE,
        AssetType.EQUITY,
        BarFrequency.DAILY,
        AdjustmentType.NONE,
        EODRevisionStrategy.APPEND_ONLY,
    ),
    EODProviderCapability(
        Market.CN,
        Venue.SZSE,
        AssetType.EQUITY,
        BarFrequency.DAILY,
        AdjustmentType.NONE,
        EODRevisionStrategy.APPEND_ONLY,
    ),
)

_TEMPORARY_EXCEPTION_TYPES = frozenset(
    {
        ("requests.exceptions", "ConnectionError"),
        ("requests.exceptions", "ConnectTimeout"),
        ("requests.exceptions", "ProxyError"),
        ("requests.exceptions", "ReadTimeout"),
        ("requests.exceptions", "Timeout"),
        ("urllib3.exceptions", "ConnectTimeoutError"),
        ("urllib3.exceptions", "MaxRetryError"),
        ("urllib3.exceptions", "NewConnectionError"),
        ("urllib3.exceptions", "ProtocolError"),
        ("urllib3.exceptions", "ProxyError"),
        ("urllib3.exceptions", "ReadTimeoutError"),
        ("urllib3.exceptions", "TimeoutError"),
    }
)
_TEMPORARY_RATE_LIMIT_MARKERS = (
    "rate limit",
    "too many requests",
    "访问频率",
    "每分钟最多访问",
    "频率限制",
)
_PERMANENT_MARKERS = (
    "authentication",
    "invalid token",
    "permission",
    "quota exhausted",
    "token无效",
    "token 无效",
    "无权限",
    "权限不足",
    "积分不足",
    "额度耗尽",
)


def _default_token_resolver() -> str:
    return _OS.getenv(TUSHARE_TOKEN_ENVIRONMENT_VARIABLE, "")


def _default_client_factory(token: str) -> _TushareClient:
    try:
        tushare = import_module("tushare")
    except ImportError:
        raise EODProviderError(
            EODProviderErrorCode.PROVIDER_UNAVAILABLE,
            "The Tushare client is unavailable.",
        ) from None
    factory = getattr(tushare, "pro_api", None)
    if not callable(factory):
        raise EODProviderError(
            EODProviderErrorCode.PROVIDER_UNAVAILABLE,
            "The Tushare client is unavailable.",
        )
    return factory(token)


def _token(resolver: TokenResolver) -> str:
    try:
        value = resolver()
    except EODProviderError:
        raise
    except Exception:
        raise EODProviderError(
            EODProviderErrorCode.PERMANENT_PROVIDER_FAILURE,
            "The Tushare credential is unavailable.",
        ) from None
    if type(value) is not str or not value.strip() or "\x00" in value or len(value) > 4096:
        raise EODProviderError(
            EODProviderErrorCode.PERMANENT_PROVIDER_FAILURE,
            "The Tushare credential is unavailable.",
        )
    return value.strip()


def _is_temporary_exception(exc: Exception) -> bool:
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return True
    return any(
        (error_type.__module__, error_type.__name__) in _TEMPORARY_EXCEPTION_TYPES
        for error_type in type(exc).__mro__
    )


def _classify_client_exception(exc: Exception) -> EODProviderError:
    if _is_temporary_exception(exc):
        return EODProviderError(
            EODProviderErrorCode.TEMPORARY_PROVIDER_FAILURE,
            "The Tushare daily endpoint failed temporarily for this request.",
        )
    text = str(exc).casefold()
    if any(marker in text for marker in _TEMPORARY_RATE_LIMIT_MARKERS):
        return EODProviderError(
            EODProviderErrorCode.TEMPORARY_PROVIDER_FAILURE,
            "The Tushare daily endpoint is temporarily rate limited.",
        )
    if any(marker in text for marker in _PERMANENT_MARKERS):
        return EODProviderError(
            EODProviderErrorCode.PERMANENT_PROVIDER_FAILURE,
            "The Tushare request is not authorized for this operation.",
        )
    return EODProviderError(
        EODProviderErrorCode.PROVIDER_UNAVAILABLE,
        "The Tushare daily endpoint is unavailable for this request.",
    )


def _expected_trading_days(
    calendar: TradingCalendar,
    request: EODProviderRequest,
) -> Tuple[date, ...]:
    try:
        expected = validate_trading_days(calendar, request.requested_range)
    except Exception as exc:
        raise EODProviderError(
            EODProviderErrorCode.MALFORMED_PROVIDER_PAYLOAD,
            "The trading calendar could not validate the Tushare request.",
        ) from exc
    if not expected:
        raise EODProviderError(
            EODProviderErrorCode.UNSUPPORTED_REQUEST,
            "The Tushare request must contain at least one trading day.",
        )
    return expected


def _decimal(value: object, field_name: str) -> Decimal:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a finite decimal number")
    try:
        text = str(value).strip()
        parsed = Decimal(text)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a finite decimal number") from exc
    if not text or not parsed.is_finite():
        raise ValueError(f"{field_name} must be a finite decimal number")
    return parsed


def _trade_date(value: object) -> date:
    if type(value) is not str or len(value) != 8 or not value.isascii() or not value.isdigit():
        raise ValueError("trade_date must use the exact YYYYMMDD form")
    try:
        return date(int(value[:4]), int(value[4:6]), int(value[6:]))
    except ValueError as exc:
        raise ValueError("trade_date must be a valid calendar date") from exc


def _symbol(value: object, expected: str) -> str:
    if type(value) is not str:
        raise ValueError("ts_code must be text")
    normalized = value.strip().upper()
    if normalized != expected:
        raise ValueError("ts_code does not match the requested canonical symbol")
    return normalized


def _frame_to_bars(frame: object, request: EODProviderRequest) -> Tuple[EODBar, ...]:
    if type(frame) is not pd.DataFrame:
        raise EODProviderError(
            EODProviderErrorCode.MALFORMED_PROVIDER_PAYLOAD,
            "The Tushare payload must be an exact pandas DataFrame.",
        )
    isolated = frame.copy(deep=True)
    if isolated.empty:
        return ()
    columns = tuple(isolated.columns)
    if any(type(column) is not str for column in columns) or len(set(columns)) != len(columns):
        raise EODProviderError(
            EODProviderErrorCode.MALFORMED_PROVIDER_PAYLOAD,
            "The Tushare payload contains invalid or duplicate columns.",
        )
    if any(column not in columns for column in _REQUIRED_COLUMNS):
        raise EODProviderError(
            EODProviderErrorCode.MALFORMED_PROVIDER_PAYLOAD,
            "The Tushare payload is missing a required daily field.",
        )

    bars = []
    try:
        for row_number in range(len(isolated.index)):
            row = isolated.iloc[row_number]
            _symbol(row["ts_code"], request.dataset.canonical_symbol)
            trade_date = _trade_date(row["trade_date"])
            if not request.requested_range.contains(trade_date):
                raise ValueError("trade_date is outside the requested range")
            bars.append(
                EODBar(
                    dataset=request.dataset,
                    trade_date=trade_date,
                    open=_decimal(row["open"], "open"),
                    high=_decimal(row["high"], "high"),
                    low=_decimal(row["low"], "low"),
                    close=_decimal(row["close"], "close"),
                    volume=_decimal(row["vol"], "vol") * _VOLUME_LOTS_TO_SHARES,
                    amount=(_decimal(row["amount"], "amount") * _AMOUNT_THOUSAND_CNY_TO_CNY),
                )
            )
    except EODProviderError:
        raise
    except (KeyError, TypeError, ValueError):
        raise EODProviderError(
            EODProviderErrorCode.MALFORMED_PROVIDER_PAYLOAD,
            "The Tushare payload failed canonical daily-bar conversion.",
        ) from None
    return tuple(bars)


def _result_status(
    bars: Tuple[EODBar, ...],
    expected_dates: Tuple[date, ...],
) -> EODProviderResultStatus:
    if not bars:
        return EODProviderResultStatus.EMPTY
    observed_dates = tuple(sorted(bar.trade_date for bar in bars))
    return (
        EODProviderResultStatus.SUCCESS
        if observed_dates == expected_dates
        else EODProviderResultStatus.PARTIAL_SUCCESS
    )


class TushareEODEquityProvider:
    """Single-endpoint Tushare adapter with lazy credentials and client construction."""

    provider_name = "tushare_eod_equity"
    provider_version = "1"
    endpoint_name = "daily"

    def __init__(
        self,
        calendar: TradingCalendar,
        *,
        token_resolver: Optional[TokenResolver] = None,
        client_factory: Optional[ClientFactory] = None,
    ) -> None:
        if not isinstance(calendar, TradingCalendar):
            raise TypeError("calendar must implement TradingCalendar")
        if token_resolver is not None and not callable(token_resolver):
            raise TypeError("token_resolver must be callable or None")
        if client_factory is not None and not callable(client_factory):
            raise TypeError("client_factory must be callable or None")
        self._calendar = calendar
        self._token_resolver = token_resolver or _default_token_resolver
        self._client_factory = client_factory or _default_client_factory

    @property
    def capabilities(self) -> Tuple[EODProviderCapability, ...]:
        return _CAPABILITIES

    def fetch(self, request: EODProviderRequest) -> EODProviderResult:
        """Fetch one dataset/range without retry, fallback, persistence or publication."""

        if type(request) is not EODProviderRequest:
            raise TypeError("request must be an exact EODProviderRequest")
        validate_eod_provider_request(request, self.capabilities)
        expected_dates = _expected_trading_days(self._calendar, request)

        try:
            client = self._client_factory(_token(self._token_resolver))
            endpoint = getattr(client, self.endpoint_name, None)
            if not callable(endpoint):
                raise EODProviderError(
                    EODProviderErrorCode.PROVIDER_UNAVAILABLE,
                    "The Tushare daily endpoint is unavailable.",
                )
            frame = endpoint(
                ts_code=request.dataset.canonical_symbol,
                start_date=request.requested_range.start_date.strftime("%Y%m%d"),
                end_date=request.requested_range.end_date.strftime("%Y%m%d"),
                fields=_FIELDS,
            )
        except EODProviderError:
            raise
        except Exception as exc:
            raise _classify_client_exception(exc) from None

        bars = _frame_to_bars(frame, request)
        result = EODProviderResult(
            request=request,
            provider_name=self.provider_name,
            provider_version=self.provider_version,
            status=_result_status(bars, expected_dates),
            bars=bars,
        )
        return validate_eod_provider_result(result, self._calendar)


__all__ = [
    "ClientFactory",
    "TUSHARE_TOKEN_ENVIRONMENT_VARIABLE",
    "TokenResolver",
    "TushareEODEquityProvider",
]
