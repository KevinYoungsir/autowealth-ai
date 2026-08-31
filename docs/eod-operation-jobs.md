# Durable EOD Operation Jobs

## Decision

AutoWealth uses versioned operation requests, an immutable job model, and the
`EODOperationJobRepository` Protocol to persist EOD operation submissions, claims, leases,
and terminal outcomes. PR4A provides `LocalEODOperationJobRepository` as a same-host SQLite
implementation; it does not execute Providers, Coordinators, full refresh, or maintenance.

This foundation stores operation intent and bounded summaries only. It is not a worker,
scheduler, CLI, API, or daily ingestion service. Importing the modules and reading the
repository do not access the network, create directories, or execute EOD operations.

## Operation Contract

Operation request schema version 1 supports exactly four operation types:

| Operation type | Payload |
| --- | --- |
| `incremental_single` | One dataset, request date range, revision policy, and `dry_run` |
| `incremental_batch` | Up to 256 canonical datasets, request date range, revision policy, `dry_run`, and failure policy |
| `full_refresh` | One dataset, request date range, revision policy, and `dry_run` |
| `maintenance` | One dataset, `dry_run`, and staging/pointer-temp cleanup switches |

Boolean fields must be exact `bool` values; `0` and `1` are rejected. Batch datasets are
sorted by `EODDatasetKey.identity`, and duplicate identities fail validation. Input order
therefore does not change the logical request. Requests do not accept generation IDs,
publication attempt IDs, or other execution-result fields.

Maintenance defaults to `dry_run=true`. Constructing a request never cleans a repository.

## Execution Context and Fingerprint

`EODOperationExecutionContext` is an immutable, path-independent caller-supplied identity:

- `calendar_identity` identifies a validated trading calendar;
- `execution_config_fingerprint` is an opaque stable identity formatted as
  `sha256:<64 lowercase hex>`.

PR4A does not read YAML, calendar files, environment variables, or file timestamps and does
not define a production configuration hashing strategy. A later composition layer is
responsible for deriving these values from a validated runtime or catalog.

Requests use canonical JSON with `allow_nan=False`, sorted keys, and compact separators.
The operation fingerprint is SHA-256 over the canonical request JSON UTF-8 bytes. It includes
operation type, typed payload, and execution context, but excludes job ID, idempotency key,
retry link, timestamps, worker, lease, status, result, and failure.

## Job Identity and Lifecycle

Each newly created submission is one immutable job. Job IDs use this format:

```text
job-YYYYMMDDTHHMMSSffffffZ-<32 lowercase hex>
```

Timestamps are timezone-aware UTC and serialize as ISO-8601 with `+00:00`. The exact lifecycle
is:

```text
queued -> running -> completed
                  -> failed
                  -> abandoned
```

- `queued` has no started/finished time, worker, lease, result, or failure;
- `running` requires started time, worker, claim version, and a valid lease;
- `completed` requires finished time and a result, with no failure;
- `failed` requires finished time and a failure, with no result;
- `abandoned` is produced only by explicit expired-lease recovery and has a stable failure;
- terminal jobs cannot transition again.

A retry always creates a new job and uses `retry_of_job_id` to reference a fingerprint-matched
`failed` or `abandoned` job. Completed, queued, running, missing, or fingerprint-mismatched
targets are rejected.

## Idempotency

Callers may supply a 1-128 character safe-ASCII idempotency key. Plaintext keys are not stored.
The binding table stores a domain-separated SHA-256, job ID, operation fingerprint, and retry
intent. A job may have at most 32 aliases.

Submission follows this truth table:

- same key, request, and retry intent returns the original canonical job;
- one key with a different fingerprint or retry intent returns a conflict;
- no key with an active matching fingerprint returns the existing active job;
- a new key with an active matching fingerprint binds to that active job;
- a terminal fingerprint permits a new job unless an old key is replayed;
- an old key replay after terminal state still returns its original job.

A SQLite partial unique index ensures that at most one `queued` or `running` job exists for an
operation fingerprint. Python pre-checks do not replace the database constraint; a concurrent
constraint race re-reads and returns the matching active job.

## SQLite Persistence

The local implementation has one fixed layout:

```text
operations_root/
└── eod_operation_jobs.sqlite3
```

Persistence schema version 1 contains only:

- `metadata`: internal schema version;
- `jobs`: canonical request, lifecycle, lease, summaries, and logical-record SHA;
- `idempotency_bindings`: hashed idempotency aliases.

Mutation connections enable foreign keys, rollback journal mode, `synchronous=FULL`, and a
finite 5000 ms busy timeout. Submission, claim, and state changes use `BEGIN IMMEDIATE` and one
transaction. Busy/locked errors become stable `persistence_busy` errors after the timeout;
there is no sleep loop or unbounded retry.

Only the first `submit` may safely create the root, database, and schema. The constructor,
`get`, `list_recent`, and `inspect_health` create nothing; reads use SQLite `mode=ro`. Other
mutations fail closed when the store is absent instead of silently initializing an empty store.

## Claim, Lease, and Abandonment

`claim_next` atomically selects a queued job by `created_at ASC, job_id ASC`, then assigns the
worker, initial `claim_version=1`, and a 30-3600 second lease.

`renew_lease`, `complete`, and `fail` require the running job's worker and claim version and an
unexpired lease. Renewal must strictly extend the lease and cannot revive an expired claim.

`mark_expired_running_abandoned` is an explicit recovery primitive with a maximum limit of 256.
It only changes running jobs whose `lease_expires_at <= now`. Import, construction, reads,
submission, and startup do not trigger abandonment.

## Integrity and Safety

Each job row stores `record_sha256`, calculated from the canonical logical public record only.
It excludes SQLite row IDs, page state, journals, file timestamps, and connection metadata.
State fields and the checksum update in the same transaction.

Reads reconstruct and validate request JSON, fingerprint, enums, UTC timestamps, lifecycle,
retry reference, and logical-record checksum. Unknown schema, malformed JSON, invalid state,
bad fingerprint/checksum, or broken retry links fail closed. If a selected list row is corrupt,
the entire list operation fails instead of returning a partial trusted result.

Every recognized schema v1 open compares the required tables, column type/null/default/primary-key
contract, foreign keys, critical index attributes and columns, and normalized canonical object SQL
against the same schema initializer used for a fresh store. A physical mismatch is
corrupt_record; an unknown version remains unsupported_schema. Validation is read-only:
existing stores are never auto-repaired or migrated, and manual migration is unsupported in PR4A.

The root, database, and existing rollback-journal paths are checked for symlinks and unsafe file
types. The application never deletes, renames, or cleans SQLite journals itself. Errors and
failure summaries do not persist tracebacks, raw Provider/SQLite exceptions, credentials, or
absolute paths.

## Public Bounds

Public requests, jobs, result summaries, and failure summaries have fixed budgets:

- dataset/result items and warnings: at most 256;
- messages and metadata strings: at most 512 characters;
- worker ID: at most 64 characters;
- metadata: depth 3, with at most 32 dict/list items at each level;
- metadata JSON: at most 16 KiB;
- logical record: at most 256 KiB;
- list limit: default 50, maximum 256.

Metadata accepts controlled JSON containers and scalars. It rejects non-finite numbers,
bool-as-int values, custom mappings/sequences, cycles, and excess depth.

## Health and Repository Boundary

`inspect_health` is read-only:

- `absent`: the root or database does not exist;
- `healthy`: schema version is recognized and SQLite quick check succeeds;
- `invalid`: schema, integrity, or path safety is invalid.

The Repository Protocol exposes only submit, get, list, claim, renew, complete, fail, explicit
abandonment, and health. It does not expose SQL, connections, delete, prune, vacuum, or repair.

The SQLite implementation supports a durable filesystem on one host only. It does not
coordinate multiple hosts, container replicas, or ephemeral filesystems. A future PostgreSQL
implementation may satisfy the same Protocol, but it is outside PR4A and no migration is added.

The operation-job database must reside on a trusted, service-owned local filesystem. PR4A does
not defend against a hostile local process replacing, rewriting, or mutating that same SQLite
database file or schema. Multi-host and hostile shared filesystems are unsupported.

## PR4B Worker Integration

PR4B adds an explicit synchronous worker and an in-memory operation catalog without changing
operation schema version 1 or the SQLite persistence schema. The worker is constructed with a
durable job repository, an exact catalog, one shared `InProcessEODDatasetLockManager`, a worker
identity, and an explicit absolute operation root. Construction does not inspect the database,
claim work, create files, load Providers, or access the network.

Before every claim attempt, `run_one` checks repository health and calls bounded expired-lease
recovery with the actual worker clock and `limit=256`. It then claims the oldest queued job
using the repository's `created_at, job_id` ordering. Unknown or disabled datasets and execution
contexts that do not exactly match the current catalog fail closed as terminal job failures;
they do not execute a Provider or publication.

The worker starts a daemon heartbeat after claim and stops it before the final lease renewal and
terminal transition. The default initial lease is 300 seconds, the heartbeat interval is 60
seconds, and the idle poll interval is 5 seconds. These values are strictly bounded. Lease loss,
renewal persistence errors, heartbeat startup/shutdown failure, or an unsafe checkpoint stop the
worker without writing a potentially stale terminal result.

Generation identity is deterministic for a claimed job and dataset:

```text
<job_id>-sha256(canonical EODDatasetKey.to_dict())
```

Publication `created_at` is the durable job's `started_at`. Incremental single and batch jobs
reuse `EODBatchCoordinator`; full refresh and maintenance use their explicit executors. All
writers receive the same in-process dataset lock manager.

Cooperative checkpoints run before Provider invocations, after Provider invocations, after the
Provider stage, before publication, before the next batch dataset, before each maintenance
delete, and before terminal transition. A checkpoint only prevents a new controlled side
effect; it cannot roll back a Provider response or immutable generation already committed
before lease loss.

A crash after generation publication but before job completion leaves the immutable generation
and the job in `running` state. Later expired-lease recovery marks that job `abandoned`; it does
not delete or roll back the generation. Retrying is always a new explicit job linked through
`retry_of_job_id`. PR4B does not implement hidden whole-job retry.

The worker is a library-level same-host execution boundary. It does not provide a scheduler,
service manager, CLI, API, distributed lock, fencing token, multi-host coordination, automatic
daily ingestion, or automatic startup. Only one intentional writer process is supported by the
built-in lock implementation.
## Compatibility, Rollback, and Exclusions

PR4A adds an independent schema v1. It does not change existing EOD generations, manifests,
caches, research artifacts, Coordinator behavior, Provider ordering, or research metrics. It
has no direct relationship to generation retention. It provides no automatic retention,
deletion, repair, vacuum, worker, scheduler, CLI, API, execution, or daily ingestion.

Before any production job store exists, rolling back the PR removes the capability. If a SQLite
store already exists, an older release will not read or modify it; operators should retain the
file until a separate migration or disposition decision. Unknown future schemas always fail
closed and are never migrated automatically.

PR4B's explicit `EODOperationWorker` verifies that the operation store root and every EOD
generation repository root are different and non-nested before execution. PR4A itself still
does not compose or execute those repositories.

This module is research data operations infrastructure only. It has no real-trading capability,
does not call DeepSeek, and does not constitute investment advice.
