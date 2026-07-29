"""Verify AutoWealth product release metadata without importing the package."""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
import tomllib
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Sequence

SEMVER_TEXT = r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)"
SEMVER_RE = re.compile(rf"^{SEMVER_TEXT}$")
TAG_RE = re.compile(rf"^v(?P<version>{SEMVER_TEXT})$")
PACKAGE_NAME = "autowealth-ai"


class ReleaseMetadataError(ValueError):
    """Raised when release metadata is missing, malformed, or inconsistent."""


@dataclass(frozen=True)
class VerificationResult:
    product_version: str
    release_date: str
    changelog_heading: str
    tag: str | None
    artifacts: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "artifacts": list(self.artifacts),
            "changelog_heading": self.changelog_heading,
            "dist_checked": bool(self.artifacts),
            "product_version": self.product_version,
            "release_date": self.release_date,
            "status": "ok",
            "tag": self.tag,
        }


def _read_product_version(project_root: Path) -> str:
    with (project_root / "pyproject.toml").open("rb") as handle:
        data = tomllib.load(handle)
    try:
        version = data["project"]["version"]
    except (KeyError, TypeError) as exc:
        raise ReleaseMetadataError("pyproject.toml is missing project.version") from exc
    if not isinstance(version, str) or not SEMVER_RE.fullmatch(version):
        raise ReleaseMetadataError(
            "pyproject.toml project.version must be strict MAJOR.MINOR.PATCH"
        )
    return version


def _read_source_version(project_root: Path) -> str:
    source_path = project_root / "autowealth" / "__init__.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    values: list[str] = []
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if any(
            isinstance(target, ast.Name) and target.id == "__version__" for target in node.targets
        ):
            if not isinstance(node.value, ast.Constant) or not isinstance(node.value.value, str):
                raise ReleaseMetadataError("autowealth.__version__ must be a string literal")
            values.append(node.value.value)
    if len(values) != 1:
        raise ReleaseMetadataError("autowealth/__init__.py must define __version__ exactly once")
    return values[0]


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if type(value) is not dict:
        raise ReleaseMetadataError(f"{path.name} root must be a JSON object")
    return value


def _find_release_heading(changelog: str, version: str) -> tuple[re.Match[str], str]:
    pattern = re.compile(
        rf"^## \[{re.escape(version)}\] - (?P<date>\d{{4}}-\d{{2}}-\d{{2}})[ \t]*$",
        re.MULTILINE,
    )
    matches = list(pattern.finditer(changelog))
    if len(matches) != 1:
        raise ReleaseMetadataError(
            f"CHANGELOG.md must contain exactly one heading: ## [{version}] - YYYY-MM-DD"
        )
    release_date = matches[0].group("date")
    try:
        date.fromisoformat(release_date)
    except ValueError as exc:
        raise ReleaseMetadataError(
            f"CHANGELOG.md has an invalid release date: {release_date}"
        ) from exc
    return matches[0], release_date


def extract_release_notes(project_root: Path, version: str) -> str:
    """Return exactly one version section without falling back to another release."""

    changelog = (project_root / "CHANGELOG.md").read_text(encoding="utf-8")
    heading, _ = _find_release_heading(changelog, version)
    next_heading = re.search(r"^## \[", changelog[heading.end() :], re.MULTILINE)
    end = heading.end() + next_heading.start() if next_heading else len(changelog)
    return changelog[heading.start() : end].strip() + "\n"


def _normalized_distribution_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def _artifact_identity(path: Path) -> tuple[str, str] | None:
    name = path.name
    if name.endswith(".whl"):
        parts = name[:-4].split("-")
        if len(parts) < 5:
            raise ReleaseMetadataError(f"invalid wheel filename: {name}")
        return parts[0], parts[1]
    if name.endswith(".tar.gz"):
        match = re.fullmatch(rf"(?P<name>.+)-(?P<version>{SEMVER_TEXT})\.tar\.gz", name)
        if not match:
            raise ReleaseMetadataError(f"invalid sdist filename: {name}")
        return match.group("name"), match.group("version")
    return None


def _validate_dist(dist_dir: Path, version: str) -> tuple[str, ...]:
    if not dist_dir.is_dir():
        raise ReleaseMetadataError(f"dist directory does not exist: {dist_dir}")
    wheel_count = 0
    sdist_count = 0
    artifacts: list[str] = []
    errors: list[str] = []
    for path in sorted(dist_dir.iterdir(), key=lambda item: item.name):
        if not path.is_file():
            continue
        identity = _artifact_identity(path)
        if identity is None:
            continue
        distribution, artifact_version = identity
        artifacts.append(path.name)
        wheel_count += int(path.name.endswith(".whl"))
        sdist_count += int(path.name.endswith(".tar.gz"))
        if _normalized_distribution_name(distribution) != PACKAGE_NAME:
            errors.append(f"unexpected distribution name in {path.name}")
        if artifact_version != version:
            errors.append(
                f"artifact {path.name} has version {artifact_version}, expected {version}"
            )
    if wheel_count == 0:
        errors.append("dist directory must contain a wheel")
    if sdist_count == 0:
        errors.append("dist directory must contain an sdist")
    if errors:
        raise ReleaseMetadataError("; ".join(errors))
    return tuple(artifacts)


def verify_release_metadata(
    project_root: Path,
    *,
    expected_version: str | None = None,
    tag: str | None = None,
    dist_dir: Path | None = None,
) -> VerificationResult:
    """Validate product metadata and optional tag/package artifacts."""

    project_root = project_root.resolve()
    product_version = _read_product_version(project_root)
    errors: list[str] = []

    if expected_version is not None:
        if not SEMVER_RE.fullmatch(expected_version):
            errors.append("expected version must be strict MAJOR.MINOR.PATCH")
        elif expected_version != product_version:
            errors.append(
                "expected version "
                f"{expected_version} does not match product version {product_version}"
            )

    normalized_tag: str | None = None
    if tag is not None:
        tag_match = TAG_RE.fullmatch(tag)
        if not tag_match:
            errors.append("tag must match strict format vMAJOR.MINOR.PATCH")
        elif tag_match.group("version") != product_version:
            errors.append(f"tag {tag} does not match product version {product_version}")
        else:
            normalized_tag = tag

    package_json = _read_json(project_root / "frontend" / "package.json")
    package_lock = _read_json(project_root / "frontend" / "package-lock.json")
    lock_packages = package_lock.get("packages")
    root_package = lock_packages.get("") if type(lock_packages) is dict else None
    observed_versions = {
        "autowealth.__version__": _read_source_version(project_root),
        "frontend/package.json version": package_json.get("version"),
        "frontend/package-lock.json version": package_lock.get("version"),
        "frontend/package-lock.json packages[''].version": (
            root_package.get("version") if type(root_package) is dict else None
        ),
    }
    for label, observed in observed_versions.items():
        if observed != product_version:
            errors.append(f"{label} is {observed!r}, expected {product_version!r}")

    changelog = (project_root / "CHANGELOG.md").read_text(encoding="utf-8")
    try:
        heading, release_date = _find_release_heading(changelog, product_version)
    except ReleaseMetadataError as exc:
        errors.append(str(exc))
        heading = None
        release_date = ""

    if errors:
        raise ReleaseMetadataError("; ".join(errors))

    artifacts = _validate_dist(dist_dir.resolve(), product_version) if dist_dir else ()
    assert heading is not None
    return VerificationResult(
        product_version=product_version,
        release_date=release_date,
        changelog_heading=heading.group(0).strip(),
        tag=normalized_tag,
        artifacts=artifacts,
    )


def _write_release_notes(destination: Path, project_root: Path, notes: str) -> None:
    resolved_root = project_root.resolve()
    resolved_destination = destination.resolve()
    try:
        resolved_destination.relative_to(resolved_root)
    except ValueError:
        pass
    else:
        raise ReleaseMetadataError("release notes output must be outside the repository")
    if not resolved_destination.parent.is_dir():
        raise ReleaseMetadataError("release notes output directory does not exist")
    resolved_destination.write_text(notes, encoding="utf-8")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="repository root (defaults to the script's parent repository)",
    )
    parser.add_argument("--expected-version")
    parser.add_argument("--tag")
    parser.add_argument("--dist-dir", type=Path)
    parser.add_argument("--print-release-notes", action="store_true")
    parser.add_argument("--output-release-notes", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    project_root = args.project_root.resolve()
    try:
        result = verify_release_metadata(
            project_root,
            expected_version=args.expected_version,
            tag=args.tag,
            dist_dir=args.dist_dir,
        )
        notes = extract_release_notes(project_root, result.product_version)
        if args.output_release_notes:
            _write_release_notes(args.output_release_notes, project_root, notes)
        summary = result.as_dict()
        if args.output_release_notes:
            summary["release_notes_output"] = str(args.output_release_notes.resolve())
        if args.print_release_notes:
            summary["release_notes"] = notes
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
        return 0
    except (
        OSError,
        SyntaxError,
        json.JSONDecodeError,
        tomllib.TOMLDecodeError,
        ReleaseMetadataError,
    ) as exc:
        payload = {
            "code": "release_metadata_invalid",
            "errors": [str(exc)],
            "status": "error",
        }
        print(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
