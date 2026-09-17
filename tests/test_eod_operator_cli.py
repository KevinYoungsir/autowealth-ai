from __future__ import annotations

from io import StringIO
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

from autowealth.market_data.operation_operator import (
    EODOperationOperatorError,
    EODOperationOperatorErrorCode,
)
from autowealth.market_data.operation_worker import (
    EODOperationWorkerResult,
    EODOperationWorkerStatus,
)
from autowealth.market_data.operator_cli import main
from autowealth.market_data.operations import (
    EODOperationFailurePolicy,
    EODOperationJobStatus,
    EODOperationType,
)
from autowealth.market_data.providers import EODRevisionStrategy

ROOT = Path(__file__).resolve().parents[1]
JOB_ID = "job-20260901T080000000000Z-" + "a" * 32


class FakeOperator:
    def __init__(self) -> None:
        self.calls = []
        self.worker_result = EODOperationWorkerResult(EODOperationWorkerStatus.NO_WORK)
        self.raise_error = None

    def _record(self, name, **kwargs):
        if self.raise_error is not None:
            raise self.raise_error
        self.calls.append((name, kwargs))
        return {"result": name}

    def catalog_inspect(self):
        return self._record("catalog.inspect")

    def jobs_health(self):
        return self._record("jobs.health")

    def jobs_list(self, **kwargs):
        return self._record("jobs.list", **kwargs)

    def jobs_show(self, job_id):
        return self._record("jobs.show", job_id=job_id)

    def jobs_retry(self, job_id, **kwargs):
        return self._record("jobs.retry", job_id=job_id, **kwargs)

    def submit_incremental_single(self, **kwargs):
        return self._record("submit.incremental_single", **kwargs)

    def submit_incremental_batch(self, **kwargs):
        return self._record("submit.incremental_batch", **kwargs)

    def submit_full_refresh(self, **kwargs):
        return self._record("submit.full_refresh", **kwargs)

    def submit_maintenance(self, **kwargs):
        return self._record("submit.maintenance", **kwargs)

    def worker_run_one(self, **kwargs):
        if self.raise_error is not None:
            raise self.raise_error
        self.calls.append(("worker.run_one", kwargs))
        return self.worker_result


def write_manifest(tmp_path: Path) -> Path:
    path = tmp_path / "operator.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "config_schema_version": 1,
                "operations_root": "operations",
                "datasets": [
                    {
                        "production_config": "production.yaml",
                        "storage_identity": "fixture-storage",
                        "enabled": True,
                    }
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return path


def run_cli(tmp_path: Path, fake: FakeOperator, arguments: list[str]):
    output = StringIO()
    config = write_manifest(tmp_path)
    calls = []

    def factory(parsed):
        calls.append(parsed)
        return fake

    exit_code = main(
        ["--config", str(config), *arguments],
        operator_factory=factory,
        stdout=output,
    )
    return exit_code, json.loads(output.getvalue()), calls


@pytest.mark.parametrize(
    "arguments,command",
    [
        (["catalog", "inspect"], "catalog.inspect"),
        (["jobs", "health"], "jobs.health"),
        (["jobs", "list"], "jobs.list"),
        (["jobs", "show", JOB_ID], "jobs.show"),
        (["jobs", "retry", JOB_ID], "jobs.retry"),
        (
            [
                "submit",
                "incremental-single",
                "--storage-identity",
                "fixture-storage",
                "--start-date",
                "2024-01-02",
                "--end-date",
                "2024-01-05",
                "--revision-strategy",
                "append_only",
                "--dry-run",
            ],
            "submit.incremental_single",
        ),
        (
            [
                "submit",
                "incremental-batch",
                "--all-enabled",
                "--start-date",
                "2024-01-02",
                "--end-date",
                "2024-01-05",
                "--revision-strategy",
                "append_only",
                "--dry-run",
            ],
            "submit.incremental_batch",
        ),
        (
            [
                "submit",
                "full-refresh",
                "--storage-identity",
                "fixture-storage",
                "--start-date",
                "2024-01-02",
                "--end-date",
                "2024-01-05",
                "--execute",
            ],
            "submit.full_refresh",
        ),
        (
            [
                "submit",
                "maintenance",
                "--storage-identity",
                "fixture-storage",
                "--dry-run",
            ],
            "submit.maintenance",
        ),
        (
            ["worker", "run-one", "--worker-id", "fixture-worker", "--execute"],
            "worker.run_one",
        ),
    ],
)
def test_all_commands_use_stable_success_envelopes(
    tmp_path: Path,
    arguments: list[str],
    command: str,
) -> None:
    exit_code, payload, calls = run_cli(tmp_path, FakeOperator(), arguments)

    assert exit_code == 0
    assert payload["schema_version"] == 1
    assert payload["command"] == command
    assert payload["ok"] is True
    assert calls
    assert payload == json.loads(
        json.dumps(payload, ensure_ascii=False, allow_nan=False, sort_keys=True)
    )


def test_jobs_list_converts_filters_to_exact_enums(tmp_path: Path) -> None:
    fake = FakeOperator()
    exit_code, _, _ = run_cli(
        tmp_path,
        fake,
        [
            "jobs",
            "list",
            "--limit",
            "25",
            "--status",
            "failed",
            "--operation-type",
            "maintenance",
        ],
    )

    assert exit_code == 0
    _, values = fake.calls[0]
    assert values == {
        "limit": 25,
        "statuses": (EODOperationJobStatus.FAILED,),
        "operation_types": (EODOperationType.MAINTENANCE,),
    }


def test_incremental_arguments_map_to_existing_domain_contracts(tmp_path: Path) -> None:
    fake = FakeOperator()
    exit_code, payload, _ = run_cli(
        tmp_path,
        fake,
        [
            "submit",
            "incremental-single",
            "--storage-identity",
            "fixture-storage",
            "--start-date",
            "2024-01-02",
            "--end-date",
            "2024-01-05",
            "--revision-strategy",
            "overlap_window",
            "--overlap-trading-days",
            "3",
            "--execute",
            "--idempotency-key",
            "plaintext-secret-alias",
        ],
    )

    assert exit_code == 0
    _, values = fake.calls[0]
    assert values["dry_run"] is False
    assert values["execute"] is True
    assert values["requested_range"].to_dict() == {
        "start_date": "2024-01-02",
        "end_date": "2024-01-05",
    }
    assert values["revision_policy"].strategy is EODRevisionStrategy.OVERLAP_WINDOW
    assert values["revision_policy"].overlap_trading_days == 3
    assert "plaintext-secret-alias" not in json.dumps(payload)


def test_batch_selectors_and_failure_policy_are_exact(tmp_path: Path) -> None:
    fake = FakeOperator()
    exit_code, _, _ = run_cli(
        tmp_path,
        fake,
        [
            "submit",
            "incremental-batch",
            "--storage-identity",
            "two",
            "--storage-identity",
            "one",
            "--start-date",
            "2024-01-02",
            "--end-date",
            "2024-01-05",
            "--revision-strategy",
            "append_only",
            "--failure-policy",
            "continue_on_failure",
            "--dry-run",
        ],
    )

    assert exit_code == 0
    _, values = fake.calls[0]
    assert values["storage_identities"] == ("two", "one")
    assert values["all_enabled"] is False
    assert values["failure_policy"] is EODOperationFailurePolicy.CONTINUE_ON_FAILURE


def test_maintenance_negative_switches_are_deterministic(tmp_path: Path) -> None:
    fake = FakeOperator()
    exit_code, _, _ = run_cli(
        tmp_path,
        fake,
        [
            "submit",
            "maintenance",
            "--storage-identity",
            "fixture-storage",
            "--execute",
            "--no-cleanup-staging",
            "--no-cleanup-pointer-temps",
        ],
    )

    assert exit_code == 0
    _, values = fake.calls[0]
    assert values["cleanup_staging"] is False
    assert values["cleanup_pointer_temps"] is False


@pytest.mark.parametrize(
    "arguments",
    [
        [
            "submit",
            "incremental-single",
            "--storage-identity",
            "fixture-storage",
            "--start-date",
            "2024-01-02",
            "--end-date",
            "2024-01-05",
            "--revision-strategy",
            "append_only",
        ],
        [
            "submit",
            "maintenance",
            "--storage-identity",
            "fixture-storage",
            "--dry-run",
            "--execute",
        ],
        ["worker", "run-one", "--worker-id", "worker-without-confirmation"],
        [
            "submit",
            "incremental-batch",
            "--all-enabled",
            "--storage-identity",
            "duplicate-mode",
            "--start-date",
            "2024-01-02",
            "--end-date",
            "2024-01-05",
            "--revision-strategy",
            "append_only",
            "--dry-run",
        ],
    ],
)
def test_argument_rejections_are_safe_and_do_not_construct_operator(
    tmp_path: Path,
    arguments: list[str],
) -> None:
    config = write_manifest(tmp_path)
    output = StringIO()
    calls = []

    exit_code = main(
        ["--config", str(config), *arguments],
        operator_factory=lambda value: calls.append(value),
        stdout=output,
    )
    payload = json.loads(output.getvalue())

    assert exit_code == 2
    assert payload["ok"] is False
    assert payload["error"]["code"] == "invalid_arguments"
    assert calls == []
    assert str(tmp_path.resolve()) not in output.getvalue()


def test_invalid_revision_policy_is_safe_input_error(tmp_path: Path) -> None:
    exit_code, payload, _ = run_cli(
        tmp_path,
        FakeOperator(),
        [
            "submit",
            "incremental-single",
            "--storage-identity",
            "fixture-storage",
            "--start-date",
            "2024-01-02",
            "--end-date",
            "2024-01-05",
            "--revision-strategy",
            "overlap_window",
            "--dry-run",
        ],
    )

    assert exit_code == 2
    assert payload["error"]["code"] == "invalid_input"


def test_retry_confirmation_is_delegated_without_rewriting_request(tmp_path: Path) -> None:
    fake = FakeOperator()
    exit_code, _, _ = run_cli(
        tmp_path,
        fake,
        ["jobs", "retry", JOB_ID, "--execute", "--idempotency-key", "secret-alias"],
    )

    assert exit_code == 0
    assert fake.calls == [
        (
            "jobs.retry",
            {
                "job_id": JOB_ID,
                "execute": True,
                "idempotency_key": "secret-alias",
            },
        )
    ]


@pytest.mark.parametrize(
    "status,expected_exit",
    [
        (EODOperationWorkerStatus.NO_WORK, 0),
        (EODOperationWorkerStatus.JOB_COMPLETED, 0),
        (EODOperationWorkerStatus.JOB_FAILED, 3),
        (EODOperationWorkerStatus.WORKER_UNSAFE, 4),
        (EODOperationWorkerStatus.WORKER_FATAL, 4),
    ],
)
def test_worker_status_exit_code_mapping(
    tmp_path: Path,
    status: EODOperationWorkerStatus,
    expected_exit: int,
) -> None:
    fake = FakeOperator()
    fake.worker_result = EODOperationWorkerResult(status, diagnostic="stable_code")

    exit_code, payload, _ = run_cli(
        tmp_path,
        fake,
        ["worker", "run-one", "--worker-id", "fixture-worker", "--execute"],
    )

    assert exit_code == expected_exit
    assert payload["ok"] is True
    assert payload["data"]["status"] == status.value
    assert payload["data"]["diagnostic"] == "stable_code"
    assert fake.calls == [("worker.run_one", {"worker_id": "fixture-worker", "execute": True})]


def test_domain_and_unexpected_errors_never_expose_raw_details(tmp_path: Path) -> None:
    fake = FakeOperator()
    fake.raise_error = EODOperationOperatorError(EODOperationOperatorErrorCode.JOB_NOT_FOUND)
    exit_code, payload, _ = run_cli(tmp_path, fake, ["jobs", "show", JOB_ID])
    assert exit_code == 3
    assert payload["error"]["code"] == "job_not_found"

    fake.raise_error = RuntimeError("apiKey=secret C:\\private\\provider-response.json")
    exit_code, payload, _ = run_cli(tmp_path, fake, ["jobs", "health"])
    serialized = json.dumps(payload)
    assert exit_code == 4
    assert payload["error"]["code"] == "internal_error"
    assert "secret" not in serialized
    assert "private" not in serialized
    assert "traceback" not in serialized.lower()


def test_missing_config_error_does_not_echo_sensitive_path(tmp_path: Path) -> None:
    missing = tmp_path / "apiKey=secret.yaml"
    output = StringIO()

    exit_code = main(
        ["--config", str(missing), "jobs", "health"],
        stdout=output,
    )

    assert exit_code == 2
    assert "secret" not in output.getvalue()
    assert str(tmp_path.resolve()) not in output.getvalue()


def test_help_and_import_are_offline_and_side_effect_free(tmp_path: Path) -> None:
    script = """
import runpy
import sys
from pathlib import Path

root = Path.cwd()
before = tuple(root.rglob("*"))

def audit(event, args):
    del args
    if event in {"socket.bind", "socket.connect", "socket.getaddrinfo"}:
        raise AssertionError("operator import/help must not access network")

sys.addaudithook(audit)
sys.argv = ["operator_cli", "--help"]
try:
    runpy.run_module("autowealth.market_data.operator_cli", run_name="__main__")
except SystemExit as error:
    if error.code != 0:
        raise
after = tuple(root.rglob("*"))
assert before == after
"""
    environment = {"PYTHONPATH": str(ROOT), "PYTHONIOENCODING": "utf-8"}
    for name in ("SystemRoot", "WINDIR"):
        if name in os.environ:
            environment[name] = os.environ[name]

    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "catalog" in completed.stdout
    assert tuple(tmp_path.rglob("*")) == ()
