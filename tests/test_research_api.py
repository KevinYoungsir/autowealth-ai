import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.modules["yfinance"] = MagicMock()

from fastapi.testclient import TestClient

from autowealth.api.research_server import app, create_research_app
from autowealth.research import (
    mock_candidate_symbols,
    mock_factor_scores,
    mock_industries,
    mock_portfolio_constraints,
    mock_price_data,
)


client = TestClient(app)


def test_research_health():
    response = client.get("/research/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["service"] == "autowealth-research-api"
    assert payload["mock_mode"] is True
    assert "version" in payload


def test_research_cors_allows_configured_dashboard_origins():
    origins = (
        "http://127.0.0.1:3000,http://localhost:3000,"
        "https://dashboard.outlook.xin"
    )
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

    with patch("requests.post", side_effect=AssertionError("DeepSeek network call is not allowed")) as post:
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

    text = json.dumps({"result": demo_result, "summary": summary, "report": report}, ensure_ascii=False)
    restricted = ["建议买入", "建议卖出", "推荐买入", "推荐卖出", "保证收益"]
    for phrase in restricted:
        assert phrase not in text


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
