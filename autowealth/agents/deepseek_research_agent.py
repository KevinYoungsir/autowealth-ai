"""
DeepSeek-backed research-only agent.

The agent is intentionally separated from the legacy trading-signal agents. It
summarizes and reviews research pipeline outputs, but it does not modify target
weights or create trading instructions.
"""

from __future__ import annotations

import copy
import json
import math
import os
from dataclasses import asdict, is_dataclass
from typing import Any, Dict, List, Mapping, Optional

import pandas as pd

from autowealth.agents.prompts import (
    COUNTER_ARGUMENT_PROMPT,
    DEEPSEEK_RESEARCH_SYSTEM_PROMPT,
    RISK_PROMPT,
    SUMMARY_PROMPT,
    VALIDATION_PROMPT,
)
from autowealth.agents.schema import (
    CounterArgument,
    DeepSeekResearchReport,
    ResearchNote,
    ResearchValidationResult,
    RiskFlag,
)


FORBIDDEN_OUTPUT_PHRASES = ["建议买入", "建议卖出", "推荐买入", "推荐卖出", "保证收益"]


class DeepSeekResearchAgent:
    """
    Research-only wrapper around DeepSeek-compatible chat completions.

    mock_mode defaults to True so tests, demos and offline research never call a
    real API unless explicitly configured by the caller.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        mock_mode: bool = True,
        timeout: int = 30,
    ) -> None:
        self.api_key = api_key if api_key is not None else os.getenv("DEEPSEEK_API_KEY", "")
        self.base_url = base_url if base_url is not None else os.getenv("DEEPSEEK_BASE_URL", "")
        self.model = model if model is not None else os.getenv("DEEPSEEK_MODEL", "")
        self.mock_mode = mock_mode
        self.timeout = timeout

        if not self.mock_mode and not all([self.api_key, self.base_url, self.model]):
            raise ValueError(
                "DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL and DEEPSEEK_MODEL are required "
                "when mock_mode is False."
            )

    def summarize_research_result(self, research_result: object) -> Dict[str, Any]:
        """
        Return a structured research summary.
        """
        payload = self._research_result_payload(research_result)
        if self.mock_mode:
            output = self._mock_summary(payload)
        else:
            output = self._call_deepseek_json("summary", SUMMARY_PROMPT, payload)
        return self._ensure_safe_json_output(output)

    def analyze_risk_flags(self, research_result: object) -> Dict[str, Any]:
        """
        Return structured risk observations for research review.
        """
        payload = self._research_result_payload(research_result)
        if self.mock_mode:
            output = self._mock_risk_flags(payload)
        else:
            output = self._call_deepseek_json("risk_flags", RISK_PROMPT, payload)
        return self._ensure_safe_json_output(output)

    def generate_counter_arguments(self, research_result: object) -> Dict[str, Any]:
        """
        Return structured counter-arguments for the research experiment.
        """
        payload = self._research_result_payload(research_result)
        if self.mock_mode:
            output = self._mock_counter_arguments(payload)
        else:
            output = self._call_deepseek_json("counter_arguments", COUNTER_ARGUMENT_PROMPT, payload)
        return self._ensure_safe_json_output(output)

    def validate_research_consistency(self, research_result: object) -> Dict[str, Any]:
        """
        Return structured consistency checks without mutating target weights.
        """
        original_weights = copy.deepcopy(self._extract_target_weights(research_result))
        payload = self._research_result_payload(research_result)
        if self.mock_mode:
            output = self._mock_validation(payload)
        else:
            output = self._call_deepseek_json("validation", VALIDATION_PROMPT, payload)

        output["target_weights_unchanged"] = original_weights == self._extract_target_weights(
            research_result
        )
        return self._ensure_safe_json_output(output)

    def build_research_report(self, research_result: object) -> Dict[str, Any]:
        """
        Build a complete structured research report.
        """
        summary = self.summarize_research_result(research_result)
        risk_review = self.analyze_risk_flags(research_result)
        counter_review = self.generate_counter_arguments(research_result)
        validation = self.validate_research_consistency(research_result)
        report = DeepSeekResearchReport(
            research_note=summary,
            risk_flags=risk_review.get("risk_flags", []),
            counter_arguments=counter_review.get("counter_arguments", []),
            validation_result=validation,
            metadata={
                "agent": "DeepSeekResearchAgent",
                "mock_mode": self.mock_mode,
                "model": self.model if not self.mock_mode else "mock",
            },
            warnings=list(
                dict.fromkeys(
                    summary.get("warnings", [])
                    + risk_review.get("warnings", [])
                    + validation.get("warnings", [])
                )
            ),
        ).to_dict()
        return self._ensure_safe_json_output(report)

    def _call_deepseek_json(self, task: str, prompt: str, payload: Mapping[str, Any]) -> Dict[str, Any]:
        import requests

        endpoint = self.base_url.rstrip("/") + "/chat/completions"
        response = requests.post(
            endpoint,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": DEEPSEEK_RESEARCH_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": json.dumps(
                            {"task": task, "instruction": prompt, "payload": payload},
                            ensure_ascii=False,
                            default=str,
                        ),
                    },
                ],
                "response_format": {"type": "json_object"},
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        result = response.json()
        content = result["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        if not isinstance(parsed, dict):
            raise ValueError("DeepSeek response must be a JSON object.")
        return parsed

    def _mock_summary(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        selected_symbols = list(payload.get("selected_symbols", []))
        target_weights = dict(payload.get("target_weights", {}))
        cash_weight = self._cash_weight(target_weights)
        metrics = dict(payload.get("backtest_metrics", {}))
        note = ResearchNote(
            title="Structured research experiment summary",
            summary=(
                f"Experiment {payload.get('experiment_name', 'unknown')} reviewed "
                f"{len(selected_symbols)} selected symbols with cash weight {cash_weight:.4f}."
            ),
            key_points=[
                f"Research window: {payload.get('start_date')} to {payload.get('end_date')}.",
                f"Selected symbol count: {len(selected_symbols)}.",
                f"Annualized return metric: {metrics.get('annualized_return')}.",
                f"Maximum drawdown metric: {metrics.get('max_drawdown')}.",
                f"Macro regime: {payload.get('macro_summary', {}).get('regime', 'not_provided')}.",
            ],
            limitations=[
                "Mock mode uses supplied structured fields only.",
                "Historical metrics do not imply future outcomes.",
                "This output does not contain trade execution instructions.",
            ],
            evidence={
                "selected_symbols": selected_symbols,
                "target_weight_sum": round(sum(target_weights.values()), 10),
                "cash_weight": cash_weight,
                "metric_names": sorted(metrics.keys()),
            },
            warnings=list(payload.get("warnings", [])),
        )
        return note.to_dict()

    def _mock_risk_flags(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        target_weights = dict(payload.get("target_weights", {}))
        metrics = dict(payload.get("backtest_metrics", {}))
        warnings = list(payload.get("warnings", []))
        flags: List[RiskFlag] = []

        max_drawdown = self._as_float(metrics.get("max_drawdown"))
        if max_drawdown is not None:
            severity = "high" if max_drawdown <= -0.35 else "medium" if max_drawdown <= -0.2 else "low"
            flags.append(
                RiskFlag(
                    category="drawdown",
                    severity=severity,
                    description="Review historical drawdown depth in the research backtest.",
                    evidence={"max_drawdown": max_drawdown},
                    review_focus="Stress periods, data coverage and rebalance assumptions.",
                )
            )

        if target_weights:
            top_symbol, top_weight = max(target_weights.items(), key=lambda item: item[1])
            severity = "medium" if top_weight >= 0.12 else "low"
            flags.append(
                RiskFlag(
                    category="concentration",
                    severity=severity,
                    description="Review concentration exposure in target weights.",
                    evidence={"top_symbol": top_symbol, "top_weight": top_weight},
                    review_focus="Single-name and industry concentration assumptions.",
                )
            )

        cash_weight = self._cash_weight(target_weights)
        if cash_weight >= 0.3:
            flags.append(
                RiskFlag(
                    category="cash_weight",
                    severity="medium",
                    description="Cash weight is material in the research result.",
                    evidence={"cash_weight": cash_weight},
                    review_focus="Macro multiplier and portfolio constraint effects.",
                )
            )

        if warnings:
            flags.append(
                RiskFlag(
                    category="pipeline_warnings",
                    severity="medium",
                    description="Pipeline warnings require research review.",
                    evidence={"warning_count": len(warnings), "warnings": warnings[:5]},
                    review_focus="Input completeness and rejected symbol reasons.",
                )
            )

        if not flags:
            flags.append(
                RiskFlag(
                    category="general_review",
                    severity="low",
                    description="No major structured risk flag was triggered by mock rules.",
                    evidence={"selected_count": len(payload.get("selected_symbols", []))},
                    review_focus="Continue checking assumptions before downstream use.",
                )
            )

        return {
            "risk_flags": [flag.to_dict() for flag in flags],
            "warnings": warnings,
            "metadata": {"agent": "DeepSeekResearchAgent", "mock_mode": True},
        }

    def _mock_counter_arguments(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        arguments = [
            CounterArgument(
                topic="factor_stability",
                argument=(
                    "The current factor snapshot may not remain stable across different "
                    "market regimes or reporting periods."
                ),
                evidence_needed=[
                    "Rolling factor rank history",
                    "Out-of-sample factor decay analysis",
                    "Industry-neutral factor diagnostics",
                ],
                affected_assumptions=["factor_summary", "selected_symbols"],
                research_value="Tests whether selected names depend on one point-in-time score.",
            ),
            CounterArgument(
                topic="macro_sensitivity",
                argument=(
                    "The macro multiplier may compress diverse macro information into a "
                    "single exposure scalar."
                ),
                evidence_needed=[
                    "Macro regime transition history",
                    "Scenario analysis under slowdown and recovery labels",
                    "External risk event timeline",
                ],
                affected_assumptions=["macro_summary", "target_weights"],
                research_value="Checks whether macro interpretation is too coarse.",
            ),
            CounterArgument(
                topic="backtest_assumptions",
                argument=(
                    "Backtest metrics can be sensitive to data quality, rebalance timing, "
                    "transaction cost settings and survivorship controls."
                ),
                evidence_needed=[
                    "Data quality report",
                    "Rebalance calendar audit",
                    "Cost and slippage sensitivity table",
                ],
                affected_assumptions=["backtest_metrics", "equity_curve"],
                research_value="Separates modeling assumptions from observed history.",
            ),
        ]
        return {
            "counter_arguments": [argument.to_dict() for argument in arguments],
            "metadata": {
                "agent": "DeepSeekResearchAgent",
                "mock_mode": True,
                "experiment_name": payload.get("experiment_name"),
            },
        }

    def _mock_validation(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        target_weights = dict(payload.get("target_weights", {}))
        selected_symbols = set(payload.get("selected_symbols", []))
        backtest_metrics = dict(payload.get("backtest_metrics", {}))
        issues: List[str] = []
        warnings = list(payload.get("warnings", []))
        checks = {
            "target_weight_sum_lte_one": sum(target_weights.values()) <= 1.0 + 1e-9,
            "selected_symbols_have_weights": selected_symbols.issubset(set(target_weights.keys())),
            "backtest_metrics_present": all(
                key in backtest_metrics
                for key in ["annualized_return", "max_drawdown", "sharpe_ratio", "calmar_ratio"]
            ),
            "equity_curve_non_empty": bool(payload.get("equity_curve", {}).get("length", 0)),
            "no_forbidden_language": not self._contains_forbidden_phrase(payload),
        }
        for check_name, passed in checks.items():
            if not passed:
                issues.append(f"Consistency check failed: {check_name}")

        validation = ResearchValidationResult(
            is_consistent=all(checks.values()),
            checks=checks,
            issues=issues,
            warnings=warnings,
            target_weights_unchanged=True,
        )
        return validation.to_dict()

    def _research_result_payload(self, research_result: object) -> Dict[str, Any]:
        raw = self._to_plain_data(research_result)
        payload = {
            "experiment_name": raw.get("experiment_name"),
            "start_date": raw.get("start_date"),
            "end_date": raw.get("end_date"),
            "candidate_symbols": list(raw.get("candidate_symbols", []) or []),
            "selected_symbols": list(raw.get("selected_symbols", []) or []),
            "rejected_symbols": dict(raw.get("rejected_symbols", {}) or {}),
            "factor_summary": self._to_plain_data(raw.get("factor_summary", {}) or {}),
            "macro_summary": self._to_plain_data(raw.get("macro_summary", {}) or {}),
            "target_weights": dict(raw.get("target_weights", {}) or {}),
            "backtest_metrics": self._to_plain_data(raw.get("backtest_metrics", {}) or {}),
            "equity_curve": self._summarize_equity_curve(raw.get("equity_curve")),
            "warnings": list(raw.get("warnings", []) or []),
            "explanation": raw.get("explanation", ""),
        }
        return self._json_ready(payload)

    def _extract_target_weights(self, research_result: object) -> Dict[str, float]:
        raw = self._to_plain_data(research_result)
        return dict(raw.get("target_weights", {}) or {})

    def _summarize_equity_curve(self, equity_curve: object) -> Dict[str, Any]:
        if equity_curve is None:
            return {"length": 0, "start": None, "end": None}
        if isinstance(equity_curve, pd.DataFrame):
            if equity_curve.empty:
                return {"length": 0, "start": None, "end": None}
            values = equity_curve.iloc[:, 0]
        elif isinstance(equity_curve, pd.Series):
            if equity_curve.empty:
                return {"length": 0, "start": None, "end": None}
            values = equity_curve
        elif isinstance(equity_curve, list):
            return {
                "length": len(equity_curve),
                "start": equity_curve[0] if equity_curve else None,
                "end": equity_curve[-1] if equity_curve else None,
            }
        else:
            return {"length": 0, "start": None, "end": None}

        return {
            "length": int(len(values)),
            "start": self._json_ready(values.iloc[0]),
            "end": self._json_ready(values.iloc[-1]),
        }

    def _to_plain_data(self, value: object) -> Any:
        if is_dataclass(value):
            return {key: self._to_plain_data(val) for key, val in asdict(value).items()}
        if isinstance(value, Mapping):
            return {str(key): self._to_plain_data(val) for key, val in value.items()}
        if isinstance(value, (list, tuple)):
            return [self._to_plain_data(item) for item in value]
        return value

    def _json_ready(self, value: Any) -> Any:
        if isinstance(value, Mapping):
            return {str(key): self._json_ready(val) for key, val in value.items()}
        if isinstance(value, (list, tuple)):
            return [self._json_ready(item) for item in value]
        if isinstance(value, pd.Timestamp):
            return value.isoformat()
        if hasattr(value, "item"):
            try:
                return value.item()
            except ValueError:
                return str(value)
        if isinstance(value, float) and not math.isfinite(value):
            return None
        return value

    def _ensure_safe_json_output(self, output: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(output, dict):
            raise ValueError("Agent output must be a JSON object represented as dict.")
        json.dumps(output, ensure_ascii=False, default=str)
        if self._contains_forbidden_phrase(output):
            raise ValueError("Agent output contains forbidden investment-advice language.")
        return output

    def _contains_forbidden_phrase(self, value: Any) -> bool:
        if isinstance(value, str):
            return any(phrase in value for phrase in FORBIDDEN_OUTPUT_PHRASES)
        if isinstance(value, Mapping):
            return any(self._contains_forbidden_phrase(item) for item in value.values())
        if isinstance(value, (list, tuple, set)):
            return any(self._contains_forbidden_phrase(item) for item in value)
        return False

    def _cash_weight(self, target_weights: Mapping[str, float]) -> float:
        return max(0.0, 1.0 - sum(float(weight) for weight in target_weights.values()))

    def _as_float(self, value: Any) -> Optional[float]:
        if value is None:
            return None
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return number if math.isfinite(number) else None
