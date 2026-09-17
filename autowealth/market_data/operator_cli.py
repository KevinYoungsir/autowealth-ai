"""Safe JSON CLI for explicit EOD operation administration."""

from __future__ import annotations

import argparse
from datetime import date
import json
import importlib
import sys
from typing import Callable, Optional, Sequence, TextIO

Path = importlib.import_module("pathlib").Path

from .job_repository import EODOperationJobRepositoryError
from .operation_operator import (
    EODOperationOperator,
    EODOperationOperatorError,
    EODOperationOperatorErrorCode,
)
from .operation_worker import EODOperationWorkerResult, EODOperationWorkerStatus
from .operations import (
    EODOperationFailurePolicy,
    EODOperationJobStatus,
    EODOperationType,
)
from .operator_config import EODOperatorConfigError, load_eod_operator_config
from .planning import EODRevisionPolicy
from .providers import EODRevisionStrategy
from .schemas import EODDateRange

EOD_OPERATOR_OUTPUT_SCHEMA_VERSION = 1

_COMMANDS = frozenset(
    {
        "catalog.inspect",
        "jobs.health",
        "jobs.list",
        "jobs.show",
        "jobs.retry",
        "submit.incremental_single",
        "submit.incremental_batch",
        "submit.full_refresh",
        "submit.maintenance",
        "worker.run_one",
    }
)

_INPUT_ERROR_CODES = frozenset(
    {
        EODOperationOperatorErrorCode.INVALID_INPUT,
        EODOperationOperatorErrorCode.DUPLICATE_SELECTOR,
        EODOperationOperatorErrorCode.EXECUTE_CONFIRMATION_REQUIRED,
    }
)


class _ArgumentError(ValueError):
    pass


class _SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        del message
        raise _ArgumentError("The EOD operator arguments are invalid.")


def _build_parser() -> argparse.ArgumentParser:
    parser = _SafeArgumentParser(prog="python -m autowealth.market_data.operator_cli")
    parser.add_argument("--config", required=True, help="Path to the EOD operator manifest.")
    commands = parser.add_subparsers(dest="group", required=True)

    catalog = commands.add_parser("catalog")
    catalog_commands = catalog.add_subparsers(dest="catalog_command", required=True)
    catalog_commands.add_parser("inspect").set_defaults(command_value="catalog.inspect")

    jobs = commands.add_parser("jobs")
    job_commands = jobs.add_subparsers(dest="jobs_command", required=True)
    job_commands.add_parser("health").set_defaults(command_value="jobs.health")
    listing = job_commands.add_parser("list")
    listing.add_argument("--limit", type=_list_limit, default=50)
    listing.add_argument(
        "--status",
        action="append",
        choices=tuple(item.value for item in EODOperationJobStatus),
    )
    listing.add_argument(
        "--operation-type",
        action="append",
        choices=tuple(item.value for item in EODOperationType),
    )
    listing.set_defaults(command_value="jobs.list")
    show = job_commands.add_parser("show")
    show.add_argument("job_id")
    show.set_defaults(command_value="jobs.show")
    retry = job_commands.add_parser("retry")
    retry.add_argument("job_id")
    retry.add_argument("--execute", action="store_true")
    retry.add_argument("--idempotency-key")
    retry.set_defaults(command_value="jobs.retry")

    submit = commands.add_parser("submit")
    submit_commands = submit.add_subparsers(dest="submit_command", required=True)

    single = submit_commands.add_parser("incremental-single")
    _single_selector(single)
    _range_arguments(single)
    _revision_arguments(single)
    _execution_arguments(single)
    single.add_argument("--idempotency-key")
    single.set_defaults(command_value="submit.incremental_single")

    batch = submit_commands.add_parser("incremental-batch")
    selectors = batch.add_mutually_exclusive_group(required=True)
    selectors.add_argument("--storage-identity", action="append", default=[])
    selectors.add_argument("--all-enabled", action="store_true")
    _range_arguments(batch)
    _revision_arguments(batch)
    batch.add_argument(
        "--failure-policy",
        choices=tuple(item.value for item in EODOperationFailurePolicy),
        default=EODOperationFailurePolicy.STOP_ON_FAILURE.value,
    )
    _execution_arguments(batch)
    batch.add_argument("--idempotency-key")
    batch.set_defaults(command_value="submit.incremental_batch")

    refresh = submit_commands.add_parser("full-refresh")
    _single_selector(refresh)
    _range_arguments(refresh)
    _execution_arguments(refresh)
    refresh.add_argument("--idempotency-key")
    refresh.set_defaults(command_value="submit.full_refresh")

    maintenance = submit_commands.add_parser("maintenance")
    _single_selector(maintenance)
    _execution_arguments(maintenance)
    maintenance.add_argument("--no-cleanup-staging", action="store_true")
    maintenance.add_argument("--no-cleanup-pointer-temps", action="store_true")
    maintenance.add_argument("--idempotency-key")
    maintenance.set_defaults(command_value="submit.maintenance")

    worker = commands.add_parser("worker")
    worker_commands = worker.add_subparsers(dest="worker_command", required=True)
    run_one = worker_commands.add_parser("run-one")
    run_one.add_argument("--worker-id", required=True)
    run_one.add_argument("--execute", action="store_true", required=True)
    run_one.set_defaults(command_value="worker.run_one")
    return parser


def _single_selector(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--storage-identity", required=True)


def _range_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--start-date", required=True, type=_iso_date)
    parser.add_argument("--end-date", required=True, type=_iso_date)


def _revision_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--revision-strategy",
        required=True,
        choices=tuple(item.value for item in EODRevisionStrategy),
    )
    parser.add_argument("--overlap-trading-days", type=_non_negative_integer, default=0)


def _execution_arguments(parser: argparse.ArgumentParser) -> None:
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--execute", action="store_true")


def _iso_date(value: str) -> date:
    try:
        parsed = date.fromisoformat(value)
    except (TypeError, ValueError):
        raise argparse.ArgumentTypeError("date must be canonical ISO text") from None
    if parsed.isoformat() != value:
        raise argparse.ArgumentTypeError("date must be canonical ISO text")
    return parsed


def _list_limit(value: str) -> int:
    parsed = _integer(value)
    if not 1 <= parsed <= 256:
        raise argparse.ArgumentTypeError("limit must be between 1 and 256")
    return parsed


def _non_negative_integer(value: str) -> int:
    parsed = _integer(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("value must be non-negative")
    return parsed


def _integer(value: str) -> int:
    try:
        parsed = int(value, 10)
    except (TypeError, ValueError):
        raise argparse.ArgumentTypeError("value must be an integer") from None
    if str(parsed) != value:
        raise argparse.ArgumentTypeError("value must use canonical integer text")
    return parsed


def _command_hint(arguments: Sequence[str]) -> str:
    tokens = tuple(arguments)
    pairs = {
        ("catalog", "inspect"): "catalog.inspect",
        ("jobs", "health"): "jobs.health",
        ("jobs", "list"): "jobs.list",
        ("jobs", "show"): "jobs.show",
        ("jobs", "retry"): "jobs.retry",
        ("submit", "incremental-single"): "submit.incremental_single",
        ("submit", "incremental-batch"): "submit.incremental_batch",
        ("submit", "full-refresh"): "submit.full_refresh",
        ("submit", "maintenance"): "submit.maintenance",
        ("worker", "run-one"): "worker.run_one",
    }
    for index, token in enumerate(tokens[:-1]):
        command = pairs.get((token, tokens[index + 1]))
        if command is not None:
            return command
    return "operator"


def _revision_policy(arguments: argparse.Namespace) -> EODRevisionPolicy:
    return EODRevisionPolicy(
        strategy=EODRevisionStrategy(arguments.revision_strategy),
        overlap_trading_days=arguments.overlap_trading_days,
    )


def _requested_range(arguments: argparse.Namespace) -> EODDateRange:
    return EODDateRange(arguments.start_date, arguments.end_date)


def _dispatch(
    operator: EODOperationOperator,
    arguments: argparse.Namespace,
) -> tuple[dict[str, object], int]:
    command = arguments.command_value
    if command == "catalog.inspect":
        return operator.catalog_inspect(), 0
    if command == "jobs.health":
        return operator.jobs_health(), 0
    if command == "jobs.list":
        statuses = (
            None
            if arguments.status is None
            else tuple(EODOperationJobStatus(value) for value in arguments.status)
        )
        operation_types = (
            None
            if arguments.operation_type is None
            else tuple(EODOperationType(value) for value in arguments.operation_type)
        )
        return (
            operator.jobs_list(
                limit=arguments.limit,
                statuses=statuses,
                operation_types=operation_types,
            ),
            0,
        )
    if command == "jobs.show":
        return operator.jobs_show(arguments.job_id), 0
    if command == "jobs.retry":
        return (
            operator.jobs_retry(
                arguments.job_id,
                execute=arguments.execute,
                idempotency_key=arguments.idempotency_key,
            ),
            0,
        )
    if command == "submit.incremental_single":
        return (
            operator.submit_incremental_single(
                storage_identity=arguments.storage_identity,
                requested_range=_requested_range(arguments),
                revision_policy=_revision_policy(arguments),
                dry_run=arguments.dry_run,
                execute=arguments.execute,
                idempotency_key=arguments.idempotency_key,
            ),
            0,
        )
    if command == "submit.incremental_batch":
        return (
            operator.submit_incremental_batch(
                storage_identities=tuple(arguments.storage_identity),
                all_enabled=arguments.all_enabled,
                requested_range=_requested_range(arguments),
                revision_policy=_revision_policy(arguments),
                failure_policy=EODOperationFailurePolicy(arguments.failure_policy),
                dry_run=arguments.dry_run,
                execute=arguments.execute,
                idempotency_key=arguments.idempotency_key,
            ),
            0,
        )
    if command == "submit.full_refresh":
        return (
            operator.submit_full_refresh(
                storage_identity=arguments.storage_identity,
                requested_range=_requested_range(arguments),
                dry_run=arguments.dry_run,
                execute=arguments.execute,
                idempotency_key=arguments.idempotency_key,
            ),
            0,
        )
    if command == "submit.maintenance":
        return (
            operator.submit_maintenance(
                storage_identity=arguments.storage_identity,
                dry_run=arguments.dry_run,
                execute=arguments.execute,
                cleanup_staging=not arguments.no_cleanup_staging,
                cleanup_pointer_temps=not arguments.no_cleanup_pointer_temps,
                idempotency_key=arguments.idempotency_key,
            ),
            0,
        )
    if command == "worker.run_one":
        result = operator.worker_run_one(
            worker_id=arguments.worker_id,
            execute=arguments.execute,
        )
        return _worker_data(result), _worker_exit_code(result.status)
    raise _ArgumentError("The EOD operator command is invalid.")


def _worker_data(result: EODOperationWorkerResult) -> dict[str, object]:
    return {
        "status": result.status.value,
        "job_id": result.job_id,
        "diagnostic": result.diagnostic,
    }


def _worker_exit_code(status: EODOperationWorkerStatus) -> int:
    if status in (
        EODOperationWorkerStatus.NO_WORK,
        EODOperationWorkerStatus.JOB_COMPLETED,
    ):
        return 0
    if status is EODOperationWorkerStatus.JOB_FAILED:
        return 3
    return 4


def _success(command: str, data: dict[str, object]) -> dict[str, object]:
    if command not in _COMMANDS:
        raise ValueError("command is not a stable operator command")
    return {
        "schema_version": EOD_OPERATOR_OUTPUT_SCHEMA_VERSION,
        "command": command,
        "ok": True,
        "data": data,
    }


def _failure(command: str, code: str, message: str) -> dict[str, object]:
    return {
        "schema_version": EOD_OPERATOR_OUTPUT_SCHEMA_VERSION,
        "command": command,
        "ok": False,
        "error": {"code": code, "message": message},
    }


def _emit(stream: TextIO, payload: dict[str, object]) -> None:
    stream.write(
        json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    )


def main(
    argv: Optional[Sequence[str]] = None,
    *,
    operator_factory: Callable[..., EODOperationOperator] = EODOperationOperator,
    stdout: Optional[TextIO] = None,
) -> int:
    arguments = tuple(sys.argv[1:] if argv is None else argv)
    output = sys.stdout if stdout is None else stdout
    parser = _build_parser()
    try:
        parsed = parser.parse_args(arguments)
    except _ArgumentError:
        _emit(
            output,
            _failure(
                _command_hint(arguments),
                "invalid_arguments",
                "The EOD operator arguments are invalid.",
            ),
        )
        return 2
    except SystemExit as error:
        return int(error.code)

    command = parsed.command_value
    try:
        config = load_eod_operator_config(Path(parsed.config))
        operator = operator_factory(config)
        data, exit_code = _dispatch(operator, parsed)
        _emit(output, _success(command, data))
        return exit_code
    except EODOperatorConfigError as error:
        _emit(output, _failure(command, error.code.value, error.message))
        return 2
    except EODOperationOperatorError as error:
        _emit(output, _failure(command, error.code.value, error.message))
        return 2 if error.code in _INPUT_ERROR_CODES else 3
    except EODOperationJobRepositoryError as error:
        _emit(output, _failure(command, error.code.value, error.message))
        return 3
    except (_ArgumentError, TypeError, ValueError):
        _emit(
            output,
            _failure(command, "invalid_input", "The EOD operator input is invalid."),
        )
        return 2
    except Exception:
        _emit(
            output,
            _failure(command, "internal_error", "The EOD operator command failed safely."),
        )
        return 4


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["EOD_OPERATOR_OUTPUT_SCHEMA_VERSION", "main"]
