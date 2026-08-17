"""Offline-testable AKShare adapters for canonical China EOD datasets."""

from __future__ import annotations

from datetime import date
from importlib import import_module
from typing import Callable, Optional, Tuple

import pandas as pd

from .calendar import TradingCalendar, validate_trading_days
from .dataframe_conversion import (
    _parse_trade_date,
    _resolve_columns,
    convert_eod_dataframe_to_bars,
)
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
    EODDatasetKey,
    EODDateRange,
    Market,
    Venue,
)

_Endpoint = Callable[..., object]

_REQUESTS_EXCEPTIONS_MODULE = ".".join(("requests", "exceptions"))
_URLLIB3_EXCEPTIONS_MODULE = ".".join(("urllib3", "exceptions"))
_TEMPORARY_ENDPOINT_EXCEPTION_TYPES = frozenset(
    {
        (_REQUESTS_EXCEPTIONS_MODULE, "ConnectionError"),
        (_REQUESTS_EXCEPTIONS_MODULE, "ConnectTimeout"),
        (_REQUESTS_EXCEPTIONS_MODULE, "ProxyError"),
        (_REQUESTS_EXCEPTIONS_MODULE, "ReadTimeout"),
        (_REQUESTS_EXCEPTIONS_MODULE, "Timeout"),
        (_URLLIB3_EXCEPTIONS_MODULE, "ConnectTimeoutError"),
        (_URLLIB3_EXCEPTIONS_MODULE, "MaxRetryError"),
        (_URLLIB3_EXCEPTIONS_MODULE, "NewConnectionError"),
        (_URLLIB3_EXCEPTIONS_MODULE, "ProtocolError"),
        (_URLLIB3_EXCEPTIONS_MODULE, "ProxyError"),
        (_URLLIB3_EXCEPTIONS_MODULE, "ReadTimeoutError"),
        (_URLLIB3_EXCEPTIONS_MODULE, "TimeoutError"),
    }
)

_EQUITY_CAPABILITIES = (
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
        Venue.SSE,
        AssetType.EQUITY,
        BarFrequency.DAILY,
        AdjustmentType.QFQ,
        EODRevisionStrategy.FULL_REFRESH_REQUIRED,
    ),
    EODProviderCapability(
        Market.CN,
        Venue.SSE,
        AssetType.EQUITY,
        BarFrequency.DAILY,
        AdjustmentType.HFQ,
        EODRevisionStrategy.FULL_REFRESH_REQUIRED,
    ),
    EODProviderCapability(
        Market.CN,
        Venue.SZSE,
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
        AdjustmentType.QFQ,
        EODRevisionStrategy.FULL_REFRESH_REQUIRED,
    ),
    EODProviderCapability(
        Market.CN,
        Venue.SZSE,
        AssetType.EQUITY,
        BarFrequency.DAILY,
        AdjustmentType.HFQ,
        EODRevisionStrategy.FULL_REFRESH_REQUIRED,
    ),
)

_INDEX_CAPABILITIES = (
    EODProviderCapability(
        Market.CN,
        Venue.SSE,
        AssetType.INDEX,
        BarFrequency.DAILY,
        AdjustmentType.NONE,
        EODRevisionStrategy.APPEND_ONLY,
    ),
    EODProviderCapability(
        Market.CN,
        Venue.SZSE,
        AssetType.INDEX,
        BarFrequency.DAILY,
        AdjustmentType.NONE,
        EODRevisionStrategy.APPEND_ONLY,
    ),
)

_INDEX_SYMBOLS = {
    "000300.SH": "000300",
    "000905.SH": "000905",
    "000852.SH": "000852",
    "000001.SH": "000001",
    "399001.SZ": "399001",
    "399006.SZ": "399006",
}

_EQUITY_ADJUSTMENTS = {
    AdjustmentType.NONE: "",
    AdjustmentType.QFQ: "qfq",
    AdjustmentType.HFQ: "hfq",
}


def _unsupported(message: str) -> EODProviderError:
    return EODProviderError(EODProviderErrorCode.UNSUPPORTED_REQUEST, message)


def akshare_equity_symbol(dataset: EODDatasetKey) -> str:
    """Return the six-digit AKShare symbol for one canonical equity dataset."""

    if type(dataset) is not EODDatasetKey:
        raise TypeError("dataset must be an exact EODDatasetKey")
    if (
        dataset.market is not Market.CN
        or dataset.asset_type is not AssetType.EQUITY
        or dataset.frequency is not BarFrequency.DAILY
        or dataset.venue not in (Venue.SSE, Venue.SZSE)
    ):
        raise _unsupported("AKShare equity data does not support the requested dataset.")
    return dataset.canonical_symbol[:6]


def akshare_index_symbol(dataset: EODDatasetKey) -> str:
    """Return the frozen AKShare symbol for one supported canonical index dataset."""

    if type(dataset) is not EODDatasetKey:
        raise TypeError("dataset must be an exact EODDatasetKey")
    if (
        dataset.market is not Market.CN
        or dataset.asset_type is not AssetType.INDEX
        or dataset.frequency is not BarFrequency.DAILY
        or dataset.adjustment_type is not AdjustmentType.NONE
    ):
        raise _unsupported("AKShare index data does not support the requested dataset.")
    try:
        return _INDEX_SYMBOLS[dataset.canonical_symbol]
    except KeyError as exc:
        raise _unsupported("AKShare index data does not support the requested symbol.") from exc


def akshare_index_daily_symbol(dataset: EODDatasetKey) -> str:
    """Return the exchange-prefixed symbol for AKShare index daily history."""

    symbol = akshare_index_symbol(dataset)
    prefix = "sh" if dataset.venue is Venue.SSE else "sz"
    return f"{prefix}{symbol}"


def _expected_trading_days(
    calendar: TradingCalendar,
    request: EODProviderRequest,
) -> Tuple[date, ...]:
    try:
        expected_dates = validate_trading_days(calendar, request.requested_range)
    except Exception as exc:
        raise EODProviderError(
            EODProviderErrorCode.MALFORMED_PROVIDER_PAYLOAD,
            "The trading calendar could not validate the EOD provider request.",
        ) from exc
    if not expected_dates:
        raise _unsupported("The EOD provider request must contain at least one trading day.")
    return expected_dates


def _result_status(
    bars: Tuple[EODBar, ...],
    expected_dates: Tuple[date, ...],
) -> EODProviderResultStatus:
    if not bars:
        return EODProviderResultStatus.EMPTY
    observed_dates = tuple(bar.trade_date for bar in bars)
    return (
        EODProviderResultStatus.SUCCESS
        if observed_dates == expected_dates
        else EODProviderResultStatus.PARTIAL_SUCCESS
    )


def _is_temporary_endpoint_failure(exc: Exception) -> bool:
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return True
    return any(
        (error_type.__module__, error_type.__name__) in _TEMPORARY_ENDPOINT_EXCEPTION_TYPES
        for error_type in type(exc).__mro__
    )


class AKShareEODEquityProvider:
    """Single-endpoint AKShare adapter for canonical A-share equity EOD bars."""

    provider_name = "akshare_eod_equity"
    provider_version = "1"
    endpoint_name = "stock_zh_a_hist"

    def __init__(
        self,
        calendar: TradingCalendar,
        endpoint: Optional[_Endpoint] = None,
    ) -> None:
        if not isinstance(calendar, TradingCalendar):
            raise TypeError("calendar must implement TradingCalendar")
        if endpoint is not None and not callable(endpoint):
            raise TypeError("endpoint must be callable or None")
        self._calendar = calendar
        self._endpoint_callable = endpoint

    @property
    def capabilities(self) -> Tuple[EODProviderCapability, ...]:
        """Return the six immutable equity capabilities in stable order."""

        return _EQUITY_CAPABILITIES

    def fetch(self, request: EODProviderRequest) -> EODProviderResult:
        """Fetch and validate one equity EOD request without retry or persistence."""

        if type(request) is not EODProviderRequest:
            raise TypeError("request must be an exact EODProviderRequest")
        validate_eod_provider_request(request, self.capabilities)
        expected_dates = _expected_trading_days(self._calendar, request)
        symbol = akshare_equity_symbol(request.dataset)
        endpoint = self._resolve_endpoint()
        try:
            frame = endpoint(
                symbol=symbol,
                period="daily",
                start_date=request.requested_range.start_date.strftime("%Y%m%d"),
                end_date=request.requested_range.end_date.strftime("%Y%m%d"),
                adjust=_EQUITY_ADJUSTMENTS[request.dataset.adjustment_type],
            )
        except EODProviderError:
            raise
        except (TimeoutError, ConnectionError) as exc:
            raise EODProviderError(
                EODProviderErrorCode.TEMPORARY_PROVIDER_FAILURE,
                "The AKShare equity endpoint failed temporarily for this request.",
            ) from exc
        except Exception as exc:
            if _is_temporary_endpoint_failure(exc):
                raise EODProviderError(
                    EODProviderErrorCode.TEMPORARY_PROVIDER_FAILURE,
                    "The AKShare equity endpoint failed temporarily for this request.",
                ) from exc
            raise EODProviderError(
                EODProviderErrorCode.PROVIDER_UNAVAILABLE,
                "The AKShare equity endpoint is unavailable for this request.",
            ) from exc
        bars = convert_eod_dataframe_to_bars(
            frame,
            request.dataset,
            request.requested_range,
        )
        result = EODProviderResult(
            request=request,
            provider_name=self.provider_name,
            provider_version=self.provider_version,
            status=_result_status(bars, expected_dates),
            bars=bars,
        )
        return validate_eod_provider_result(result, self._calendar)

    def _resolve_endpoint(self) -> _Endpoint:
        if self._endpoint_callable is not None:
            return self._endpoint_callable
        try:
            ak = import_module("akshare")
        except ImportError as exc:
            raise EODProviderError(
                EODProviderErrorCode.PROVIDER_UNAVAILABLE,
                "The AKShare equity endpoint is unavailable.",
            ) from exc
        endpoint = getattr(ak, "stock_zh_a_hist", None)
        if not callable(endpoint):
            raise EODProviderError(
                EODProviderErrorCode.PROVIDER_UNAVAILABLE,
                "The AKShare equity endpoint is unavailable.",
            )
        self._endpoint_callable = endpoint
        return endpoint


class AKShareEODIndexProvider:
    """Single-endpoint AKShare adapter for supported canonical index EOD bars."""

    provider_name = "akshare_eod_index"
    provider_version = "1"
    endpoint_name = "index_zh_a_hist"

    def __init__(
        self,
        calendar: TradingCalendar,
        endpoint: Optional[_Endpoint] = None,
    ) -> None:
        if not isinstance(calendar, TradingCalendar):
            raise TypeError("calendar must implement TradingCalendar")
        if endpoint is not None and not callable(endpoint):
            raise TypeError("endpoint must be callable or None")
        self._calendar = calendar
        self._endpoint_callable = endpoint

    @property
    def capabilities(self) -> Tuple[EODProviderCapability, ...]:
        """Return the two immutable index capabilities in stable order."""

        return _INDEX_CAPABILITIES

    def fetch(self, request: EODProviderRequest) -> EODProviderResult:
        """Fetch and validate one index EOD request without fallback or persistence."""

        if type(request) is not EODProviderRequest:
            raise TypeError("request must be an exact EODProviderRequest")
        validate_eod_provider_request(request, self.capabilities)
        expected_dates = _expected_trading_days(self._calendar, request)
        symbol = akshare_index_symbol(request.dataset)
        endpoint = self._resolve_endpoint()
        try:
            frame = endpoint(
                symbol=symbol,
                period="daily",
                start_date=request.requested_range.start_date.strftime("%Y%m%d"),
                end_date=request.requested_range.end_date.strftime("%Y%m%d"),
            )
        except EODProviderError:
            raise
        except (TimeoutError, ConnectionError) as exc:
            raise EODProviderError(
                EODProviderErrorCode.TEMPORARY_PROVIDER_FAILURE,
                "The AKShare index endpoint failed temporarily for this request.",
            ) from exc
        except Exception as exc:
            if _is_temporary_endpoint_failure(exc):
                raise EODProviderError(
                    EODProviderErrorCode.TEMPORARY_PROVIDER_FAILURE,
                    "The AKShare index endpoint failed temporarily for this request.",
                ) from exc
            raise EODProviderError(
                EODProviderErrorCode.PROVIDER_UNAVAILABLE,
                "The AKShare index endpoint is unavailable for this request.",
            ) from exc
        bars = convert_eod_dataframe_to_bars(
            frame,
            request.dataset,
            request.requested_range,
        )
        result = EODProviderResult(
            request=request,
            provider_name=self.provider_name,
            provider_version=self.provider_version,
            status=_result_status(bars, expected_dates),
            bars=bars,
        )
        return validate_eod_provider_result(result, self._calendar)

    def _resolve_endpoint(self) -> _Endpoint:
        if self._endpoint_callable is not None:
            return self._endpoint_callable
        try:
            ak = import_module("akshare")
        except ImportError as exc:
            raise EODProviderError(
                EODProviderErrorCode.PROVIDER_UNAVAILABLE,
                "The AKShare index endpoint is unavailable.",
            ) from exc
        endpoint = getattr(ak, "index_zh_a_hist", None)
        if not callable(endpoint):
            raise EODProviderError(
                EODProviderErrorCode.PROVIDER_UNAVAILABLE,
                "The AKShare index endpoint is unavailable.",
            )
        self._endpoint_callable = endpoint
        return endpoint


class AKShareEODIndexDailyProvider:
    """Independent fallback adapter for full-history AKShare index daily data."""

    provider_name = "akshare_eod_index_daily"
    provider_version = "1"
    endpoint_name = "stock_zh_index_daily"

    def __init__(
        self,
        calendar: TradingCalendar,
        endpoint: Optional[_Endpoint] = None,
    ) -> None:
        if not isinstance(calendar, TradingCalendar):
            raise TypeError("calendar must implement TradingCalendar")
        if endpoint is not None and not callable(endpoint):
            raise TypeError("endpoint must be callable or None")
        self._calendar = calendar
        self._endpoint_callable = endpoint

    @property
    def capabilities(self) -> Tuple[EODProviderCapability, ...]:
        """Return the two immutable unadjusted index capabilities."""

        return _INDEX_CAPABILITIES

    def fetch(self, request: EODProviderRequest) -> EODProviderResult:
        """Fetch full index history and strictly filter the requested range locally."""

        if type(request) is not EODProviderRequest:
            raise TypeError("request must be an exact EODProviderRequest")
        validate_eod_provider_request(request, self.capabilities)
        expected_dates = _expected_trading_days(self._calendar, request)
        symbol = akshare_index_daily_symbol(request.dataset)
        endpoint = self._resolve_endpoint()
        try:
            frame = endpoint(symbol=symbol)
        except EODProviderError:
            raise
        except (TimeoutError, ConnectionError) as exc:
            raise EODProviderError(
                EODProviderErrorCode.TEMPORARY_PROVIDER_FAILURE,
                "The AKShare index daily endpoint failed temporarily for this request.",
            ) from exc
        except Exception as exc:
            if _is_temporary_endpoint_failure(exc):
                raise EODProviderError(
                    EODProviderErrorCode.TEMPORARY_PROVIDER_FAILURE,
                    "The AKShare index daily endpoint failed temporarily for this request.",
                ) from exc
            raise EODProviderError(
                EODProviderErrorCode.PROVIDER_UNAVAILABLE,
                "The AKShare index daily endpoint is unavailable for this request.",
            ) from exc
        filtered = _filter_index_daily_frame(frame, request.requested_range)
        bars = convert_eod_dataframe_to_bars(
            filtered,
            request.dataset,
            request.requested_range,
        )
        result = EODProviderResult(
            request=request,
            provider_name=self.provider_name,
            provider_version=self.provider_version,
            status=_result_status(bars, expected_dates),
            bars=bars,
        )
        return validate_eod_provider_result(result, self._calendar)

    def _resolve_endpoint(self) -> _Endpoint:
        if self._endpoint_callable is not None:
            return self._endpoint_callable
        try:
            ak = import_module("akshare")
            endpoint = getattr(ak, "stock_zh_index_daily", None)
        except Exception as exc:
            raise EODProviderError(
                EODProviderErrorCode.PROVIDER_UNAVAILABLE,
                "The AKShare index daily endpoint is unavailable.",
            ) from exc
        if not callable(endpoint):
            raise EODProviderError(
                EODProviderErrorCode.PROVIDER_UNAVAILABLE,
                "The AKShare index daily endpoint is unavailable.",
            )
        self._endpoint_callable = endpoint
        return endpoint


def _filter_index_daily_frame(
    frame: object,
    requested_range: EODDateRange,
) -> pd.DataFrame:
    if type(frame) is not pd.DataFrame:
        raise EODProviderError(
            EODProviderErrorCode.MALFORMED_PROVIDER_PAYLOAD,
            "The provider payload must be an exact pandas DataFrame.",
        )
    isolated = frame.copy(deep=True)
    if isolated.empty:
        return pd.DataFrame()

    columns = _resolve_columns(isolated)
    date_column = columns["date"]
    if date_column is None:  # pragma: no cover - _resolve_columns requires a date.
        raise EODProviderError(
            EODProviderErrorCode.MALFORMED_PROVIDER_PAYLOAD,
            "The provider payload is missing a required EOD column.",
        )
    unrestricted_range = EODDateRange(date.min, date.max)
    parsed_dates = tuple(
        _parse_trade_date(isolated.iloc[row_number][date_column], unrestricted_range)
        for row_number in range(len(isolated.index))
    )
    mask = [requested_range.contains(trade_date) for trade_date in parsed_dates]
    return isolated.loc[mask].copy(deep=True).reset_index(drop=True)


__all__ = [
    "AKShareEODEquityProvider",
    "AKShareEODIndexDailyProvider",
    "AKShareEODIndexProvider",
    "akshare_equity_symbol",
    "akshare_index_daily_symbol",
    "akshare_index_symbol",
]
