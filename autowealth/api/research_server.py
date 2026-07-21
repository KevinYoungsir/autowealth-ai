"""
Research-only FastAPI aggregation surface.

This module is intentionally independent from ``autowealth.api.server`` so the
legacy API behavior remains unchanged.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional

import pandas as pd
from fastapi import APIRouter, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from autowealth.agents.deepseek_research_agent import DeepSeekResearchAgent
from autowealth.i18n import DEFAULT_REPORT_LOCALE, SupportedLocale
from autowealth.api.research_models import (
    DeepSeekMockReportResponse,
    EquityPoint,
    EquityCurvePoint,
    HoldingRecord,
    PortfolioConstraintsInput,
    RESEARCH_API_EXPLANATION,
    RESEARCH_API_VERSION,
    ResearchDemoResponse,
    ResearchFactorScoreInput,
    ResearchHealthResponse,
    ResearchAPIErrorResponse,
    ResearchBenchmarkCurveResponse,
    ResearchEquityCurveResponse,
    ResearchFactorsResponse,
    ResearchHoldingsResponse,
    ResearchPipelineResultPayload,
    RealResearchReportResponse,
    ResearchRunDetailResponse,
    ResearchRunListResponse,
    ResearchRunRequest,
    ResearchRunSummary,
    ResearchSummaryPayload,
    ResearchTradesResponse,
    ResearchWarningsResponse,
    TradeRecord,
    WarningSummary,
)
from autowealth.portfolio.schema import PortfolioConstraints
from autowealth.research import (
    mock_candidate_symbols,
    mock_factor_scores,
    mock_industries,
    mock_macro_regime,
    mock_portfolio_constraints,
    mock_price_data,
    run_research_pipeline,
    summarize_research_result,
)
from autowealth.research.real_report import build_real_research_report
from autowealth.research.run_store import (
    InvalidRunIdError,
    ResearchArtifactDecodeError,
    ResearchArtifactNotFoundError,
    ResearchRunNotFoundError,
    ResearchRunStore,
    ResearchRunStoreError,
    aggregate_warnings,
)
from autowealth.research.schema import ResearchPipelineResult, ResearchSummary

DEFAULT_RESEARCH_API_CORS_ORIGINS = (
    "http://127.0.0.1:3000",
    "http://localhost:3000",
    "https://dashboard.outlook.xin",
)
DEFAULT_RESEARCH_API_TRUSTED_HOSTS = (
    "127.0.0.1",
    "localhost",
    "testserver",
    "api.outlook.xin",
)
RAILWAY_HEALTHCHECK_HOST = "healthcheck.railway.app"


@dataclass
class _PrecomputedFactorScore:
    symbol: str
    score: float
    factor_scores: Dict[str, float]
    warnings: list[str]


research_router = APIRouter(prefix="/research", tags=["research"])
RUN_ERROR_RESPONSES = {
    400: {"model": ResearchAPIErrorResponse},
    404: {"model": ResearchAPIErrorResponse},
    422: {"model": ResearchAPIErrorResponse},
}


def _request_run_store(request: Request) -> ResearchRunStore:
    return request.app.state.research_run_store


@research_router.get("/health", response_model=ResearchHealthResponse)
async def research_health(request: Request) -> ResearchHealthResponse:
    store = _request_run_store(request)
    research_runs_available = store.ensure_directory()
    latest_run_available = store.has_runs() if research_runs_available else False
    return ResearchHealthResponse(
        status="ok",
        service="autowealth-research-api",
        version=RESEARCH_API_VERSION,
        mock_mode=True,
        research_runs_available=research_runs_available,
        latest_run_available=latest_run_available,
    )


@research_router.get("/demo", response_model=ResearchDemoResponse)
async def research_demo() -> ResearchDemoResponse:
    result = _run_demo_experiment()
    summary = summarize_research_result(result)
    return ResearchDemoResponse(
        mock_mode=True,
        result=_result_payload(result),
        summary=_summary_payload(summary),
        explanation=RESEARCH_API_EXPLANATION,
    )


@research_router.get(
    "/runs",
    response_model=ResearchRunListResponse,
    responses=RUN_ERROR_RESPONSES,
)
async def research_runs(
    request: Request,
    limit: int = Query(20, ge=1, le=100),
) -> ResearchRunListResponse:
    store = _request_run_store(request)
    runs = [ResearchRunSummary(**item) for item in store.list_runs(limit=limit)]
    return ResearchRunListResponse(count=len(runs), runs=runs)


@research_router.get(
    "/runs/latest",
    response_model=ResearchRunDetailResponse,
    responses=RUN_ERROR_RESPONSES,
)
async def research_latest_run(request: Request) -> ResearchRunDetailResponse:
    return _run_detail_response(_request_run_store(request).get_latest_run())


@research_router.get(
    "/runs/{run_id}",
    response_model=ResearchRunDetailResponse,
    responses=RUN_ERROR_RESPONSES,
)
async def research_run_detail(
    run_id: str,
    request: Request,
) -> ResearchRunDetailResponse:
    return _run_detail_response(_request_run_store(request).get_run(run_id))


@research_router.get(
    "/runs/{run_id}/report",
    response_model=RealResearchReportResponse,
    responses=RUN_ERROR_RESPONSES,
)
async def research_run_report(
    run_id: str,
    request: Request,
    response: Response,
    locale: SupportedLocale = Query(DEFAULT_REPORT_LOCALE),
) -> RealResearchReportResponse:
    report = build_real_research_report(
        _request_run_store(request),
        run_id,
        locale=locale,
    )
    response.headers["Content-Language"] = locale
    return RealResearchReportResponse(**report)


@research_router.get(
    "/runs/{run_id}/equity-curve",
    response_model=ResearchEquityCurveResponse,
    responses=RUN_ERROR_RESPONSES,
)
async def research_run_equity_curve(
    run_id: str,
    request: Request,
    downsample: int = Query(500, ge=2, le=5000),
) -> ResearchEquityCurveResponse:
    frame = _request_run_store(request).read_equity_curve(run_id)
    if "date" not in frame or "equity" not in frame:
        raise ResearchArtifactDecodeError(
            f"equity_curve.parquet for run {run_id} lacks date/equity columns"
        )
    frame = frame.sort_values("date")
    sampled = _downsample_frame(frame, downsample)
    points = [
        EquityCurvePoint(
            date=_date_text(row["date"]),
            equity=float(row["equity"]),
        )
        for _, row in sampled.iterrows()
    ]
    return ResearchEquityCurveResponse(
        run_id=run_id,
        total_points=len(frame),
        returned_points=len(points),
        downsample=downsample,
        points=points,
    )


@research_router.get(
    "/runs/{run_id}/benchmark-curve",
    response_model=ResearchBenchmarkCurveResponse,
    responses=RUN_ERROR_RESPONSES,
)
async def research_run_benchmark_curve(
    run_id: str,
    request: Request,
    downsample: int = Query(500, ge=2, le=5000),
) -> ResearchBenchmarkCurveResponse:
    store = _request_run_store(request)
    detail = store.get_run(run_id)
    status, reasons = _benchmark_response_status(detail["benchmark_metrics"])
    if status == "unavailable":
        return ResearchBenchmarkCurveResponse(
            run_id=run_id,
            status=status,
            reasons=reasons,
            downsample=downsample,
        )
    frame = store.read_benchmark_curve(run_id)
    if "date" not in frame:
        raise ResearchArtifactDecodeError(
            f"benchmark_curve.parquet for run {run_id} lacks a date column"
        )
    sampled = _downsample_frame(frame.sort_values("date"), downsample)
    points = _frame_records(sampled)
    return ResearchBenchmarkCurveResponse(
        run_id=run_id,
        status=status,
        reasons=reasons,
        total_points=len(frame),
        returned_points=len(points),
        downsample=downsample,
        points=points,
    )


@research_router.get(
    "/runs/{run_id}/holdings",
    response_model=ResearchHoldingsResponse,
    responses=RUN_ERROR_RESPONSES,
)
async def research_run_holdings(
    run_id: str,
    request: Request,
    limit: int = Query(200, ge=1, le=2000),
    rebalance_date: Optional[str] = Query(None),
) -> ResearchHoldingsResponse:
    store = _request_run_store(request)
    frame = store.read_holdings(run_id)
    records = _holding_records(frame, rebalance_date=rebalance_date)[:limit]
    manifest = store.read_manifest(run_id)
    coverage = _mapping_value(manifest.get("coverage_summary"))
    constraints = _mapping_value(
        _mapping_value(manifest.get("config_summary")).get("portfolio_constraints")
    )
    return ResearchHoldingsResponse(
        run_id=run_id,
        records=[HoldingRecord(**record) for record in records],
        returned=len(records),
        min_holdings=_optional_int(constraints.get("min_holdings")),
        holdings_count_by_rebalance={
            str(date): int(count)
            for date, count in _mapping_value(coverage.get("holdings_count_by_rebalance")).items()
        },
    )


@research_router.get(
    "/runs/{run_id}/trades",
    response_model=ResearchTradesResponse,
    responses=RUN_ERROR_RESPONSES,
)
async def research_run_trades(
    run_id: str,
    request: Request,
    limit: int = Query(500, ge=1, le=5000),
) -> ResearchTradesResponse:
    frame = _request_run_store(request).read_trades(run_id)
    if "date" in frame:
        frame = frame.sort_values("date", ascending=False)
    records = _frame_records(frame.head(limit))
    return ResearchTradesResponse(
        run_id=run_id,
        records=[TradeRecord(**record) for record in records],
        returned=len(records),
    )


@research_router.get(
    "/runs/{run_id}/factors",
    response_model=ResearchFactorsResponse,
    responses=RUN_ERROR_RESPONSES,
)
async def research_run_factors(
    run_id: str,
    request: Request,
    limit: int = Query(500, ge=1, le=5000),
) -> ResearchFactorsResponse:
    store = _request_run_store(request)
    frame = store.read_factor_snapshots(run_id)
    if "rebalance_date" in frame:
        frame = frame.sort_values("rebalance_date", ascending=False)
    records = _frame_records(frame.head(limit))
    coverage = _mapping_value(store.read_manifest(run_id).get("coverage_summary"))
    return ResearchFactorsResponse(
        run_id=run_id,
        records=records,
        returned=len(records),
        coverage_by_rebalance=_mapping_value(coverage.get("factor_coverage_by_rebalance")),
        coverage_overall=_mapping_value(coverage.get("factor_coverage_overall")),
    )


@research_router.get(
    "/runs/{run_id}/warnings",
    response_model=ResearchWarningsResponse,
    responses=RUN_ERROR_RESPONSES,
)
async def research_run_warnings(
    run_id: str,
    request: Request,
    sample_limit: int = Query(3, ge=0, le=10),
    raw_limit: int = Query(20, ge=0, le=200),
) -> ResearchWarningsResponse:
    summary = aggregate_warnings(
        _request_run_store(request).read_warnings(run_id),
        sample_limit=sample_limit,
        raw_limit=raw_limit,
    )
    return ResearchWarningsResponse(
        run_id=run_id,
        summary=WarningSummary(**summary),
    )


@research_router.post("/run", response_model=ResearchPipelineResultPayload)
async def research_run(request: ResearchRunRequest) -> ResearchPipelineResultPayload:
    try:
        result = run_research_pipeline(
            candidate_symbols=request.candidate_symbols,
            factor_scores=_factor_scores_from_request(request.factor_scores, request.end_date),
            macro_multiplier=request.macro_multiplier,
            portfolio_constraints=_constraints_from_request(request.constraints),
            price_data=_price_data_from_request(request.price_data),
            industries=request.industries,
            start_date=request.start_date,
            end_date=request.end_date,
            experiment_name=request.experiment_name,
            initial_capital=request.initial_capital,
            rebalance_frequency=request.rebalance_frequency,
            commission=request.commission,
            stamp_tax=request.stamp_tax,
            slippage=request.slippage,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail="The research request could not be processed.",
        ) from exc
    return _result_payload(result)


@research_router.post("/summarize", response_model=ResearchSummaryPayload)
async def research_summarize(
    payload: ResearchPipelineResultPayload,
) -> ResearchSummaryPayload:
    try:
        result = _result_from_payload(payload)
        summary = summarize_research_result(result)
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail="The research summary input is invalid.",
        ) from exc
    return _summary_payload(summary)


@research_router.post("/deepseek/mock-report", response_model=DeepSeekMockReportResponse)
async def research_deepseek_mock_report(
    payload: ResearchPipelineResultPayload,
) -> DeepSeekMockReportResponse:
    try:
        result = _result_from_payload(payload)
        agent = DeepSeekResearchAgent(
            api_key="",
            base_url="",
            model="",
            mock_mode=True,
        )
        report = agent.build_research_report(result)
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail="The mock research report input is invalid.",
        ) from exc
    return DeepSeekMockReportResponse(**report)


def _research_api_cors_origins() -> list[str]:
    configured = os.getenv("RESEARCH_API_CORS_ORIGINS", "")
    if not configured.strip():
        return list(DEFAULT_RESEARCH_API_CORS_ORIGINS)

    origins: list[str] = []
    for value in configured.split(","):
        origin = value.strip().rstrip("/")
        if origin == "*":
            raise ValueError("RESEARCH_API_CORS_ORIGINS cannot contain a wildcard")
        if origin and origin not in origins:
            origins.append(origin)
    return origins or list(DEFAULT_RESEARCH_API_CORS_ORIGINS)


def _research_api_trusted_hosts() -> list[str]:
    configured = os.getenv("RESEARCH_API_TRUSTED_HOSTS", "")
    values = (
        configured.split(",") if configured.strip() else list(DEFAULT_RESEARCH_API_TRUSTED_HOSTS)
    )
    hosts: list[str] = []
    for value in values:
        host = value.strip().lower()
        if not host:
            continue
        if "*" in host or "://" in host or "/" in host:
            raise ValueError("RESEARCH_API_TRUSTED_HOSTS contains an invalid host")
        if host not in hosts:
            hosts.append(host)
    if RAILWAY_HEALTHCHECK_HOST not in hosts:
        hosts.append(RAILWAY_HEALTHCHECK_HOST)
    return hosts or list(DEFAULT_RESEARCH_API_TRUSTED_HOSTS)


def create_research_app(
    run_store: Optional[ResearchRunStore] = None,
) -> FastAPI:
    app = FastAPI(
        title="AutoWealth Research API",
        description="Research-only aggregation API for A-share portfolio experiments.",
        version=RESEARCH_API_VERSION,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_research_api_cors_origins(),
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type"],
        max_age=600,
    )
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=_research_api_trusted_hosts(),
    )
    app.state.research_run_store = run_store or ResearchRunStore()

    @app.exception_handler(ResearchRunStoreError)
    async def research_run_store_error_handler(
        request: Request,
        exc: ResearchRunStoreError,
    ) -> JSONResponse:
        del request
        status_code, code = _store_error_status(exc)
        payload = ResearchAPIErrorResponse(code=code, message=str(exc))
        return JSONResponse(
            status_code=status_code,
            content=payload.model_dump(),
        )

    @app.exception_handler(Exception)
    async def unexpected_error_handler(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        del request, exc
        payload = ResearchAPIErrorResponse(
            code="internal_server_error",
            message="The research API could not process this request.",
        )
        return JSONResponse(status_code=500, content=payload.model_dump())

    app.include_router(research_router)
    return app


app = create_research_app()


def _run_demo_experiment() -> ResearchPipelineResult:
    return run_research_pipeline(
        candidate_symbols=mock_candidate_symbols(),
        factor_scores=mock_factor_scores(),
        macro_regime=mock_macro_regime(),
        portfolio_constraints=mock_portfolio_constraints(),
        price_data=mock_price_data(),
        industries=mock_industries(),
        start_date="2020-01-01",
        end_date="2024-12-31",
        experiment_name="api_mock_research_demo",
        rebalance_frequency="yearly",
    )


def _factor_scores_from_request(
    factor_scores: Mapping[str, float | ResearchFactorScoreInput],
    default_as_of_date: str,
) -> Dict[str, _PrecomputedFactorScore]:
    converted: Dict[str, _PrecomputedFactorScore] = {}
    for symbol, score_input in factor_scores.items():
        if isinstance(score_input, (int, float)):
            score = float(score_input)
            converted[symbol] = _PrecomputedFactorScore(
                symbol=symbol,
                score=score,
                factor_scores={"composite": score},
                warnings=[],
            )
            continue

        factor_values = dict(score_input.factor_scores)
        if not factor_values:
            factor_values[score_input.factor_name] = score_input.score
        converted[symbol] = _PrecomputedFactorScore(
            symbol=symbol,
            score=float(score_input.score),
            factor_scores={str(key): float(value) for key, value in factor_values.items()},
            warnings=list(score_input.warnings),
        )
    return converted


def _constraints_from_request(constraints: PortfolioConstraintsInput) -> PortfolioConstraints:
    return PortfolioConstraints(**constraints.model_dump())


def _price_data_from_request(price_data: Mapping[str, list]) -> Dict[str, pd.DataFrame]:
    converted = {}
    for symbol, bars in price_data.items():
        records = [bar.model_dump() for bar in bars]
        if not records:
            raise ValueError(f"price_data for {symbol} cannot be empty")
        frame = pd.DataFrame(records)
        frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
        frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
        frame = frame.dropna(subset=["date", "close"])
        if frame.empty:
            raise ValueError(f"price_data for {symbol} has no valid date/close rows")
        converted[str(symbol)] = frame
    return converted


def _result_payload(result: ResearchPipelineResult) -> ResearchPipelineResultPayload:
    return ResearchPipelineResultPayload(
        experiment_name=result.experiment_name,
        start_date=result.start_date,
        end_date=result.end_date,
        candidate_symbols=list(result.candidate_symbols),
        selected_symbols=list(result.selected_symbols),
        rejected_symbols=dict(result.rejected_symbols),
        factor_summary=_json_ready(result.factor_summary),
        macro_summary=_json_ready(result.macro_summary),
        target_weights={
            str(symbol): float(weight) for symbol, weight in result.target_weights.items()
        },
        backtest_metrics=_json_ready(result.backtest_metrics),
        equity_curve=_equity_points(result.equity_curve),
        warnings=list(result.warnings),
        explanation=result.explanation,
    )


def _summary_payload(summary: ResearchSummary) -> ResearchSummaryPayload:
    return ResearchSummaryPayload(
        experiment_name=summary.experiment_name,
        start_date=summary.start_date,
        end_date=summary.end_date,
        candidate_symbols=list(summary.candidate_symbols),
        selected_symbols=list(summary.selected_symbols),
        rejected_symbols=dict(summary.rejected_symbols),
        factor_summary=_json_ready(summary.factor_summary),
        macro_summary=_json_ready(summary.macro_summary),
        target_weights={
            str(symbol): float(weight) for symbol, weight in summary.target_weights.items()
        },
        backtest_metrics=_json_ready(summary.backtest_metrics),
        equity_curve=_equity_points(summary.equity_curve),
        warnings=list(summary.warnings),
        explanation=summary.explanation,
    )


def _result_from_payload(payload: ResearchPipelineResultPayload) -> ResearchPipelineResult:
    return ResearchPipelineResult(
        experiment_name=payload.experiment_name,
        start_date=payload.start_date,
        end_date=payload.end_date,
        candidate_symbols=list(payload.candidate_symbols),
        selected_symbols=list(payload.selected_symbols),
        rejected_symbols=dict(payload.rejected_symbols),
        factor_summary=dict(payload.factor_summary),
        macro_summary=dict(payload.macro_summary),
        target_weights=dict(payload.target_weights),
        backtest_metrics=dict(payload.backtest_metrics),
        equity_curve=_series_from_equity_points(payload.equity_curve),
        warnings=list(payload.warnings),
        explanation=payload.explanation,
    )


def _equity_points(equity_curve: object) -> list[EquityPoint]:
    if equity_curve is None:
        return []
    if isinstance(equity_curve, pd.DataFrame):
        if equity_curve.empty:
            return []
        series = equity_curve.iloc[:, 0]
    elif isinstance(equity_curve, pd.Series):
        series = equity_curve
    else:
        series = pd.Series(equity_curve)

    points = []
    for index, value in series.items():
        date = index.isoformat() if hasattr(index, "isoformat") else str(index)
        points.append(EquityPoint(date=date, equity=float(value)))
    return points


def _series_from_equity_points(points: list[EquityPoint]) -> pd.Series:
    if not points:
        return pd.Series(dtype=float)
    dates = pd.to_datetime([point.date for point in points], errors="coerce")
    values = [float(point.equity) for point in points]
    series = pd.Series(values, index=dates).dropna()
    return series.sort_index()


def _run_detail_response(detail: Mapping[str, Any]) -> ResearchRunDetailResponse:
    warning_summary = aggregate_warnings(
        _mapping_value(detail.get("warnings")),
        sample_limit=3,
        raw_limit=0,
    )
    return ResearchRunDetailResponse(
        summary=ResearchRunSummary(**_mapping_value(detail.get("summary"))),
        manifest=_mapping_value(detail.get("manifest")),
        metrics=_mapping_value(detail.get("metrics")),
        benchmark_metrics=_mapping_value(detail.get("benchmark_metrics")),
        benchmark_diagnostics=_mapping_value(detail.get("benchmark_diagnostics")),
        warning_summary=WarningSummary(**warning_summary),
    )


def _store_error_status(exc: ResearchRunStoreError) -> tuple[int, str]:
    if isinstance(exc, InvalidRunIdError):
        return 400, "invalid_run_id"
    if isinstance(exc, ResearchRunNotFoundError):
        return 404, "research_run_not_found"
    if isinstance(exc, ResearchArtifactNotFoundError):
        return 404, "research_artifact_not_found"
    if isinstance(exc, ResearchArtifactDecodeError):
        return 422, "invalid_research_artifact"
    return 500, "research_run_store_error"


def _downsample_frame(frame: pd.DataFrame, limit: int) -> pd.DataFrame:
    if len(frame) <= limit:
        return frame.copy()
    indexes = sorted({round(index * (len(frame) - 1) / (limit - 1)) for index in range(limit)})
    return frame.iloc[indexes].copy()


def _benchmark_response_status(
    benchmarks: Mapping[str, Any],
) -> tuple[str, dict[str, str]]:
    reasons: dict[str, str] = {}
    available = 0
    for symbol, value in benchmarks.items():
        entry = _mapping_value(value)
        if entry.get("status") == "unavailable":
            reasons[str(symbol)] = str(entry.get("reason") or "unavailable")
        else:
            available += 1
    if available == 0:
        return "unavailable", reasons
    if reasons:
        return "partial", reasons
    return "available", reasons


def _holding_records(
    frame: pd.DataFrame,
    *,
    rebalance_date: Optional[str],
) -> list[dict[str, Any]]:
    data = pd.DataFrame(frame).copy()
    if "date" not in data:
        raise ResearchArtifactDecodeError("holdings.parquet lacks a date column")
    data["date"] = pd.to_datetime(data["date"], errors="coerce")
    data = data.dropna(subset=["date"])
    if rebalance_date is not None:
        requested = pd.to_datetime(rebalance_date, errors="coerce")
        if pd.isna(requested):
            raise InvalidRunIdError("rebalance_date has an invalid format")
        data = data[data["date"].dt.normalize() == requested.normalize()]
    data = data.sort_values("date", ascending=False)

    records: list[dict[str, Any]] = []
    for _, row in data.iterrows():
        date_text = _date_text(row["date"])
        for column in data.columns:
            if not column.endswith("_weight") or column == "cash_weight":
                continue
            weight = _optional_float_value(row.get(column))
            if weight is None or weight <= 0:
                continue
            symbol = column[: -len("_weight")]
            records.append(
                {
                    "rebalance_date": date_text,
                    "symbol": symbol,
                    "weight": weight,
                    "shares": _optional_float_value(row.get(f"{symbol}_shares")),
                    "cash_weight": _optional_float_value(row.get("cash_weight")),
                    "cash": _optional_float_value(row.get("cash")),
                    "equity": _optional_float_value(row.get("equity")),
                }
            )
    return records


def _frame_records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    records = []
    for record in pd.DataFrame(frame).to_dict(orient="records"):
        records.append({str(key): _json_scalar(value) for key, value in record.items()})
    return records


def _json_scalar(value: Any) -> Any:
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if hasattr(value, "item"):
        try:
            value = value.item()
        except (TypeError, ValueError):
            return str(value)
    try:
        if bool(pd.isna(value)):
            return None
    except (TypeError, ValueError):
        pass
    return value


def _date_text(value: Any) -> str:
    timestamp = pd.to_datetime(value, errors="coerce")
    if pd.isna(timestamp):
        return str(value)
    return pd.Timestamp(timestamp).isoformat()


def _mapping_value(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _optional_float_value(value: object) -> Optional[float]:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return None if pd.isna(parsed) else parsed


def _optional_int(value: object) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _json_ready(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    if isinstance(value, tuple):
        return [_json_ready(item) for item in value]
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if hasattr(value, "item"):
        try:
            return value.item()
        except ValueError:
            return str(value)
    return value
