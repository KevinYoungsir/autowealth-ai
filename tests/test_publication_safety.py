from __future__ import annotations

import re
import subprocess
from pathlib import Path

import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_ROOT = REPOSITORY_ROOT / ".github" / "workflows"
EXTERNAL_WORKFLOWS = (
    "publish-twitter.yml",
    "publish-reddit.yml",
    "publish-devto.yml",
    "community-notify.yml",
)
AUTHORITATIVE_REPOSITORY = "https://github.com/KevinYoungsir/autowealth-ai"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _tracked_text() -> dict[Path, str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
    )
    tracked: dict[Path, str] = {}
    for raw_path in result.stdout.split(b"\0"):
        if not raw_path:
            continue
        path = REPOSITORY_ROOT / raw_path.decode("utf-8")
        try:
            tracked[path] = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
    return tracked


def test_no_automatic_tag_workflow_exists() -> None:
    assert not (WORKFLOW_ROOT / "auto-tag.yml").exists()


def test_external_publication_workflows_are_manual_and_confirmed() -> None:
    for name in EXTERNAL_WORKFLOWS:
        text = _read(WORKFLOW_ROOT / name)
        assert re.search(r"(?m)^on:\n  workflow_dispatch:", text)
        assert not re.search(r"(?m)^  (?:release|watch|schedule):", text)
        assert "release_tag:" in text
        assert "confirmation:" in text
        assert "inputs.confirmation == 'PUBLISH'" in text
        assert "releases/tags/$RELEASE_TAG" in text
        assert ".draft == false" in text
        assert ".prerelease == false" in text


def test_external_workflows_do_not_execute_release_text_as_shell() -> None:
    for name in EXTERNAL_WORKFLOWS:
        text = _read(WORKFLOW_ROOT / name)
        assert not re.search(r"(?m)^\s*(?:source|\.)\s+", text)
        assert not re.search(r"\beval\b", text)
        assert "tag_" + "NAME" not in text
        assert "release_info.env" not in text
        assert "set -euo pipefail" in text
        assert "release.json" in text
        assert "jq " in text


def test_release_workflow_uses_immutable_official_actions() -> None:
    text = _read(WORKFLOW_ROOT / "release.yml")
    uses = re.findall(r"uses:\s*([^@\s]+)@([^\s#]+)(?:\s+#\s+([^\s]+))?", text)

    assert uses
    for action, revision, version_comment in uses:
        assert action.startswith("actions/")
        assert re.fullmatch(r"[0-9a-f]{40}", revision)
        assert re.fullmatch(r"v\d+(?:\.\d+){1,2}", version_comment)


def test_release_workflow_has_minimal_permissions() -> None:
    workflow = yaml.safe_load(_read(WORKFLOW_ROOT / "release.yml"))

    assert workflow["permissions"] == {}
    for job_name, job in workflow["jobs"].items():
        expected = {"contents": "write"} if job_name == "release" else {"contents": "read"}
        assert job["permissions"] == expected
    text = _read(WORKFLOW_ROOT / "release.yml")
    assert "packages: write" not in text
    assert "id-token: write" not in text


def test_release_workflow_enforces_main_head_and_clean_dist() -> None:
    text = _read(WORKFLOW_ROOT / "release.yml")

    assert 'VERIFIED_TAG_REF="refs/release-tags/$TAG"' in text
    assert "refs/tags/$TAG:$VERIFIED_TAG_REF" in text
    assert 'git cat-file -t "$VERIFIED_TAG_REF"' in text
    assert 'git rev-parse "$VERIFIED_TAG_REF^{commit}"' in text
    assert 'git rev-parse "refs/remotes/origin/main^{commit}"' in text
    assert '[[ "$TAG_COMMIT" != "$MAIN_COMMIT" ]]' in text
    assert 'git cat-file -t "$TAG"' not in text
    assert 'git rev-parse "$TAG^{commit}"' not in text
    assert "rm -rf dist" in text
    assert "mkdir -p dist" in text
    assert text.index("rm -rf dist") < text.index("python -m build --outdir dist")


def test_release_workflow_audits_frontend_and_does_not_publish_registries() -> None:
    text = _read(WORKFLOW_ROOT / "release.yml")

    assert 'node-version: "20.9.0"' in text
    assert "npm audit --omit=dev --audit-level=high" in text
    assert "npm audit fix" not in text
    assert "twine upload" not in text
    assert "docker push" not in text


def test_release_workflow_validates_checksums_before_publishing_draft() -> None:
    text = _read(WORKFLOW_ROOT / "release.yml")

    checksum_index = text.index("sha256sum -c SHA256SUMS.txt")
    draft_index = text.index("gh release create")
    upload_index = text.index("gh release upload")
    validate_index = text.index("Verify the draft asset set")
    publish_index = text.index('gh release edit "$TAG" --draft=false')

    assert "SHA256SUMS.txt" in text
    assert "Expected exactly two Python package files" in text
    assert "--draft" in text
    assert "--clobber" in text
    assert ".assets | length == 3" in text
    assert checksum_index < draft_index < upload_index < validate_index < publish_index


def test_tracked_public_text_has_no_stale_repository_or_package_claims() -> None:
    forbidden = (
        "Jsoned" + "/autowealth-ai",
        "github.com/" + "Jsoned",
        "your" + "username",
        "pip install " + "autowealth-ai",
    )

    for path, text in _tracked_text().items():
        for value in forbidden:
            assert value not in text, f"{value!r} remains in {path.relative_to(REPOSITORY_ROOT)}"


def test_public_governance_documents_use_authoritative_repository_links() -> None:
    code_of_conduct = _read(REPOSITORY_ROOT / "CODE_OF_CONDUCT.md")
    contributing = _read(REPOSITORY_ROOT / "CONTRIBUTING.md")
    security = _read(REPOSITORY_ROOT / "SECURITY.md")

    assert f"{AUTHORITATIVE_REPOSITORY}/issues" in code_of_conduct
    assert f"git clone {AUTHORITATIVE_REPOSITORY}.git" in contributing
    assert f"{AUTHORITATIVE_REPOSITORY}/issues" in contributing
    assert f"{AUTHORITATIVE_REPOSITORY}/pulls" in contributing
    assert f"{AUTHORITATIVE_REPOSITORY}/security/advisories/new" in security


def test_public_governance_documents_do_not_expose_local_or_secret_values() -> None:
    secret_patterns = (
        re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
        re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
        re.compile(r"AKIA[0-9A-Z]{16}"),
        re.compile(r"(?i)(?:C:\\Users\\|D:\\Autowealth-ai)"),
        re.compile(r"https://[^\s)]+\.vercel\.app"),
    )

    for name in ("CODE_OF_CONDUCT.md", "CONTRIBUTING.md", "SECURITY.md"):
        text = _read(REPOSITORY_ROOT / name)
        for pattern in secret_patterns:
            assert pattern.search(text) is None, f"{pattern.pattern!r} found in {name}"


def test_release_process_uses_authoritative_release_date() -> None:
    text = _read(REPOSITORY_ROOT / "docs" / "release-process.md")

    assert "## [0.17.0] - 2026-08-10" in text
    assert "2026-07-28" not in text
