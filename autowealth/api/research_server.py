"""
Research-only FastAPI aggregation surface.

This module is intentionally independent from ``autowealth.api.server`` so the
legacy API behavior remains unchanged.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, Mapping

import pandas as pd
from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from autowealth.agents.deepseek_research_agent import DeepSeekResearchAgent
from autowealth.api.research_models import (
    DeepSeekMockReportResponse,
    EquityPoint,
    PortfolioConstraintsInput,
    RESEARCH_API_EXPLANATION,
    RESEARCH_API_VERSION,
    ResearchDemoResponse,
    ResearchFactorScoreInput,
    ResearchHealthResponse,
    ResearchPipelineResultPayload,
    ResearchRunRequest,
    ResearchSummaryPayload,
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
from autowealth.research.schema import ResearchPipelineResult, ResearchSummary


DEFAULT_RESEARCH_API_CORS_ORIGINS = (
    "http://127.0.0.1:3000",
    "http://localhost:3000",
    "https://dashboard.outlook.xin",
)


@dataclass
class _PrecomputedFactorScore:
    symbol: str
    score: float
    factor_scores: Dict[str, float]
    warnings: list[str]


research_router = APIRouter(prefix="/research", tags=["research"])


@research_router.get("/health", response_model=ResearchHealthResponse)
async def research_health() -> ResearchHealthResponse:
    return ResearchHealthResponse(
        status="ok",
        service="autowealth-research-api",
        version=RESEARCH_API_VERSION,
        mock_mode=True,
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
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _result_payload(result)


@research_router.post("/summarize", response_model=ResearchSummaryPayload)
async def research_summarize(
    payload: ResearchPipelineResultPayload,
) -> ResearchSummaryPayload:
    try:
        result = _result_from_payload(payload)
        summary = summarize_research_result(result)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
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
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return DeepSeekMockReportResponse(**report)


def _research_api_cors_origins() -> list[str]:
    configured = os.getenv("RESEARCH_API_CORS_ORIGINS", "")
    if not configured.strip():
        return list(DEFAULT_RESEARCH_API_CORS_ORIGINS)

    origins: list[str] = []
    for value in configured.split(","):
        origin = value.strip().rstrip("/")
        if origin and origin not in origins:
            origins.append(origin)
    return origins or list(DEFAULT_RESEARCH_API_CORS_ORIGINS)


def create_research_app() -> FastAPI:
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
        target_weights={str(symbol): float(weight) for symbol, weight in result.target_weights.items()},
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
        target_weights={str(symbol): float(weight) for symbol, weight in summary.target_weights.items()},
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
