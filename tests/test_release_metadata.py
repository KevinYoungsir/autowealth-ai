from __future__ import annotations

import hashlib
import io
import json
import socket
import tarfile
import zipfile
from pathlib import Path

import pytest

from scripts.verify_release_metadata import (
    ReleaseMetadataError,
    extract_release_notes,
    main,
    verify_release_metadata,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.16.0"


def _write_fixture_repository(
    root: Path,
    *,
    pyproject_version: str = VERSION,
    source_version: str = VERSION,
    package_version: str = VERSION,
    lock_version: str = VERSION,
    lock_root_version: str = VERSION,
    changelog: str | None = None,
) -> Path:
    (root / "autowealth").mkdir(parents=True)
    (root / "frontend").mkdir()
    (root / "pyproject.toml").write_text(
        '[project]\nname = "autowealth-ai"\n' f'version = "{pyproject_version}"\n',
        encoding="utf-8",
    )
    (root / "autowealth" / "__init__.py").write_text(
        f'__version__ = "{source_version}"\n',
        encoding="utf-8",
    )
    (root / "frontend" / "package.json").write_text(
        json.dumps({"name": "dashboard", "version": package_version}),
        encoding="utf-8",
    )
    (root / "frontend" / "package-lock.json").write_text(
        json.dumps(
            {
                "name": "dashboard",
                "version": lock_version,
                "lockfileVersion": 3,
                "packages": {"": {"name": "dashboard", "version": lock_root_version}},
            }
        ),
        encoding="utf-8",
    )
    changelog_text = changelog or (
        "# Changelog\n\n"
        "## [未发布]\n\n"
        "## [0.16.0] - 2026-07-29\n\n"
        "### 新增\n"
        "- Current release.\n\n"
        "## [0.15.1] - 2026-07-17\n\n"
        "- Previous release.\n\n"
        "[未发布]: https://example.test/compare/v0.16.0...HEAD\n"
        "[0.16.0]: https://example.test/compare/v0.15.1...v0.16.0\n"
        "[0.15.1]: https://example.test/releases/v0.15.1\n"
    )
    (root / "CHANGELOG.md").write_text(changelog_text, encoding="utf-8")
    return root


def _metadata_bytes(version: str = VERSION) -> bytes:
    return ("Metadata-Version: 2.4\n" "Name: autowealth-ai\n" f"Version: {version}\n" "\n").encode(
        "utf-8"
    )


def _write_wheel(path: Path, *, metadata_version: str | None = None) -> None:
    with zipfile.ZipFile(path, mode="w") as archive:
        archive.writestr(
            f"autowealth_ai-{metadata_version or VERSION}.dist-info/METADATA",
            _metadata_bytes(metadata_version or VERSION),
        )


def _write_sdist(path: Path, *, metadata_version: str | None = None) -> None:
    version = metadata_version or VERSION
    payload = _metadata_bytes(version)
    member = tarfile.TarInfo(name=f"autowealth_ai-{version}/PKG-INFO")
    member.size = len(payload)
    with tarfile.open(path, mode="w:gz") as archive:
        archive.addfile(member, io.BytesIO(payload))


def _write_artifact_pair(dist: Path, *, version: str = VERSION) -> tuple[Path, Path]:
    wheel = dist / f"autowealth_ai-{version}-py3-none-any.whl"
    sdist = dist / f"autowealth_ai-{version}.tar.gz"
    _write_wheel(wheel, metadata_version=version)
    _write_sdist(sdist, metadata_version=version)
    return wheel, sdist


def _write_checksums(dist: Path, artifacts: tuple[Path, Path]) -> Path:
    checksum = dist / "SHA256SUMS.txt"
    lines = [
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}"
        for path in sorted(artifacts, key=lambda item: item.name)
    ]
    checksum.write_text("\n".join(lines) + "\n", encoding="ascii")
    return checksum


def _verify(root: Path, **kwargs: object):
    return verify_release_metadata(root, **kwargs)


def test_current_repository_product_versions_are_consistent() -> None:
    paths = [
        REPOSITORY_ROOT / "pyproject.toml",
        REPOSITORY_ROOT / "autowealth" / "__init__.py",
        REPOSITORY_ROOT / "frontend" / "package.json",
        REPOSITORY_ROOT / "frontend" / "package-lock.json",
        REPOSITORY_ROOT / "CHANGELOG.md",
    ]
    before = {path: path.read_bytes() for path in paths}

    result = _verify(REPOSITORY_ROOT, expected_version=VERSION)

    assert result.product_version == VERSION
    assert {path: path.read_bytes() for path in paths} == before


def test_pyproject_version_is_authoritative(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = _write_fixture_repository(tmp_path, pyproject_version="0.15.1")
    fixture_before = {
        path.relative_to(root): path.read_bytes() for path in root.rglob("*") if path.is_file()
    }
    repository_paths = [
        REPOSITORY_ROOT / "pyproject.toml",
        REPOSITORY_ROOT / "autowealth" / "__init__.py",
        REPOSITORY_ROOT / "frontend" / "package.json",
        REPOSITORY_ROOT / "frontend" / "package-lock.json",
        REPOSITORY_ROOT / "CHANGELOG.md",
    ]
    repository_before = {path: path.read_bytes() for path in repository_paths}

    exit_code = main(["--project-root", str(root)])

    captured = capsys.readouterr()
    error = json.loads(captured.err)
    assert exit_code != 0
    assert error["code"] == "release_metadata_invalid"
    assert "autowealth.__version__ is '0.16.0', expected '0.15.1'" in error["errors"][0]
    assert "frontend/package.json version is '0.16.0', expected '0.15.1'" in error["errors"][0]
    fixture_after = {
        path.relative_to(root): path.read_bytes() for path in root.rglob("*") if path.is_file()
    }
    assert fixture_after == fixture_before
    assert {path: path.read_bytes() for path in repository_paths} == repository_before


def test_source_version_mismatch_fails(tmp_path: Path) -> None:
    root = _write_fixture_repository(tmp_path, source_version="0.15.1")

    with pytest.raises(ReleaseMetadataError, match="autowealth.__version__"):
        _verify(root)


def test_package_json_version_mismatch_fails(tmp_path: Path) -> None:
    root = _write_fixture_repository(tmp_path, package_version="0.15.1")

    with pytest.raises(ReleaseMetadataError, match="frontend/package.json"):
        _verify(root)


def test_package_lock_top_level_version_mismatch_fails(tmp_path: Path) -> None:
    root = _write_fixture_repository(tmp_path, lock_version="0.15.1")

    with pytest.raises(ReleaseMetadataError, match="package-lock.json version"):
        _verify(root)


def test_package_lock_root_package_version_mismatch_fails(tmp_path: Path) -> None:
    root = _write_fixture_repository(tmp_path, lock_root_version="0.15.1")

    with pytest.raises(ReleaseMetadataError, match=r"packages\[''\]\.version"):
        _verify(root)


def test_exact_release_heading_is_required_and_accepted(tmp_path: Path) -> None:
    root = _write_fixture_repository(tmp_path)

    result = _verify(root)

    assert result.changelog_heading == "## [0.16.0] - 2026-07-29"
    assert result.release_date == "2026-07-29"


def test_older_heading_does_not_replace_missing_current_heading(tmp_path: Path) -> None:
    root = _write_fixture_repository(
        tmp_path,
        changelog="# Changelog\n\n## [0.15.1] - 2026-07-17\n\n- Previous release.\n",
    )

    with pytest.raises(ReleaseMetadataError, match=r"\[0\.16\.0\]"):
        _verify(root)


def test_matching_strict_tag_passes(tmp_path: Path) -> None:
    root = _write_fixture_repository(tmp_path)

    result = _verify(root, tag="v0.16.0")

    assert result.tag == "v0.16.0"


def test_mismatched_tag_fails(tmp_path: Path) -> None:
    root = _write_fixture_repository(tmp_path)

    with pytest.raises(ReleaseMetadataError, match="does not match product version"):
        _verify(root, tag="v0.15.1")


@pytest.mark.parametrize(
    "tag",
    [
        "0.16.0",
        "v0.16",
        "release-v0.16.0",
        "v0.16.0-beta",
    ],
)
def test_non_strict_semver_tags_fail(tmp_path: Path, tag: str) -> None:
    root = _write_fixture_repository(tmp_path)

    with pytest.raises(ReleaseMetadataError, match="strict format"):
        _verify(root, tag=tag)


def test_release_notes_extract_only_requested_section(tmp_path: Path) -> None:
    root = _write_fixture_repository(tmp_path)

    notes = extract_release_notes(root, VERSION)

    assert notes.startswith("## [0.16.0] - 2026-07-29")
    assert "Current release." in notes
    assert "## [未发布]" not in notes
    assert "[未发布]:" not in notes


def test_release_notes_exclude_previous_release(tmp_path: Path) -> None:
    root = _write_fixture_repository(tmp_path)

    notes = extract_release_notes(root, VERSION)

    assert "## [0.15.1]" not in notes
    assert "Previous release." not in notes
    assert "[0.16.0]:" not in notes
    assert "[0.15.1]:" not in notes
    assert "compare/v0.16.0...HEAD" not in notes


def test_dist_with_old_wheel_and_sdist_versions_fails(tmp_path: Path) -> None:
    root = _write_fixture_repository(tmp_path / "repo")
    dist = tmp_path / "dist"
    dist.mkdir()
    _write_artifact_pair(dist, version="0.1.0")

    with pytest.raises(ReleaseMetadataError, match="0.1.0"):
        _verify(root, dist_dir=dist)


def test_dist_with_current_wheel_and_sdist_versions_passes(tmp_path: Path) -> None:
    root = _write_fixture_repository(tmp_path / "repo")
    dist = tmp_path / "dist"
    dist.mkdir()
    wheel = "autowealth_ai-0.16.0-py3-none-any.whl"
    sdist = "autowealth_ai-0.16.0.tar.gz"
    _write_artifact_pair(dist)

    result = _verify(root, dist_dir=dist)

    assert result.artifacts == (wheel, sdist)


def test_dist_with_only_sdist_fails_for_missing_wheel(tmp_path: Path) -> None:
    root = _write_fixture_repository(tmp_path / "repo")
    dist = tmp_path / "dist"
    dist.mkdir()
    _write_sdist(dist / "autowealth_ai-0.16.0.tar.gz")

    with pytest.raises(ReleaseMetadataError, match="exactly one wheel; found 0"):
        _verify(root, dist_dir=dist)


def test_dist_with_only_wheel_fails_for_missing_sdist(tmp_path: Path) -> None:
    root = _write_fixture_repository(tmp_path / "repo")
    dist = tmp_path / "dist"
    dist.mkdir()
    _write_wheel(dist / "autowealth_ai-0.16.0-py3-none-any.whl")

    with pytest.raises(ReleaseMetadataError, match="exactly one sdist; found 0"):
        _verify(root, dist_dir=dist)


def test_dist_with_two_wheels_fails(tmp_path: Path) -> None:
    root = _write_fixture_repository(tmp_path / "repo")
    dist = tmp_path / "dist"
    dist.mkdir()
    _write_wheel(dist / "autowealth_ai-0.16.0-py3-none-any.whl")
    _write_wheel(dist / "autowealth_ai-0.16.0-cp312-cp312-win_amd64.whl")
    _write_sdist(dist / "autowealth_ai-0.16.0.tar.gz")

    with pytest.raises(ReleaseMetadataError, match="exactly one wheel; found 2"):
        _verify(root, dist_dir=dist)


def test_dist_with_two_sdists_fails(tmp_path: Path) -> None:
    root = _write_fixture_repository(tmp_path / "repo")
    dist = tmp_path / "dist"
    dist.mkdir()
    _write_wheel(dist / "autowealth_ai-0.16.0-py3-none-any.whl")
    _write_sdist(dist / "autowealth_ai-0.16.0.tar.gz")
    _write_sdist(dist / "autowealth-ai-0.16.0.tar.gz")

    with pytest.raises(ReleaseMetadataError, match="exactly one sdist; found 2"):
        _verify(root, dist_dir=dist)


def test_dist_with_current_and_old_artifacts_fails(tmp_path: Path) -> None:
    root = _write_fixture_repository(tmp_path / "repo")
    dist = tmp_path / "dist"
    dist.mkdir()
    _write_artifact_pair(dist)
    _write_wheel(
        dist / "autowealth_ai-0.1.0-py3-none-any.whl",
        metadata_version="0.1.0",
    )

    with pytest.raises(ReleaseMetadataError, match="0.1.0"):
        _verify(root, dist_dir=dist)


def test_dist_with_unexpected_file_fails(tmp_path: Path) -> None:
    root = _write_fixture_repository(tmp_path / "repo")
    dist = tmp_path / "dist"
    dist.mkdir()
    _write_artifact_pair(dist)
    (dist / "build.log").write_text("unexpected", encoding="utf-8")

    with pytest.raises(ReleaseMetadataError, match="unexpected dist file: build.log"):
        _verify(root, dist_dir=dist)


def test_dist_rejects_metadata_version_mismatch(tmp_path: Path) -> None:
    root = _write_fixture_repository(tmp_path / "repo")
    dist = tmp_path / "dist"
    dist.mkdir()
    wheel = dist / "autowealth_ai-0.16.0-py3-none-any.whl"
    _write_wheel(wheel, metadata_version="0.15.1")
    _write_sdist(dist / "autowealth_ai-0.16.0.tar.gz")

    with pytest.raises(ReleaseMetadataError, match="metadata has version 0.15.1"):
        _verify(root, dist_dir=dist)


def test_dist_accepts_valid_sha256sums(tmp_path: Path) -> None:
    root = _write_fixture_repository(tmp_path / "repo")
    dist = tmp_path / "dist"
    dist.mkdir()
    artifacts = _write_artifact_pair(dist)
    _write_checksums(dist, artifacts)

    result = _verify(root, dist_dir=dist)

    assert result.artifacts == tuple(path.name for path in artifacts)


def test_dist_rejects_invalid_sha256sums(tmp_path: Path) -> None:
    root = _write_fixture_repository(tmp_path / "repo")
    dist = tmp_path / "dist"
    dist.mkdir()
    artifacts = _write_artifact_pair(dist)
    checksum = _write_checksums(dist, artifacts)
    content = checksum.read_text(encoding="ascii")
    replacement = "0" if content[0] != "0" else "1"
    checksum.write_text(replacement + content[1:], encoding="ascii")

    with pytest.raises(ReleaseMetadataError, match="digest does not match"):
        _verify(root, dist_dir=dist)


def test_verification_does_not_use_network_or_write_repository(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _write_fixture_repository(tmp_path / "repo")
    before = {
        path.relative_to(root): path.read_bytes() for path in root.rglob("*") if path.is_file()
    }

    def reject_network(*args: object, **kwargs: object) -> None:
        raise AssertionError(f"network access attempted: {args!r} {kwargs!r}")

    monkeypatch.setattr(socket, "create_connection", reject_network)
    monkeypatch.setattr(socket, "socket", reject_network)

    _verify(root, expected_version=VERSION, tag="v0.16.0")

    after = {
        path.relative_to(root): path.read_bytes() for path in root.rglob("*") if path.is_file()
    }
    assert after == before


def test_cli_outputs_stable_machine_readable_summary(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = _write_fixture_repository(tmp_path)

    exit_code = main(
        [
            "--project-root",
            str(root),
            "--expected-version",
            VERSION,
            "--tag",
            "v0.16.0",
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output == {
        "artifacts": [],
        "changelog_heading": "## [0.16.0] - 2026-07-29",
        "dist_checked": False,
        "product_version": VERSION,
        "release_date": "2026-07-29",
        "status": "ok",
        "tag": "v0.16.0",
    }


def test_release_notes_output_cannot_modify_repository(tmp_path: Path) -> None:
    root = _write_fixture_repository(tmp_path)

    exit_code = main(
        [
            "--project-root",
            str(root),
            "--output-release-notes",
            str(root / "release-notes.md"),
        ]
    )

    assert exit_code == 1
    assert not (root / "release-notes.md").exists()


def test_release_notes_output_writes_only_explicit_external_path(tmp_path: Path) -> None:
    root = _write_fixture_repository(tmp_path / "repo")
    destination = tmp_path / "release-notes.md"

    exit_code = main(
        [
            "--project-root",
            str(root),
            "--output-release-notes",
            str(destination),
        ]
    )

    assert exit_code == 0
    assert destination.read_text(encoding="utf-8") == extract_release_notes(root, VERSION)
