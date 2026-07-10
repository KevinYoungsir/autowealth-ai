"""Point-in-time real-data research pipeline."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional, Union

import pandas as pd
import yaml

from autowealth.backtest import PortfolioBacktester, generate_rebalance_dates
from autowealth.backtest.metrics import (
    annualized_return,
    calmar_ratio,
    daily_returns,
    max_drawdown,
    sharpe_ratio,
    total_return,
    volatility,
)
from autowealth.data.ashare_provider import AShareDataProvider
from autowealth.data.cache import ParquetCache
from autowealth.data.fundamental_provider import (
    AShareFundamentalProvider,
    FundamentalProviderResult,
)
from autowealth.data.fundamental_schema import (
    FundamentalRecord,
    latest_fundamental_asof,
    normalize_fundamental_data,
)
from autowealth.data.index_provider import AShareIndexProvider
from autowealth.data.quality import check_price_quality
from autowealth.data.universe import FixedStockUniverse, UniverseSnapshot
from autowealth.factors import (
    combine_factor_scores,
    low_vol_factor,
    momentum_factor,
    overbought_oversold_factor,
    quality_factor,
    value_factor,
)
from autowealth.factors.schema import CompositeFactorScore, FactorScore
from autowealth.macro.asof import load_macro_asof_csv, select_macro_asof
from autowealth.macro.scoring import score_macro_environment
from autowealth.portfolio import PortfolioConstraints, StockCandidate, build_factor_portfolio
from autowealth.research.artifacts import (
    ResearchArtifactSet,
    current_git_commit,
    write_research_artifacts,
)
from autowealth.research.schema import scalar_metrics


PathLike = Union[str, Path]
SUPPORTED_REBALANCE_FREQUENCIES = {"yearly", "five_year"}
SUPPORTED_FACTOR_NAMES = {
    "value",
    "quality",
    "momentum",
    "low_vol",
    "overbought_oversold",
}
REQUIRED_CONFIG_KEYS = {
    "start_date",
    "end_date",
    "candidate_symbols",
    "rebalance_frequency",
    "initial_capital",
    "commission",
    "stamp_tax",
    "slippage",
    "factor_weights",
    "portfolio_constraints",
    "benchmark_symbols",
    "macro_csv_path",
    "cache_directory",
    "output_directory",
}


class RealResearchError(RuntimeError):
    """Base error for one real-data research run."""


class RealDataAccessError(RealResearchError):
    """Raised when required external market data is unavailable."""


@dataclass(frozen=True)
class RealResearchConfig:
    experiment_name: str
    start_date: str
    end_date: str
    candidate_symbols: list[str]
    rebalance_frequency: str
    initial_capital: float
    commission: float
    stamp_tax: float
    slippage: float
    factor_weights: dict[str, float]
    portfolio_constraints: PortfolioConstraints
    benchmark_symbols: list[str]
    macro_csv_path: Path
    cache_directory: Path
    output_directory: Path
    price_adjust: str = "none"

    def to_dict(self) -> dict[str, object]:
        values = asdict(self)
        values["macro_csv_path"] = str(self.macro_csv_path)
        values["cache_directory"] = str(self.cache_directory)
        values["output_directory"] = str(self.output_directory)
        return values


@dataclass
class RealResearchResult:
    run_id: str
    run_directory: Path
    config: RealResearchConfig
    metrics: dict[str, Any]
    benchmark_metrics: dict[str, dict[str, Any]]
    equity_curve: pd.Series
    benchmark_curve: pd.DataFrame
    target_weights_by_date: dict[str, dict[str, float]]
    factor_snapshots: pd.DataFrame
    warnings: list[str]
    artifacts: ResearchArtifactSet


def load_real_research_config(path: PathLike) -> RealResearchConfig:
    """Parse and validate one deterministic YAML research configuration."""
    config_path = Path(path).resolve()
    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise RealResearchError(f"unable to read research config {config_path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise RealResearchError(f"invalid YAML in research config {config_path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise RealResearchError("research config must be a YAML mapping")

    missing = sorted(REQUIRED_CONFIG_KEYS - set(raw))
    if missing:
        raise RealResearchError(f"research config missing required keys: {missing}")

    root = _repository_root(config_path)
    try:
        config = RealResearchConfig(
            experiment_name=str(raw.get("experiment_name", config_path.stem)),
            start_date=_date_string(raw["start_date"]),
            end_date=_date_string(raw["end_date"]),
            candidate_symbols=_symbols(raw["candidate_symbols"]),
            rebalance_frequency=str(raw["rebalance_frequency"]).lower(),
            initial_capital=float(raw["initial_capital"]),
            commission=float(raw["commission"]),
            stamp_tax=float(raw["stamp_tax"]),
            slippage=float(raw["slippage"]),
            factor_weights={
                str(name): float(weight)
                for name, weight in dict(raw["factor_weights"]).items()
            },
            portfolio_constraints=PortfolioConstraints(
                **dict(raw["portfolio_constraints"])
            ),
            benchmark_symbols=_symbols(raw["benchmark_symbols"]),
            macro_csv_path=_resolve_config_path(raw["macro_csv_path"], root),
            cache_directory=_resolve_config_path(raw["cache_directory"], root),
            output_directory=_resolve_config_path(raw["output_directory"], root),
            price_adjust=str(raw.get("price_adjust", "none")).lower(),
        )
    except (TypeError, ValueError) as exc:
        raise RealResearchError(f"invalid research config value: {exc}") from exc
    _validate_config(config)
    return config


def _validate_config(config: RealResearchConfig) -> None:
    if pd.Timestamp(config.start_date) > pd.Timestamp(config.end_date):
        raise RealResearchError("start_date cannot be after end_date")
    if config.rebalance_frequency not in SUPPORTED_REBALANCE_FREQUENCIES:
        raise RealResearchError("rebalance_frequency must be yearly or five_year")
    if config.initial_capital <= 0:
        raise RealResearchError("initial_capital must be positive")
    if any(value < 0 for value in (config.commission, config.stamp_tax, config.slippage)):
        raise RealResearchError("transaction costs must be non-negative")
    unknown = set(config.factor_weights) - SUPPORTED_FACTOR_NAMES
    if unknown:
        raise RealResearchError(f"unsupported factor weights: {sorted(unknown)}")
    if not config.factor_weights or any(weight < 0 for weight in config.factor_weights.values()):
        raise RealResearchError("factor_weights must be non-empty and non-negative")
    if sum(config.factor_weights.values()) <= 0:
        raise RealResearchError("factor weight sum must be positive")
    if config.price_adjust not in {"none", "qfq", "hfq"}:
        raise RealResearchError("price_adjust must be none, qfq or hfq")


def _repository_root(path: Path) -> Path:
    start = path if path.is_dir() else path.parent
    for candidate in (start, *start.parents):
        if (candidate / "pyproject.toml").exists():
            return candidate
    return Path.cwd().resolve()


def _resolve_config_path(value: object, root: Path) -> Path:
    path = Path(str(value))
    return path if path.is_absolute() else (root / path).resolve()


def _date_string(value: object) -> str:
    return pd.Timestamp(value).strftime("%Y-%m-%d")


def _symbols(values: object) -> list[str]:
    if not isinstance(values, list):
        raise ValueError("symbol fields must be YAML lists")
    symbols = list(
        dict.fromkeys(str(value).strip() for value in values if str(value).strip())
    )
    if not symbols:
        raise ValueError("symbol list cannot be empty")
    return symbols


def _universe_snapshot(provider: object, as_of_date: str) -> UniverseSnapshot:
    if not hasattr(provider, "get_universe"):
        raise RealResearchError("universe provider must define get_universe(as_of_date)")
    value = provider.get_universe(as_of_date)
    if isinstance(value, UniverseSnapshot):
        return value
    if isinstance(value, (list, tuple, set)):
        return UniverseSnapshot(
            as_of_date=as_of_date,
            symbols=_symbols(list(value)),
            source=provider.__class__.__name__,
            point_in_time=False,
            warnings=["universe provider did not declare point-in-time status"],
        )
    raise RealResearchError("universe provider returned an unsupported value")


def _load_macro_data(
    config: RealResearchConfig,
    provider: Optional[object],
) -> tuple[pd.DataFrame, str, list[str]]:
    source = "local_csv" if provider is None else provider.__class__.__name__
    try:
        if provider is None:
            data = load_macro_asof_csv(config.macro_csv_path)
        elif hasattr(provider, "get_macro_data"):
            data = provider.get_macro_data(config.start_date, config.end_date)
        elif callable(provider):
            data = provider(config.start_date, config.end_date)
        else:
            raise TypeError("macro provider must define get_macro_data or be callable")
    except Exception as exc:
        return pd.DataFrame(), source, [f"macro provider failed: {exc}"]

    frame = pd.DataFrame(data).copy()
    if frame.empty:
        return frame, source, ["macro source contains no real observations"]
    return frame, source, []


def _macro_asof(
    macro_data: pd.DataFrame,
    rebalance_date: pd.Timestamp,
) -> tuple[Optional[object], float, Optional[str], list[str]]:
    date_text = rebalance_date.strftime("%Y-%m-%d")
    if macro_data.empty:
        return None, 1.0, None, [
            f"no point-in-time macro data for {date_text}; neutral multiplier used"
        ]

    selection = select_macro_asof(macro_data, rebalance_date)
    if selection.record is None:
        return None, 1.0, None, selection.warnings + [
            f"neutral macro multiplier used for {date_text}"
        ]

    indicator_names = [
        "pmi",
        "cpi_yoy",
        "ppi_yoy",
        "m2_yoy",
        "social_financing_yoy",
        "ten_year_yield",
        "usd_cny",
        "policy_score",
        "external_risk_score",
    ]
    indicators = {name: selection.record.get(name) for name in indicator_names}
    score = score_macro_environment(indicators, as_of_date=date_text)
    available_date = str(selection.record.get("available_date"))
    return (
        score,
        score.equity_position_multiplier,
        available_date,
        selection.warnings + list(score.warnings),
    )


def _future_fundamental_warnings(
    symbol: str,
    data: pd.DataFrame,
    rebalance_date: pd.Timestamp,
) -> list[str]:
    if data.empty:
        return [f"{symbol} has no point-in-time fundamental records"]
    normalized = normalize_fundamental_data(data)
    available = normalized["available_date"]
    report_date = normalized["report_date"]
    missing = int(available.isna().sum())
    future_available = int((available > rebalance_date).fillna(False).sum())
    future_reports = int((report_date > rebalance_date).fillna(False).sum())
    warnings: list[str] = []
    if missing:
        warnings.append(
            f"{symbol} ignored {missing} fundamental rows without available_date"
        )
    if future_available:
        warnings.append(
            f"{symbol} ignored {future_available} rows published after {rebalance_date.date()}"
        )
    if future_reports:
        warnings.append(
            f"{symbol} ignored {future_reports} future-report rows at {rebalance_date.date()}"
        )
    return warnings


def _prepare_price_frame(
    data: pd.DataFrame,
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    frame = pd.DataFrame(data).copy()
    if "date" not in frame.columns or "close" not in frame.columns:
        raise ValueError("price data requires date and close columns")
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
    if "volume" not in frame.columns:
        frame["volume"] = pd.NA
    frame["volume"] = pd.to_numeric(frame["volume"], errors="coerce")
    frame = frame[
        frame["date"].between(
            pd.Timestamp(start_date), pd.Timestamp(end_date), inclusive="both"
        )
    ]
    frame = frame.dropna(subset=["date", "close"])
    frame = frame[frame["close"] > 0]
    return frame.sort_values("date").drop_duplicates("date", keep="last").reset_index(drop=True)


def _aligned_trading_dates(
    price_data: Mapping[str, pd.DataFrame],
    start_date: str,
    end_date: str,
) -> pd.DatetimeIndex:
    closes = {
        symbol: _prepare_price_frame(frame, start_date, end_date)
        .set_index("date")["close"]
        for symbol, frame in price_data.items()
    }
    matrix = pd.concat(closes, axis=1).sort_index().ffill().dropna(how="any")
    if matrix.empty:
        raise RealResearchError("price matrix is empty after candidate alignment")
    return pd.DatetimeIndex(matrix.index)


def _tradability_warnings(
    symbol: str,
    data: pd.DataFrame,
    rebalance_date: pd.Timestamp,
) -> list[str]:
    day = data[data["date"] == rebalance_date]
    if day.empty:
        return [f"{symbol} has no bar on rebalance date {rebalance_date.date()}"]
    volume = pd.to_numeric(day["volume"], errors="coerce")
    if volume.isna().all():
        return [f"{symbol} tradability unknown on {rebalance_date.date()}: volume missing"]
    if (volume <= 0).any():
        return [f"{symbol} may be suspended or untradeable on {rebalance_date.date()}"]
    return []


def _safe_part(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z_.-]+", "_", str(value).strip())


def _compact_date(value: str) -> str:
    return pd.Timestamp(value).strftime("%Y%m%d")


def _sha256(path: Path) -> str:
    if not path.exists():
        return ""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _metadata_path(cache_path: Path) -> Path:
    return cache_path.with_suffix(".meta.json")


def _write_cache_metadata(cache_path: Path, metadata: Mapping[str, object]) -> None:
    _metadata_path(cache_path).write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def _read_cache_metadata(cache_path: Path) -> dict[str, object]:
    path = _metadata_path(cache_path)
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _cache_metadata(
    data_type: str,
    symbol: str,
    source: str,
    cache_path: Path,
    config: RealResearchConfig,
    fetched_at: datetime,
    **extras: object,
) -> dict[str, object]:
    metadata: dict[str, object] = {
        "data_type": data_type,
        "symbol": symbol,
        "source": source,
        "cache_path": str(cache_path),
        "start_date": config.start_date,
        "end_date": config.end_date,
        "fetched_at": fetched_at.isoformat(),
        "sha256": _sha256(cache_path),
    }
    metadata.update(extras)
    return metadata


def _price_state_warnings(symbol: str, data: pd.DataFrame) -> list[str]:
    if data.empty:
        return []
    warnings: list[str] = []
    missing_close = int(pd.to_numeric(data["close"], errors="coerce").isna().sum())
    volume = pd.to_numeric(data["volume"], errors="coerce")
    zero_volume = int((volume <= 0).fillna(False).sum())
    if missing_close:
        warnings.append(f"{symbol} has {missing_close} rows with missing close")
    if zero_volume:
        warnings.append(f"{symbol} has {zero_volume} zero-volume rows that may be suspended")
    return warnings


def _load_price_data(
    symbol: str,
    config: RealResearchConfig,
    provider: object,
    fetched_at: datetime,
) -> tuple[pd.DataFrame, dict[str, object], list[str]]:
    cache = ParquetCache(config.cache_directory / "prices")
    cache_path = cache.path_for(
        symbol, config.start_date, config.end_date, config.price_adjust
    )
    warnings: list[str] = []
    source = provider.__class__.__name__
    frame: Optional[pd.DataFrame] = None

    if cache_path.exists():
        try:
            frame = cache.read(
                symbol, config.start_date, config.end_date, config.price_adjust
            )
            source = str(_read_cache_metadata(cache_path).get("source") or source)
        except Exception as exc:
            warnings.append(f"{symbol} price cache unreadable; provider retry used: {exc}")

    if frame is None:
        frame = provider.get_daily(
            symbol,
            config.start_date,
            config.end_date,
            adjust=config.price_adjust,
        )
        cache.write(
            frame, symbol, config.start_date, config.end_date, config.price_adjust
        )

    clean = _prepare_price_frame(frame, config.start_date, config.end_date)
    quality = check_price_quality(clean)
    warnings.extend(f"{symbol} price quality error: {item}" for item in quality.errors)
    warnings.extend(
        f"{symbol} price quality warning: {item}" for item in quality.warnings
    )
    warnings.extend(_price_state_warnings(symbol, clean))
    metadata = _cache_metadata(
        "price",
        symbol,
        source,
        cache_path,
        config,
        fetched_at,
        adjust=config.price_adjust,
        rows=len(clean),
    )
    _write_cache_metadata(cache_path, metadata)
    return clean, metadata, warnings


def _load_fundamental_data(
    symbol: str,
    config: RealResearchConfig,
    provider: object,
    fetched_at: datetime,
) -> tuple[FundamentalProviderResult, dict[str, object], list[str]]:
    directory = config.cache_directory / "fundamentals"
    directory.mkdir(parents=True, exist_ok=True)
    cache_path = directory / (
        f"{_safe_part(symbol)}_{_compact_date(config.start_date)}_"
        f"{_compact_date(config.end_date)}.parquet"
    )
    warnings: list[str] = []
    provider_result: Optional[FundamentalProviderResult] = None

    if cache_path.exists():
        try:
            sidecar = _read_cache_metadata(cache_path)
            provider_result = FundamentalProviderResult(
                data=normalize_fundamental_data(pd.read_parquet(cache_path)),
                source=str(sidecar.get("source") or provider.__class__.__name__),
                point_in_time=bool(sidecar.get("point_in_time", False)),
                warnings=list(sidecar.get("warnings", [])),
            )
        except Exception as exc:
            warnings.append(
                f"{symbol} fundamental cache unreadable; provider retry used: {exc}"
            )

    if provider_result is None:
        provider_result = provider.get_fundamentals(
            symbol, config.start_date, config.end_date
        )
        if not isinstance(provider_result, FundamentalProviderResult):
            raise TypeError("fundamental provider must return FundamentalProviderResult")
        provider_result.data = normalize_fundamental_data(provider_result.data)
        provider_result.data.to_parquet(cache_path, index=False)

    provider_result.data = normalize_fundamental_data(provider_result.data)
    metadata = _cache_metadata(
        "fundamental",
        symbol,
        provider_result.source,
        cache_path,
        config,
        fetched_at,
        rows=len(provider_result.data),
        point_in_time=provider_result.point_in_time,
        warnings=provider_result.warnings,
    )
    _write_cache_metadata(cache_path, metadata)
    return provider_result, metadata, warnings


def _financial_factor_inputs(record: Optional[FundamentalRecord]) -> dict[str, object]:
    if record is None:
        return {}
    cash_flow_quality = None
    if record.operating_cash_flow is not None and record.net_profit not in (None, 0):
        cash_flow_quality = record.operating_cash_flow / record.net_profit
    return {
        "pe": record.pe,
        "pb": record.pb,
        "dividend_yield": record.dividend_yield,
        "roe": record.roe,
        "gross_margin": record.gross_margin,
        "net_margin": record.net_margin,
        "operating_cash_flow_quality": cash_flow_quality,
        "debt_to_asset": record.debt_ratio,
    }


def _calculate_factor_scores(
    symbol: str,
    price_history: pd.DataFrame,
    fundamental: Optional[FundamentalRecord],
    weights: Mapping[str, float],
    rebalance_date: pd.Timestamp,
) -> tuple[CompositeFactorScore, dict[str, FactorScore]]:
    as_of_date = rebalance_date.strftime("%Y-%m-%d")
    financial = _financial_factor_inputs(fundamental)
    scores = {
        "value": value_factor(symbol, financial, as_of_date),
        "quality": quality_factor(symbol, financial, as_of_date),
        "momentum": momentum_factor(symbol, price_history, as_of_date),
        "low_vol": low_vol_factor(symbol, price_history, as_of_date),
        "overbought_oversold": overbought_oversold_factor(
            symbol, price_history, as_of_date
        ),
    }
    selected = {name: scores[name] for name in weights}
    composite = combine_factor_scores(
        symbol,
        selected,
        weights,
        as_of_date,
        normalize_weights=True,
    )
    return composite, selected


def _factor_snapshot_row(
    rebalance_date: pd.Timestamp,
    symbol: str,
    composite: CompositeFactorScore,
    factor_scores: Mapping[str, FactorScore],
    fundamental: Optional[FundamentalRecord],
    macro_available_date: Optional[str],
    fundamental_point_in_time: bool,
) -> dict[str, object]:
    row: dict[str, object] = {
        "rebalance_date": rebalance_date,
        "symbol": symbol,
        "composite_score": composite.score,
        "fundamental_report_date": (
            fundamental.report_date if fundamental is not None else None
        ),
        "fundamental_available_date": (
            fundamental.available_date if fundamental is not None else None
        ),
        "fundamental_point_in_time": fundamental_point_in_time,
        "macro_available_date": macro_available_date,
        "warnings": " | ".join(composite.warnings),
    }
    for name, score in factor_scores.items():
        row[f"{name}_score"] = score.score
    return row


def _candidate_for_date(
    symbol: str,
    rebalance_date: pd.Timestamp,
    price_data: pd.DataFrame,
    fundamental_result: FundamentalProviderResult,
    factor_weights: Mapping[str, float],
    macro_available_date: Optional[str],
) -> tuple[StockCandidate, dict[str, object], list[str]]:
    price_history = price_data[price_data["date"] <= rebalance_date].copy()
    warnings = _tradability_warnings(symbol, price_data, rebalance_date)
    warnings.extend(
        _future_fundamental_warnings(
            symbol, fundamental_result.data, rebalance_date
        )
    )
    fundamental = latest_fundamental_asof(
        fundamental_result.data, symbol, rebalance_date
    )
    if fundamental is None:
        warnings.append(
            f"{symbol} has no fundamental record available by {rebalance_date.date()}"
        )
    if not fundamental_result.point_in_time:
        warnings.append(
            f"{symbol} fundamental source is not verified point-in-time"
        )

    composite, factor_scores = _calculate_factor_scores(
        symbol,
        price_history,
        fundamental,
        factor_weights,
        rebalance_date,
    )
    candidate = StockCandidate(
        symbol=symbol,
        score=composite.score,
        factor_scores={name: score.score for name, score in factor_scores.items()},
        industry="unknown",
        warnings=list(composite.warnings),
    )
    snapshot = _factor_snapshot_row(
        rebalance_date,
        symbol,
        composite,
        factor_scores,
        fundamental,
        macro_available_date,
        fundamental_result.point_in_time,
    )
    return candidate, snapshot, warnings


def _build_weight_schedule(
    config: RealResearchConfig,
    price_data: Mapping[str, pd.DataFrame],
    fundamental_results: Mapping[str, FundamentalProviderResult],
    macro_data: pd.DataFrame,
    universe_provider: object,
) -> tuple[dict[pd.Timestamp, dict[str, float]], pd.DataFrame, list[str]]:
    trading_dates = _aligned_trading_dates(
        price_data, config.start_date, config.end_date
    )
    rebalance_dates = generate_rebalance_dates(
        trading_dates, config.rebalance_frequency
    )
    if rebalance_dates.empty:
        raise RealResearchError("no rebalance dates available for the research window")

    schedule: dict[pd.Timestamp, dict[str, float]] = {}
    snapshots: list[dict[str, object]] = []
    warnings: list[str] = []
    all_symbols = list(price_data)

    for rebalance_date in rebalance_dates:
        date_text = rebalance_date.strftime("%Y-%m-%d")
        universe = _universe_snapshot(universe_provider, date_text)
        warnings.extend(universe.warnings)
        if not universe.point_in_time:
            warnings.append(
                f"universe at {date_text} is not verified historical membership"
            )

        eligible_symbols = [
            symbol for symbol in universe.symbols if symbol in price_data
        ]
        missing_prices = sorted(set(universe.symbols) - set(eligible_symbols))
        warnings.extend(
            f"{symbol} excluded at {date_text}: price data unavailable"
            for symbol in missing_prices
        )

        macro_score, macro_multiplier, macro_available_date, macro_warnings = (
            _macro_asof(macro_data, rebalance_date)
        )
        warnings.extend(macro_warnings)
        period_candidates: list[StockCandidate] = []
        period_snapshots: list[dict[str, object]] = []
        for symbol in eligible_symbols:
            fundamental_result = fundamental_results.get(symbol)
            if fundamental_result is None:
                fundamental_result = FundamentalProviderResult(
                    data=normalize_fundamental_data(pd.DataFrame()),
                    source="unavailable",
                    point_in_time=False,
                    warnings=["fundamental provider result unavailable"],
                )
            candidate, snapshot, candidate_warnings = _candidate_for_date(
                symbol,
                rebalance_date,
                price_data[symbol],
                fundamental_result,
                config.factor_weights,
                macro_available_date,
            )
            period_candidates.append(candidate)
            period_snapshots.append(snapshot)
            warnings.extend(candidate_warnings)

        if period_candidates:
            warnings.append(
                f"industry classification unavailable at {date_text}; "
                "unknown-industry constraint is conservative"
            )
        portfolio = build_factor_portfolio(
            period_candidates,
            constraints=config.portfolio_constraints,
            macro_regime=macro_score,
            macro_multiplier=macro_multiplier,
        )
        warnings.extend(f"{date_text}: {item}" for item in portfolio.warnings)
        if not portfolio.target_weights:
            warnings.append(
                f"no eligible target holdings at {date_text}; period remains cash"
            )

        schedule[rebalance_date] = {
            symbol: float(portfolio.target_weights.get(symbol, 0.0))
            for symbol in all_symbols
        }
        for snapshot in period_snapshots:
            symbol = str(snapshot["symbol"])
            snapshot["target_weight"] = portfolio.target_weights.get(symbol, 0.0)
            snapshot["selected"] = symbol in portfolio.selected_symbols
            snapshot["rejection_reason"] = portfolio.rejected_symbols.get(symbol)
            snapshot["macro_regime"] = (
                getattr(macro_score, "regime", None) if macro_score is not None else None
            )
            snapshots.append(snapshot)

    return schedule, pd.DataFrame(snapshots), warnings


def _performance_metrics(equity_curve: pd.Series) -> dict[str, float]:
    returns = daily_returns(equity_curve)
    return {
        "annualized_return": annualized_return(equity_curve),
        "total_return": total_return(equity_curve),
        "max_drawdown": max_drawdown(equity_curve),
        "volatility": volatility(returns),
        "sharpe_ratio": sharpe_ratio(returns),
        "calmar_ratio": calmar_ratio(equity_curve),
    }


def _load_benchmark_data(
    symbol: str,
    config: RealResearchConfig,
    provider: object,
    fetched_at: datetime,
) -> tuple[pd.DataFrame, dict[str, object], list[str]]:
    cache = ParquetCache(config.cache_directory / "benchmarks")
    cache_symbol = f"benchmark_{symbol}"
    cache_path = cache.path_for(
        cache_symbol, config.start_date, config.end_date, "none"
    )
    warnings: list[str] = []
    source = provider.__class__.__name__
    frame: Optional[pd.DataFrame] = None

    if cache_path.exists():
        try:
            frame = cache.read(
                cache_symbol, config.start_date, config.end_date, "none"
            )
            source = str(_read_cache_metadata(cache_path).get("source") or source)
        except Exception as exc:
            warnings.append(
                f"{symbol} benchmark cache unreadable; provider retry used: {exc}"
            )

    if frame is None:
        frame = provider.get_daily(symbol, config.start_date, config.end_date)
        cache.write(
            frame, cache_symbol, config.start_date, config.end_date, "none"
        )

    clean = _prepare_price_frame(frame, config.start_date, config.end_date)
    metadata = _cache_metadata(
        "benchmark",
        symbol,
        source,
        cache_path,
        config,
        fetched_at,
        rows=len(clean),
    )
    _write_cache_metadata(cache_path, metadata)
    return clean, metadata, warnings


def _run_benchmarks(
    config: RealResearchConfig,
    provider: object,
    fetched_at: datetime,
) -> tuple[
    dict[str, dict[str, float]],
    pd.DataFrame,
    list[dict[str, object]],
    list[str],
]:
    metrics: dict[str, dict[str, float]] = {}
    curves: dict[str, pd.Series] = {}
    source_records: list[dict[str, object]] = []
    warnings: list[str] = []

    for symbol in config.benchmark_symbols:
        try:
            frame, source_record, item_warnings = _load_benchmark_data(
                symbol, config, provider, fetched_at
            )
        except Exception as exc:
            warnings.append(f"benchmark {symbol} unavailable: {exc}")
            continue
        warnings.extend(item_warnings)
        source_records.append(source_record)
        if frame.empty:
            warnings.append(f"benchmark {symbol} contains no usable prices")
            continue
        close = frame.set_index("date")["close"].sort_index()
        curve = close / float(close.iloc[0]) * config.initial_capital
        curve.name = symbol
        curves[symbol] = curve
        metrics[symbol] = _performance_metrics(curve)

    benchmark_curve = pd.concat(curves, axis=1).sort_index() if curves else pd.DataFrame()
    return metrics, benchmark_curve, source_records, warnings


def _dedupe_warnings(values: list[str]) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values if str(value).strip()))


def _point_in_time_limitations(
    config: RealResearchConfig,
    fundamental_results: Mapping[str, FundamentalProviderResult],
    macro_data: pd.DataFrame,
) -> list[str]:
    limitations = [
        (
            "The fixed configured universe is not historical index membership "
            "and may contain survivorship bias."
        ),
        (
            "Historical ST, delisting, limit-up/limit-down and exact suspension "
            "execution rules are not fully modeled."
        ),
        (
            "Industry history is unavailable, so unknown-industry exposure is "
            "handled conservatively."
        ),
        (
            "Valuation fields may be absent when the provider cannot supply "
            "historical point-in-time values."
        ),
        (
            "Benchmark curves exclude portfolio transaction costs and are "
            "comparison references only."
        ),
    ]
    if any(not result.point_in_time for result in fundamental_results.values()):
        limitations.append(
            "At least one fundamental source lacks verified historical publication "
            "dates; affected rows are excluded or degraded."
        )
    if macro_data.empty:
        limitations.append(
            "No published macro observations were supplied; a neutral multiplier "
            "is disclosed and used."
        )
    if config.price_adjust != "none":
        limitations.append(
            "Adjusted price series may embed adjustment factors known after an "
            "earlier date and require source-specific review."
        )
    else:
        limitations.append(
            "Unadjusted prices avoid retrospective adjustment but do not include "
            "dividends or corporate-action total returns."
        )
    return limitations


def _run_manifest(
    config: RealResearchConfig,
    run_time: datetime,
    git_commit: str,
    source_records: list[dict[str, object]],
    point_in_time_limitations: list[str],
) -> dict[str, object]:
    return {
        "run_time": run_time.isoformat(),
        "git_commit": git_commit,
        "experiment_name": config.experiment_name,
        "data_sources": source_records,
        "data_range": {
            "start_date": config.start_date,
            "end_date": config.end_date,
        },
        "config_summary": {
            "candidate_count": len(config.candidate_symbols),
            "benchmark_symbols": config.benchmark_symbols,
            "rebalance_frequency": config.rebalance_frequency,
            "price_adjust": config.price_adjust,
            "factor_weights": config.factor_weights,
            "portfolio_constraints": asdict(config.portfolio_constraints),
        },
        "point_in_time_limitations": point_in_time_limitations,
        "survivorship_bias_risk": (
            "The configured fixed stock universe can overstate historical results because "
            "it is not reconstructed from historical constituents."
        ),
        "research_boundary": (
            "Historical research output for education and reproducibility only; "
            "past backtest results do not determine future performance."
        ),
    }


def _period_returns(values: object, date_format: str) -> dict[str, float]:
    series = pd.Series(values, dtype=float)
    result: dict[str, float] = {}
    for date, value in series.items():
        timestamp = pd.Timestamp(date)
        result[timestamp.strftime(date_format)] = float(value)
    return result


def _prepare_market_inputs(
    config: RealResearchConfig,
    price_provider: object,
    fundamental_provider: object,
    fetched_at: datetime,
) -> tuple[
    dict[str, pd.DataFrame],
    dict[str, FundamentalProviderResult],
    list[dict[str, object]],
    list[str],
]:
    price_data: dict[str, pd.DataFrame] = {}
    fundamentals: dict[str, FundamentalProviderResult] = {}
    source_records: list[dict[str, object]] = []
    warnings: list[str] = []

    for symbol in config.candidate_symbols:
        try:
            frame, metadata, item_warnings = _load_price_data(
                symbol, config, price_provider, fetched_at
            )
            if frame.empty:
                raise ValueError("provider returned no usable prices")
            price_data[symbol] = frame
            source_records.append(metadata)
            warnings.extend(item_warnings)
        except Exception as exc:
            warnings.append(f"{symbol} price provider failed: {exc}")
            source_records.append(
                {
                    "data_type": "price",
                    "symbol": symbol,
                    "source": price_provider.__class__.__name__,
                    "status": "failed",
                    "error": str(exc),
                }
            )

    if not price_data:
        raise RealDataAccessError(
            "no candidate price data is available; check network access, provider, and cache"
        )

    for symbol in price_data:
        try:
            result, metadata, item_warnings = _load_fundamental_data(
                symbol, config, fundamental_provider, fetched_at
            )
            fundamentals[symbol] = result
            source_records.append(metadata)
            warnings.extend(item_warnings)
            warnings.extend(
                f"{symbol} fundamental warning: {item}"
                for item in result.warnings
            )
        except Exception as exc:
            warning = f"{symbol} fundamental provider failed: {exc}"
            warnings.append(warning)
            fundamentals[symbol] = FundamentalProviderResult(
                data=normalize_fundamental_data(pd.DataFrame()),
                source=fundamental_provider.__class__.__name__,
                point_in_time=False,
                warnings=[warning],
            )
            source_records.append(
                {
                    "data_type": "fundamental",
                    "symbol": symbol,
                    "source": fundamental_provider.__class__.__name__,
                    "status": "failed",
                    "error": str(exc),
                }
            )

    return price_data, fundamentals, source_records, warnings


def _run_portfolio_backtest(
    config: RealResearchConfig,
    price_data: Mapping[str, pd.DataFrame],
    weight_schedule: Mapping[pd.Timestamp, Mapping[str, float]],
) -> tuple[dict[str, object], dict[str, Any]]:
    backtester = PortfolioBacktester(
        initial_capital=config.initial_capital,
        start_date=config.start_date,
        end_date=config.end_date,
        rebalance_frequency=config.rebalance_frequency,
        commission=config.commission,
        stamp_tax=config.stamp_tax,
        slippage=config.slippage,
        cash_weight=0.0,
        max_position_weight=config.portfolio_constraints.max_position_weight,
    )
    try:
        result = backtester.run_weight_schedule(
            weight_schedule,
            price_data=price_data,
            adjust=config.price_adjust,
        )
    except (TypeError, ValueError) as exc:
        raise RealResearchError(f"portfolio backtest failed: {exc}") from exc

    metrics = scalar_metrics(result)
    metrics["annual_returns"] = _period_returns(result["annual_returns"], "%Y")
    metrics["monthly_returns"] = _period_returns(result["monthly_returns"], "%Y-%m")
    metrics["rebalance_frequency"] = config.rebalance_frequency
    metrics["start_date"] = config.start_date
    metrics["end_date"] = config.end_date
    return result, metrics


def run_real_data_research(
    config_path: PathLike,
    *,
    price_provider: Optional[object] = None,
    fundamental_provider: Optional[object] = None,
    universe_provider: Optional[object] = None,
    macro_provider: Optional[object] = None,
    index_provider: Optional[object] = None,
    run_time: Optional[datetime] = None,
    git_commit: Optional[str] = None,
) -> RealResearchResult:
    """Run one reproducible, point-in-time-aware A-share research experiment.

    External access occurs only when this function is called and a supplied
    cache cannot satisfy the default providers. Tests can inject every provider
    and remain fully offline.
    """
    config = load_real_research_config(config_path)
    started_at = run_time or datetime.now(timezone.utc)
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)
    else:
        started_at = started_at.astimezone(timezone.utc)

    try:
        resolved_price_provider = price_provider or AShareDataProvider()
        resolved_fundamental_provider = (
            fundamental_provider or AShareFundamentalProvider()
        )
    except ImportError as exc:
        raise RealDataAccessError(f"real-data provider is unavailable: {exc}") from exc
    resolved_universe_provider = universe_provider or FixedStockUniverse(
        config.candidate_symbols
    )

    warnings: list[str] = []
    price_data, fundamental_results, source_records, input_warnings = (
        _prepare_market_inputs(
            config,
            resolved_price_provider,
            resolved_fundamental_provider,
            started_at,
        )
    )
    warnings.extend(input_warnings)

    macro_data, macro_source, macro_warnings = _load_macro_data(
        config, macro_provider
    )
    warnings.extend(macro_warnings)
    source_records.append(
        {
            "data_type": "macro",
            "source": macro_source,
            "path": str(config.macro_csv_path) if macro_provider is None else None,
            "rows": len(macro_data),
            "point_in_time": bool(
                not macro_data.empty
                and "available_date" in macro_data.columns
                and macro_data["available_date"].notna().all()
            ),
        }
    )
    source_records.append(
        {
            "data_type": "universe",
            "source": resolved_universe_provider.__class__.__name__,
            "configured_symbols": config.candidate_symbols,
        }
    )

    weight_schedule, factor_snapshots, schedule_warnings = _build_weight_schedule(
        config,
        price_data,
        fundamental_results,
        macro_data,
        resolved_universe_provider,
    )
    warnings.extend(schedule_warnings)
    backtest_result, metrics = _run_portfolio_backtest(
        config, price_data, weight_schedule
    )

    try:
        resolved_index_provider = index_provider or AShareIndexProvider()
    except ImportError as exc:
        resolved_index_provider = None
        warnings.append(f"benchmark provider is unavailable: {exc}")

    if resolved_index_provider is None:
        benchmark_metrics: dict[str, dict[str, float]] = {}
        benchmark_curve = pd.DataFrame()
    else:
        (
            benchmark_metrics,
            benchmark_curve,
            benchmark_sources,
            benchmark_warnings,
        ) = _run_benchmarks(config, resolved_index_provider, started_at)
        source_records.extend(benchmark_sources)
        warnings.extend(benchmark_warnings)

    limitations = _point_in_time_limitations(
        config, fundamental_results, macro_data
    )
    warnings = _dedupe_warnings(warnings)
    repository_root = _repository_root(Path(config_path).resolve())
    manifest = _run_manifest(
        config,
        started_at,
        git_commit or current_git_commit(repository_root),
        source_records,
        limitations,
    )
    artifacts = write_research_artifacts(
        config.output_directory,
        config=config.to_dict(),
        run_manifest=manifest,
        metrics=metrics,
        benchmark_metrics=benchmark_metrics,
        equity_curve=pd.Series(backtest_result["equity_curve"]),
        benchmark_curve=benchmark_curve,
        holdings=pd.DataFrame(backtest_result["holdings_by_period"]),
        trades=pd.DataFrame(backtest_result["trade_log"]),
        factor_snapshots=factor_snapshots,
        warnings=warnings,
        run_time=started_at,
    )

    serialized_schedule = {
        date.strftime("%Y-%m-%d"): dict(weights)
        for date, weights in sorted(weight_schedule.items())
    }
    return RealResearchResult(
        run_id=artifacts.run_id,
        run_directory=artifacts.run_directory,
        config=config,
        metrics=metrics,
        benchmark_metrics=benchmark_metrics,
        equity_curve=pd.Series(backtest_result["equity_curve"]),
        benchmark_curve=benchmark_curve,
        target_weights_by_date=serialized_schedule,
        factor_snapshots=factor_snapshots,
        warnings=warnings,
        artifacts=artifacts,
    )
