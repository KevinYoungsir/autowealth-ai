# EOD Operator CLI

PR4C adds an explicit command-line administration boundary for the durable EOD operation
contracts. It is research-data infrastructure only: it does not schedule daily ingestion,
execute trades, call DeepSeek, or expose an API.

## Operator manifest

Invoke the CLI with an explicit schema-versioned manifest:

~~~powershell
python -m autowealth.market_data.operator_cli --config configs/eod_operator.yaml jobs health
~~~

Schema version 1 contains exactly:

~~~yaml
config_schema_version: 1
operations_root: ../var/eod-operations
datasets:
  - production_config: ./eod_equity_600000.yaml
    storage_identity: cn-sse-equity-600000-qfq
    enabled: true
~~~

Relative paths resolve from the manifest directory. Explicit local absolute paths are accepted.
URLs, URIs, environment-variable expansion, automatic directory discovery, home-directory
fallback, and CWD-dependent fallback are rejected. Loading the operator manifest does not load
production YAML, calendars, Providers, repositories, or workers.

The operations_root stores the durable SQLite job database. Every generation repository_root
comes from its existing production config. The operator validates that these roots are different
and non-nested before catalog-dependent commands. Both locations require trusted, durable storage.

## Commands

The exact command surface is:

~~~text
catalog inspect
jobs health
jobs list
jobs show
jobs retry
submit incremental-single
submit incremental-batch
submit full-refresh
submit maintenance
worker run-one
~~~

There is no run-forever, scheduler, automatic startup, service manager, API, or automatic daily
ingestion command.

Catalog inspect loads the explicitly listed production configurations and returns canonical
dataset, storage identity, enabled state, Provider name/version, calendar identity, and execution
fingerprint. It does not fetch market data or expose filesystem paths.

Jobs health, list, and show read only the durable operation repository. They do not require
production configs or calendars and do not create an absent database or root. List filters accept
only existing operation/status enums and a limit from 1 through 256.

## Submission and execution confirmation

Each submit command requires exactly one of --dry-run or --execute. Submission always creates or
reuses a durable job; dry-run means the later worker execution must not perform real Provider or
publication side effects.

Range-based commands require canonical YYYY-MM-DD start and end dates. Incremental commands also
require an existing revision strategy. overlap_window requires a positive overlap; other
strategies require zero overlap. Full refresh always uses full_refresh_required internally and
cannot be overridden.

Batch submission accepts repeated --storage-identity values or --all-enabled, never both.
Duplicate, unknown, or disabled selectors fail closed. The failure policy is stop_on_failure by
default or explicitly continue_on_failure.

Maintenance keeps both existing cleanup switches enabled unless --no-cleanup-staging or
--no-cleanup-pointer-temps is supplied. It cannot delete complete generations, manifests, or
current pointers.

An optional idempotency key is input only. Plaintext is never returned in JSON or persisted by
the repository.

## Retry and run-one

Jobs retry accepts only failed or abandoned predecessors. It submits a new job linked by
retry_of_job_id and reuses the exact original request and fingerprint. It cannot change the
operation, dataset, range, revision policy, dry-run flag, failure policy, maintenance flags, or
execution context. A stale context fails closed. Retrying a real request requires --execute; a
dry-run predecessor cannot become real.

Worker run-one --worker-id <id> --execute constructs the existing synchronous worker and calls
run_one() exactly once. Without explicit confirmation it does not inspect, recover, claim, or
execute work. It never drains the queue or starts a loop.

## JSON and exit codes

Success:

~~~json
{"command":"jobs.health","data":{},"ok":true,"schema_version":1}
~~~

Failure:

~~~json
{"command":"jobs.health","error":{"code":"internal_error","message":"The EOD operator command failed safely."},"ok":false,"schema_version":1}
~~~

Output uses deterministic key ordering, UTF-8 JSON, and rejects non-finite numbers. It never uses
default=str, raw exceptions, tracebacks, credentials, filesystem paths, or Provider payloads.

Exit codes:

- 0: successful read/submission, no work, or completed job;
- 2: argument, config, or input validation error;
- 3: safe domain/repository rejection or worker job failure;
- 4: unsafe/fatal worker state or unexpected internal failure.

## Deployment limits and rollback

The built-in repository, lock, and CLI are same-host/single-writer tools. They are unsuitable for
ephemeral filesystems or competing worker processes. Operators must supply persistent storage,
explicit configuration, process supervision, and any scheduling outside AutoWealth.

Rolling back PR4C removes the CLI capability but does not rewrite operation schema v1, the SQLite
store, generations, caches, research artifacts, metrics, or historical runs. Existing data
remains readable by the PR4A/PR4B contracts.

All commands are research operations only and do not constitute investment advice.
