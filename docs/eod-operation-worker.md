# Durable EOD Operation Worker

## Decision

AutoWealth PR4B adds a deterministic in-memory runtime catalog and an explicit synchronous
worker for the durable EOD jobs introduced by PR4A. The worker executes only previously
submitted operation intent. It does not discover datasets, schedule daily runs, expose an API
or CLI, place trades, call DeepSeek, or create jobs during import or construction.

## Catalog contract

`EODOperationCatalog` contains at most 256 exact `EODOperationCatalogEntry` values. Entries are
sorted by canonical dataset identity. Duplicate datasets, duplicate storage identities, mixed
enabled-calendar identities, an empty catalog, and a catalog with no enabled dataset when an
execution context is requested fail closed.

Each entry binds:

- one exact `EODDatasetKey`;
- an exact enabled boolean;
- a safe, path-independent storage identity;
- one matching validated `EODRuntimeStack`.

The catalog fingerprint is `sha256:<64 lowercase hex>` over canonical JSON. It includes the
catalog and runtime contract versions, the complete local calendar identity, sorted dataset
identities, enabled states, storage identities, production config schema version, ordered
Provider names and versions, retry policy, and rate-limit policy. It excludes repository and
calendar paths, endpoint names, file timestamps, host names, process IDs, and credentials.

`build_eod_operation_catalog` explicitly reads and validates the caller's local calendar
artifacts through existing composition. Importing or constructing catalog values does not read
files, call Providers, create repositories, or access the network.

## Worker lifecycle

`EODOperationWorker.run_one()` performs these bounded steps:

1. Inspect the durable operation repository.
2. Recover at most 256 expired running jobs using the actual injected UTC clock.
3. Claim the oldest queued job with the configured initial lease.
4. Start one heartbeat for the claimed lease.
5. Validate every dataset and the exact catalog execution context.
6. Execute one incremental-single, incremental-batch, full-refresh, or maintenance operation.
7. Stop the heartbeat and perform a final lease renewal.
8. Check ownership immediately before the durable terminal transition.
9. Complete or fail the job with a bounded deterministic summary.

An absent repository returns `no_work`. Invalid health, failed recovery, or failed claim returns
`worker_fatal`. Lease ownership uncertainty returns `worker_unsafe` and stops `run_forever`.
The worker never converts an unsafe lease into a successful or failed durable job result.

Default timing is:

| Setting | Default | Allowed range |
| --- | ---: | ---: |
| Initial lease | 300 seconds | 30-3600 |
| Heartbeat interval | 60 seconds | 30-3600 |
| Idle poll interval | 5 seconds | 1-3600 |

The lease duration must be at least three heartbeat intervals. The heartbeat extends the
repository lease using the configured heartbeat interval and trusts only the repository-returned
expiry after strict job, worker, claim-version, and monotonic-expiry validation.

## Execution identity

The operation request execution context must exactly equal the current catalog context. Unknown
datasets, disabled datasets, or a context mismatch fail closed before Provider execution.

For every non-maintenance dataset, the worker derives:

```text
generation_id = job_id + "-" + sha256(canonical dataset.to_dict())
created_at = job.started_at
```

Incremental single jobs are executed as one-item batches. Batch order remains canonical, and
the request's stop/continue failure policy is preserved. Full refresh remains explicit and
eligible only under the existing planner. Maintenance preserves dry-run defaults and exact
cleanup switches.

All writer paths receive the same `InProcessEODDatasetLockManager`. Operation SQLite storage and
generation repository roots must be separate and non-nested.

## Cooperative checkpoints

The worker's lease controller is passed through existing execution boundaries. It checks
ownership at these stages:

- before every Provider invocation, including retries and fallback;
- after every Provider invocation;
- after the Provider stage;
- before immutable generation publication;
- before the next batch dataset;
- before every actual maintenance deletion;
- before the final job transition.

Control errors propagate unchanged to the worker. The optional checkpoint defaults to `None`,
so direct legacy calls preserve their prior behavior.

Checkpoints are cooperative and local. They prevent a new controlled side effect after the
worker becomes unsafe. They cannot cancel a Provider already executing, undo a file already
deleted, or roll back an immutable generation already published. They are not distributed
fencing.

## Result mapping

The durable result summary preserves the existing domain status instead of claiming broader
success:

- incremental: `success`, `dry_run`, `partial_success`, or `full_refresh_required`;
- full refresh: `success`, `dry_run`, or `full_refresh_not_eligible`;
- maintenance: `maintenance_empty`, `maintenance_inspected`, `maintenance_cleaned`, or
  `maintenance_blocked`.

Unexpected execution exceptions become stable operation-specific failures without storing the
raw exception. Result-mapping failure has its own code. No traceback, credential, local path, or
raw Provider response is added to the job record.

## Crash consistency and retry

Generation publication and operation-job completion are separate durable transactions. If a
process exits after publication but before completion, the immutable generation remains
available while the job remains `running`. Once its lease expires, a later worker invocation
marks it `abandoned`. The worker does not roll back the generation or silently rerun the job.

A retry is always an explicit new job linked to a failed or abandoned predecessor. PR4B has no
whole-job automatic retry and does not alter Provider retry or fallback semantics.

## Deployment and limitations

The built-in worker supports one intentional writer process on one host with durable local
storage. `InProcessEODDatasetLockManager` is not a cross-process or multi-host lock, and the
SQLite lease is not a fencing token. Do not run competing worker processes against the same
generation repositories.

PR4B does not include scheduler integration, service supervision, CLI/API submission, monitoring,
automatic retention, automatic daily ingestion, PostgreSQL migration, distributed locks, or
multi-host failover. Ephemeral Vercel or container filesystems remain unsuitable for the job or
generation repositories.

Rolling back PR4B leaves operation schema v1 and generation artifacts unchanged. Older code will
not execute the worker modules but can continue to read the existing supported data formats.
No historical research artifact, metric, curve, cache schema, or trading behavior is modified.

This is research data operations infrastructure only. It does not constitute investment advice
and contains no real-trading capability.
