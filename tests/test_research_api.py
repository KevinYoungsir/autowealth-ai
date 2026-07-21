import json
import os
import sys
from datetime import datetime, timezone
from numbers import Number
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.modules["yfinance"] = MagicMock()

from fastapi.testclient import TestClient
import pandas as pd
import pytest

from autowealth.api.research_server import app, create_research_app
from autowealth.i18n.warning_presenter import present_warnings
from autowealth.research import (
    mock_candidate_symbols,
    mock_factor_scores,
    mock_industries,
    mock_portfolio_constraints,
    mock_price_data,
)
from autowealth.research.artifacts import write_research_artifacts
from autowealth.research.run_store import ResearchRunStore

client = TestClient(app)
REAL_RUN_ID = "20250201T000000Z_cccccccccc"


@pytest.fixture
def real_runs_root(tmp_path: Path):
    pytest.importorskip("pyarrow")
    root = tmp_path / "research_runs"
    _write_api_run(root)
    return root


@pytest.fixture
def real_runs_client(real_runs_root: Path):
    return TestClient(create_research_app(ResearchRunStore(real_runs_root)))


def test_research_health():
    response = client.get("/research/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["service"] == "autowealth-research-api"
    assert payload["mock_mode"] is True
    assert "version" in payload
    assert isinstance(payload["research_runs_available"], bool)
    assert isinstance(payload["latest_run_available"], bool)


def test_research_cors_allows_configured_dashboard_origins():
    origins = "http://127.0.0.1:3000,http://localhost:3000," "https://dashboard.outlook.xin"
    with patch.dict(os.environ, {"RESEARCH_API_CORS_ORIGINS": origins}):
        cors_client = TestClient(create_research_app())

    for origin in origins.split(","):
        response = cors_client.options(
            "/research/health",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "GET",
            },
        )
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == origin


def test_research_cors_rejects_wildcard_configuration():
    with patch.dict(os.environ, {"RESEARCH_API_CORS_ORIGINS": "*"}):
        with pytest.raises(ValueError, match="cannot contain a wildcard"):
            create_research_app()


def test_trusted_hosts_allow_production_and_railway_healthcheck(tmp_path: Path):
    with patch.dict(
        os.environ,
        {"RESEARCH_API_TRUSTED_HOSTS": "api.outlook.xin"},
    ):
        trusted_client = TestClient(
            create_research_app(ResearchRunStore(tmp_path / "runs")),
            base_url="https://api.outlook.xin",
        )

    assert trusted_client.get("/research/health").status_code == 200
    railway = trusted_client.get(
        "/research/health",
        headers={"Host": "healthcheck.railway.app"},
    )
    assert railway.status_code == 200


def test_trusted_hosts_reject_unknown_host(tmp_path: Path):
    with patch.dict(
        os.environ,
        {"RESEARCH_API_TRUSTED_HOSTS": "api.outlook.xin"},
    ):
        trusted_client = TestClient(
            create_research_app(ResearchRunStore(tmp_path / "runs")),
            base_url="https://api.outlook.xin",
        )

    response = trusted_client.get(
        "/research/health",
        headers={"Host": "untrusted.example"},
    )

    assert response.status_code == 400
    assert "Invalid host" in response.text


def test_empty_health_and_latest_are_structured(tmp_path: Path):
    root = tmp_path / "missing" / "research_runs"
    empty_client = TestClient(create_research_app(ResearchRunStore(root)))

    health = empty_client.get("/research/health")
    runs = empty_client.get("/research/runs")
    latest = empty_client.get("/research/runs/latest")

    assert health.status_code == 200
    assert health.json()["research_runs_available"] is True
    assert health.json()["latest_run_available"] is False
    assert root.is_dir()
    assert runs.json()["runs"] == []
    assert latest.status_code == 404
    assert latest.json()["code"] == "research_run_not_found"
    assert "no research runs" in latest.json()["message"]


def test_unexpected_api_error_is_sanitized(tmp_path: Path):
    store = ResearchRunStore(tmp_path / "runs")
    store.list_runs = MagicMock(side_effect=RuntimeError("secret D:\\private\\path TOKEN=value"))
    safe_client = TestClient(
        create_research_app(store),
        raise_server_exceptions=False,
    )

    response = safe_client.get("/research/runs")

    assert response.status_code == 500
    assert response.json()["code"] == "internal_server_error"
    assert "private" not in response.text
    assert "TOKEN" not in response.text


def test_research_demo_uses_mock_data_without_network():
    with patch(
        "autowealth.data.ashare_provider.AShareDataProvider.__init__",
        side_effect=AssertionError("network data provider should not be initialized"),
    ):
        response = client.get("/research/demo")

    assert response.status_code == 200
    payload = response.json()
    assert payload["mock_mode"] is True
    assert payload["result"]["target_weights"]
    assert payload["result"]["equity_curve"]
    assert payload["summary"]["backtest_metrics"]["holding_count"] > 0


def test_research_run_with_precomputed_inputs():
    body = _run_request_body()

    with patch(
        "autowealth.data.ashare_provider.AShareDataProvider.__init__",
        side_effect=AssertionError("network data provider should not be initialized"),
    ):
        response = client.post("/research/run", json=body)

    assert response.status_code == 200
    payload = response.json()
    assert payload["experiment_name"] == "api_test_run"
    assert payload["target_weights"]
    assert sum(payload["target_weights"].values()) <= 1.0
    assert payload["equity_curve"]


def test_research_summarize():
    demo_result = client.get("/research/demo").json()["result"]

    response = client.post("/research/summarize", json=demo_result)

    assert response.status_code == 200
    payload = response.json()
    assert payload["experiment_name"] == demo_result["experiment_name"]
    assert "cash_weight" in payload["backtest_metrics"]
    assert "score_buckets" in payload["factor_summary"]


def test_research_deepseek_mock_report_does_not_access_network():
    demo_result = client.get("/research/demo").json()["result"]

    with patch(
        "requests.post", side_effect=AssertionError("DeepSeek network call is not allowed")
    ) as post:
        response = client.post("/research/deepseek/mock-report", json=demo_result)

    assert response.status_code == 200
    payload = response.json()
    assert payload["metadata"]["mock_mode"] is True
    assert payload["research_note"]
    assert payload["risk_flags"]
    assert payload["counter_arguments"]
    assert payload["validation_result"]["target_weights_unchanged"] is True
    post.assert_not_called()


def test_research_api_outputs_do_not_contain_restricted_language():
    demo_result = client.get("/research/demo").json()["result"]
    summary = client.post("/research/summarize", json=demo_result).json()
    report = client.post("/research/deepseek/mock-report", json=demo_result).json()

    text = json.dumps(
        {"result": demo_result, "summary": summary, "report": report}, ensure_ascii=False
    )
    restricted = ["建议买入", "建议卖出", "推荐买入", "推荐卖出", "保证收益"]
    for phrase in restricted:
        assert phrase not in text


def test_real_run_list_latest_and_detail(real_runs_client: TestClient):
    listed = real_runs_client.get("/research/runs?limit=10")
    latest = real_runs_client.get("/research/runs/latest")
    detail = real_runs_client.get(f"/research/runs/{REAL_RUN_ID}")

    assert listed.status_code == 200
    assert listed.json()["data_source"] == "real_artifacts"
    assert listed.json()["count"] == 1
    assert listed.json()["runs"][0]["run_id"] == REAL_RUN_ID
    assert latest.status_code == 200
    assert latest.json()["summary"]["run_status"] == "partial_success"
    assert detail.status_code == 200
    assert detail.json()["metrics"]["annualized_return"] == 0.12
    assert detail.json()["benchmark_diagnostics"] == {}
    assert detail.json()["warning_summary"]["total"] == 3


def test_real_run_detail_and_report_include_benchmark_diagnostics(
    real_runs_client: TestClient,
    real_runs_root: Path,
):
    diagnostics = {
        "schema_version": 1,
        "benchmarks": {
            "000300": {
                "status": "unavailable",
                "canonical_symbol": "000300",
                "selected_provider": None,
                "selected_endpoint": None,
                "row_count": 0,
                "first_date": None,
                "last_date": None,
                "coverage_ratio": None,
                "cache_status": "miss",
                "attempts": [
                    {
                        "provider": "fixture_primary",
                        "status": "failed",
                        "reason_code": "provider_exception",
                        "reason": "sanitized fixture failure",
                    }
                ],
            }
        },
    }
    diagnostics_path = real_runs_root / REAL_RUN_ID / "benchmark_diagnostics.json"
    diagnostics_path.write_text(
        json.dumps(diagnostics, ensure_ascii=False),
        encoding="utf-8",
    )

    detail = real_runs_client.get(f"/research/runs/{REAL_RUN_ID}")
    report = real_runs_client.get(f"/research/runs/{REAL_RUN_ID}/report")

    assert detail.status_code == 200
    assert detail.json()["benchmark_diagnostics"] == diagnostics
    assert report.status_code == 200
    report_payload = report.json()
    assert report_payload["run_status"] == "partial_success"
    assert report_payload["benchmark_status"] == "unavailable"
    assert report_payload["benchmark_review"]["evidence"]["provider_diagnostics"] == diagnostics
    assert "benchmark_diagnostics.json" in (
        report_payload["research_boundaries"]["evidence"]["source_artifacts"]
    )


def test_real_run_report_is_deterministic_and_preserves_limitations(
    real_runs_client: TestClient,
    real_runs_root: Path,
):
    run_directory = real_runs_root / REAL_RUN_ID
    source_files = [
        "run_manifest.json",
        "metrics.json",
        "benchmark_metrics.json",
        "warnings.json",
        "holdings.parquet",
        "factor_snapshots.parquet",
        "trades.parquet",
    ]
    before = {filename: (run_directory / filename).read_bytes() for filename in source_files}
    with (
        patch(
            "autowealth.data.ashare_provider.AShareDataProvider.__init__",
            side_effect=AssertionError("network provider must not be initialized"),
        ),
        patch(
            "requests.post",
            side_effect=AssertionError("external network must not be called"),
        ) as post,
        patch(
            "autowealth.agents.deepseek_research_agent.DeepSeekResearchAgent.__init__",
            side_effect=AssertionError("DeepSeek must not be initialized"),
        ),
        patch(
            "autowealth.backtest.portfolio_backtester.PortfolioBacktester.run",
            side_effect=AssertionError("backtest and trade simulation must not run"),
        ),
    ):
        response = real_runs_client.get(f"/research/runs/{REAL_RUN_ID}/report")

    assert response.status_code == 200
    payload = response.json()
    assert payload["run_id"] == REAL_RUN_ID
    assert payload["locale"] == "en-US"
    assert response.headers["content-language"] == "en-US"
    assert payload["data_source"] == "real_artifacts"
    assert payload["generated_mode"] == "deterministic"
    assert payload["run_status"] == "partial_success"
    assert payload["benchmark_status"] == "unavailable"
    assert payload["warning_count"] == 3
    assert payload["benchmark_review"]["status"] == "unavailable"
    assert payload["benchmark_review"]["evidence"]["entries"]["000300"]["status"] == "unavailable"
    assert len(payload["data_quality_review"]["evidence"]["warnings"]) == 3
    assert payload["research_boundaries"]["evidence"]["deepseek_called"] is False
    assert payload["research_boundaries"]["evidence"]["trading_executed"] is False
    assert payload["research_boundaries"]["evidence"]["source_artifacts"] == source_files
    assert before == {
        filename: (run_directory / filename).read_bytes() for filename in source_files
    }
    restricted = ["建议买入", "建议卖出", "推荐买入", "推荐卖出", "保证收益"]
    report_text = json.dumps(payload, ensure_ascii=False)
    assert all(phrase not in report_text for phrase in restricted)
    post.assert_not_called()


def test_real_run_report_locales_preserve_machine_fields_and_numbers(
    real_runs_client: TestClient,
    real_runs_root: Path,
):
    run_directory = real_runs_root / REAL_RUN_ID
    source_files = [
        "run_manifest.json",
        "metrics.json",
        "benchmark_metrics.json",
        "warnings.json",
        "holdings.parquet",
        "factor_snapshots.parquet",
        "trades.parquet",
    ]
    before = {filename: (run_directory / filename).read_bytes() for filename in source_files}

    zh_response = real_runs_client.get(f"/research/runs/{REAL_RUN_ID}/report?locale=zh-CN")
    en_response = real_runs_client.get(f"/research/runs/{REAL_RUN_ID}/report?locale=en-US")

    assert zh_response.status_code == 200
    assert en_response.status_code == 200
    assert zh_response.headers["content-language"] == "zh-CN"
    assert en_response.headers["content-language"] == "en-US"
    zh = zh_response.json()
    en = en_response.json()
    assert zh["locale"] == "zh-CN"
    assert en["locale"] == "en-US"
    assert "研究运行" in zh["executive_summary"]["summary"]
    assert "Run" in en["executive_summary"]["summary"]
    assert zh["benchmark_review"]["summary"] == ("基准数据暂不可用，当前无法得出相对表现结论。")
    assert zh["macro_review"]["summary"] == ("由于缺少可用宏观数据，本次研究使用中性回退值。")
    assert zh["research_boundaries"]["summary"] == (
        "本报告仅用于研究与教育，不构成投资建议、交易指令或收益承诺；"
        "历史研究结果不代表未来表现。"
    )

    for field in ("run_id", "data_source", "generated_mode", "run_status", "benchmark_status"):
        assert zh[field] == en[field]
    assert _numeric_values(zh) == _numeric_values(en)
    assert [flag["code"] for flag in zh["risk_flags"]] == [
        flag["code"] for flag in en["risk_flags"]
    ]
    assert [flag["category"] for flag in zh["risk_flags"]] == [
        flag["category"] for flag in en["risk_flags"]
    ]
    assert [flag["severity"] for flag in zh["risk_flags"]] == [
        flag["severity"] for flag in en["risk_flags"]
    ]

    zh_evidence = zh["data_quality_review"]["evidence"]
    en_evidence = en["data_quality_review"]["evidence"]
    assert zh_evidence["warnings"] == en_evidence["warnings"]
    assert len(zh_evidence["warnings"]) == 3
    assert [item["source_message"] for item in zh_evidence["warning_presentations"]] == zh_evidence[
        "warnings"
    ]
    assert [item["source_message"] for item in en_evidence["warning_presentations"]] == en_evidence[
        "warnings"
    ]
    assert before == {
        filename: (run_directory / filename).read_bytes() for filename in source_files
    }


def test_real_run_report_rejects_unsupported_locale(
    real_runs_client: TestClient,
):
    response = real_runs_client.get(f"/research/runs/{REAL_RUN_ID}/report?locale=fr-FR")

    assert response.status_code == 422


def test_warning_presentations_preserve_193_source_messages():
    warnings = [f"price provider warning {index}" for index in range(193)]

    presentations = present_warnings(warnings, "zh-CN")

    assert len(presentations) == 193
    assert [item["source_message"] for item in presentations] == warnings
    assert all(item["category"] == "price_provider" for item in presentations)


def _numeric_values(
    value: object,
    path: tuple[str, ...] = (),
) -> dict[tuple[str, ...], float]:
    if isinstance(value, bool):
        return {}
    if isinstance(value, Number):
        return {path: float(value)}
    if isinstance(value, dict):
        result: dict[tuple[str, ...], float] = {}
        for key, item in value.items():
            result.update(_numeric_values(item, (*path, str(key))))
        return result
    if isinstance(value, list):
        result = {}
        for index, item in enumerate(value):
            result.update(_numeric_values(item, (*path, str(index))))
        return result
    return {}


def test_real_run_report_rejects_invalid_run_id(
    real_runs_client: TestClient,
):
    response = real_runs_client.get("/research/runs/bad.run/report")

    assert response.status_code == 400
    assert response.json()["code"] == "invalid_run_id"


def test_real_run_report_missing_artifact_is_structured(
    real_runs_root: Path,
):
    (real_runs_root / REAL_RUN_ID / "factor_snapshots.parquet").unlink()
    missing_client = TestClient(create_research_app(ResearchRunStore(real_runs_root)))

    response = missing_client.get(f"/research/runs/{REAL_RUN_ID}/report")

    assert response.status_code == 404
    assert response.json()["code"] == "research_artifact_not_found"
    assert "factor_snapshots.parquet" in response.json()["message"]


def test_real_run_equity_curve_is_bounded(real_runs_client: TestClient):
    response = real_runs_client.get(f"/research/runs/{REAL_RUN_ID}/equity-curve?downsample=2")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_points"] == 3
    assert payload["returned_points"] == 2
    assert payload["points"][0]["date"].startswith("2024-01-02")
    assert payload["points"][-1]["date"].startswith("2025-12-31")


def test_real_run_benchmark_unavailable_has_no_curve(
    real_runs_client: TestClient,
):
    response = real_runs_client.get(f"/research/runs/{REAL_RUN_ID}/benchmark-curve")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "unavailable"
    assert payload["points"] == []
    assert payload["reasons"]["000300"] == "fixture unavailable"


def test_real_run_holdings_factors_and_warnings(real_runs_client: TestClient):
    holdings = real_runs_client.get(f"/research/runs/{REAL_RUN_ID}/holdings?limit=10")
    factors = real_runs_client.get(f"/research/runs/{REAL_RUN_ID}/factors?limit=10")
    warnings = real_runs_client.get(
        f"/research/runs/{REAL_RUN_ID}/warnings?sample_limit=1&raw_limit=2"
    )

    assert holdings.status_code == 200
    assert holdings.json()["returned"] == 2
    assert {item["symbol"] for item in holdings.json()["records"]} == {
        "600001",
        "000002",
    }
    assert factors.status_code == 200
    assert factors.json()["coverage_overall"]["value"]["coverage_ratio"] == 0.5
    assert factors.json()["records"][0]["composite_weights"]
    assert warnings.status_code == 200
    assert warnings.json()["summary"]["total"] == 3
    assert warnings.json()["summary"]["raw_returned"] == 2


def test_real_run_not_found_returns_structured_404(
    real_runs_client: TestClient,
):
    response = real_runs_client.get("/research/runs/missing_run")

    assert response.status_code == 404
    assert response.json()["code"] == "research_run_not_found"
    assert "D:\\" not in response.text


def test_real_run_endpoints_do_not_initialize_network_provider(
    real_runs_client: TestClient,
):
    with patch(
        "autowealth.data.ashare_provider.AShareDataProvider.__init__",
        side_effect=AssertionError("network provider must not be initialized"),
    ):
        response = real_runs_client.get("/research/runs/latest")

    assert response.status_code == 200


def test_empty_real_runs_and_mock_demo_keep_distinct_sources(tmp_path: Path):
    empty_client = TestClient(create_research_app(ResearchRunStore(tmp_path / "empty_runs")))

    runs = empty_client.get("/research/runs")
    demo = empty_client.get("/research/demo")

    assert runs.status_code == 200
    assert runs.json() == {
        "data_source": "real_artifacts",
        "count": 0,
        "runs": [],
    }
    assert demo.status_code == 200
    assert demo.json()["mock_mode"] is True


def _run_request_body():
    symbols = mock_candidate_symbols()
    factor_scores = {
        symbol: {
            "score": score.score,
            "factor_scores": {"composite": score.score},
            "as_of_date": score.as_of_date,
        }
        for symbol, score in mock_factor_scores().items()
    }
    price_data = {}
    for symbol, frame in mock_price_data(symbols).items():
        serialized = frame.copy()
        serialized["date"] = serialized["date"].dt.strftime("%Y-%m-%d")
        price_data[symbol] = serialized.to_dict(orient="records")

    constraints = mock_portfolio_constraints()
    return {
        "experiment_name": "api_test_run",
        "start_date": "2020-01-01",
        "end_date": "2024-12-31",
        "candidate_symbols": symbols,
        "factor_scores": factor_scores,
        "price_data": price_data,
        "macro_multiplier": 1.1,
        "industries": mock_industries(),
        "constraints": {
            "max_position_weight": constraints.max_position_weight,
            "min_position_weight": constraints.min_position_weight,
            "max_industry_weight": constraints.max_industry_weight,
            "max_holdings": constraints.max_holdings,
            "min_holdings": constraints.min_holdings,
            "cash_weight_min": constraints.cash_weight_min,
            "cash_weight_max": constraints.cash_weight_max,
            "min_score": constraints.min_score,
        },
        "rebalance_frequency": "yearly",
    }


def _write_api_run(root: Path) -> None:
    dates = pd.to_datetime(["2024-01-02", "2024-12-31", "2025-12-31"])
    manifest = {
        "run_id": REAL_RUN_ID,
        "run_time": "2025-02-01T00:00:00+00:00",
        "experiment_name": "api artifact fixture",
        "run_status": "partial_success",
        "run_status_reasons": ["benchmark unavailable"],
        "data_range": {"start_date": "2024-01-01", "end_date": "2025-12-31"},
        "config_summary": {"portfolio_constraints": {"min_holdings": 2}},
        "coverage_summary": {
            "benchmark_status": "unavailable",
            "warning_count": 3,
            "price_coverage_ratio": 0.8,
            "macro_observation_count": 0,
            "holdings_count_by_rebalance": {"2025-01-02": 2},
            "factor_coverage_by_rebalance": {
                "2025-01-02": {
                    "value": {
                        "available_count": 1,
                        "missing_count": 1,
                        "coverage_ratio": 0.5,
                    }
                }
            },
            "factor_coverage_overall": {
                "value": {
                    "available_count": 1,
                    "missing_count": 1,
                    "coverage_ratio": 0.5,
                }
            },
        },
    }
    metrics = {
        "start_date": "2024-01-01",
        "end_date": "2025-12-31",
        "annualized_return": 0.12,
        "total_return": 0.25,
        "max_drawdown": -0.18,
        "sharpe_ratio": 0.9,
        "calmar_ratio": 0.66,
        "volatility": 0.2,
        "turnover": 0.4,
        "annual_returns": {"2024": 0.1, "2025": 0.13},
        "monthly_returns": {"2025-01": 0.01},
    }
    holdings = pd.DataFrame(
        {
            "date": [pd.Timestamp("2025-01-02")],
            "equity": [1_100_000],
            "cash": [220_000],
            "cash_weight": [0.2],
            "600001_shares": [1000.0],
            "600001_weight": [0.4],
            "000002_shares": [2000.0],
            "000002_weight": [0.4],
        }
    )
    trades = pd.DataFrame(
        {
            "date": [pd.Timestamp("2025-01-02")],
            "symbol": ["600001"],
            "side": ["buy"],
            "shares": [1000.0],
            "price": [10.0],
            "trade_value": [10_000.0],
            "cost": [5.0],
        }
    )
    factors = pd.DataFrame(
        {
            "rebalance_date": [pd.Timestamp("2025-01-02")],
            "symbol": ["600001"],
            "composite_score": [70.0],
            "composite_weights": ['{"value": 1.0}'],
            "value_available": [True],
            "value_score": [70.0],
            "warnings": [""],
        }
    )
    write_research_artifacts(
        root,
        config={"experiment_name": "api artifact fixture"},
        run_manifest=manifest,
        metrics=metrics,
        benchmark_metrics={
            "000300": {
                "status": "unavailable",
                "symbol": "000300",
                "reason": "fixture unavailable",
                "metrics": {},
            }
        },
        equity_curve=pd.Series([1_000_000, 1_100_000, 1_250_000], index=dates),
        benchmark_curve=pd.DataFrame(),
        holdings=holdings,
        trades=trades,
        factor_snapshots=factors,
        warnings=[
            "macro data is empty; neutral multiplier used",
            "benchmark 000300 unavailable",
            "factor warning: missing pe",
        ],
        run_id=REAL_RUN_ID,
        run_time=datetime(2025, 2, 1, tzinfo=timezone.utc),
    )
