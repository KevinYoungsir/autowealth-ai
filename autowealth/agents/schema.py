"""
Structured schemas for research-only agent outputs.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List


@dataclass
class ResearchNote:
    """
    Structured research summary generated from a research pipeline result.
    """

    title: str
    summary: str
    key_points: List[str]
    limitations: List[str]
    evidence: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RiskFlag:
    """
    A structured risk observation for research review.
    """

    category: str
    severity: str
    description: str
    evidence: Dict[str, Any] = field(default_factory=dict)
    review_focus: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CounterArgument:
    """
    A structured challenge to assumptions in a research experiment.
    """

    topic: str
    argument: str
    evidence_needed: List[str]
    affected_assumptions: List[str]
    research_value: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ResearchValidationResult:
    """
    Structured consistency checks for a research pipeline output.
    """

    is_consistent: bool
    checks: Dict[str, bool]
    issues: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    target_weights_unchanged: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DeepSeekResearchReport:
    """
    Full structured report from the research agent.
    """

    research_note: Dict[str, Any]
    risk_flags: List[Dict[str, Any]]
    counter_arguments: List[Dict[str, Any]]
    validation_result: Dict[str, Any]
    metadata: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
