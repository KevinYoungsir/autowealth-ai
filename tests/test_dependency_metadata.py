"""Static contracts for dependencies required by clean test runners."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

PYPROJECT_PATH = Path(__file__).resolve().parents[1] / "pyproject.toml"
_DISTRIBUTION_NAME = re.compile(r"^\s*(?P<name>[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?)")


def _normalize_distribution_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _requirement_distribution_name(requirement: str) -> str:
    """Extract only the leading distribution name from a requirement."""
    match = _DISTRIBUTION_NAME.match(requirement)
    if match is None:
        raise ValueError(f"requirement has no distribution name: {requirement!r}")
    return _normalize_distribution_name(match.group("name"))


def _load_dev_requirements() -> list[str]:
    with PYPROJECT_PATH.open("rb") as pyproject_file:
        pyproject = tomllib.load(pyproject_file)

    optional_dependencies = pyproject["project"]["optional-dependencies"]
    assert "dev" in optional_dependencies
    return optional_dependencies["dev"]


def test_dev_extra_declares_scikit_learn_without_modifying_pyproject() -> None:
    original_pyproject = PYPROJECT_PATH.read_bytes()

    dev_requirements = _load_dev_requirements()
    distribution_names = {
        _requirement_distribution_name(requirement) for requirement in dev_requirements
    }

    assert "scikit-learn" in distribution_names
    assert PYPROJECT_PATH.read_bytes() == original_pyproject


@pytest.mark.parametrize(
    "requirement",
    [
        "scikit-learn>=1.3.0",
        "Scikit_Learn==1.3.0",
        "SCIKIT.LEARN",
    ],
)
def test_requirement_name_normalization_matches_python_packaging_rules(
    requirement: str,
) -> None:
    assert _requirement_distribution_name(requirement) == "scikit-learn"


@pytest.mark.parametrize(
    "requirement",
    [
        "not-scikit-learn>=1.0",
        "scikit-learn-helper",
        "prefix.scikit_learn",
    ],
)
def test_requirement_name_matching_does_not_use_substrings(requirement: str) -> None:
    assert _requirement_distribution_name(requirement) != "scikit-learn"
