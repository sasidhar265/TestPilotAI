# Organisational memory protection

This change protects the organisational knowledge store, not every application database or
exported evidence file, and does not establish regulatory compliance.

## Configure before enabling

Memory is disabled by default. Set `ORGANIZATIONAL_MEMORY_ENABLED=true` only with a valid
`ORGANIZATIONAL_MEMORY_ENCRYPTION_KEY` supplied through your secret manager. Generate a Fernet
key using `cryptography.fernet.Fernet.generate_key()` in the approved provisioning environment;
do not paste keys into tickets, source control, command arguments or logs. Keep the key separate
from the database and backups, and restrict application/maintenance access to it. Losing the key
makes the store unreadable. There is no automatic key generation or plaintext fallback.

`ORGANIZATIONAL_MEMORY_RETENTION_DAYS` accepts 1–365 days, default 30. This is a configurable
technical default, not a legal retention recommendation. It applies to suites, reviews, workflow
stories/scenarios, C# implementation caches and converted outputs, including their scenario rows.
Reading a record does not extend retention; updating its stored content restarts its lifetime.
Expiry runs on every store connection, at application startup and hourly while the app is running.
Schedule the `purge-expired` command when the application is stopped. Backup expiry is separate.

The entire SQLite snapshot is authenticated and encrypted with Fernet. SQLite runs in memory;
only encrypted bytes reach the snapshot or atomic replacement temporary files. A process lock
serializes reads/writes. This targets small, single-node knowledge stores; each operation loads
and rewrites the snapshot when changed, so memory and I/O scale with the store size. Keep one
application process per container and do not share the file across network filesystems/replicas.
OS swap, core dumps and privileged process access require separate host controls.

## Migrate existing plaintext memory

Install the updated dependencies. Stop the application and every old writer first. Provision the
encryption key, then run against a NEW destination; source data is preserved and an existing
destination is rejected. The maintenance CLI reads its key/retention from environment variables,
not from `.env` or the application settings cache.

```sh
python -m app.memory_admin migrate .agent-memory/test_suites.db --destination .agent-memory/test_suites.encrypted
```

Migration includes committed WAL data. Existing valid creation timestamps are used for retention;
rows without timestamps start their retention window at migration. Already expired records are
removed from the encrypted destination. Verify expected counts and retrieval in an isolated
instance using `ORGANIZATIONAL_MEMORY_PATH=.agent-memory/test_suites.encrypted`, then change the
production path and restart. The new app refuses legacy plaintext instead of reading or modifying
it. Do not reuse the plaintext source path without completing migration.

After verification, retire the plaintext source, its WAL/SHM sidecars, old backups and snapshots
through the approved storage-deletion process. The command deliberately leaves them intact for
recovery. File deletion alone does not guarantee erasure on SSDs, snapshots or managed storage.

## Expiry and deletion

With the key and approved retention value in the operator environment:

```sh
python -m app.memory_admin purge-expired .agent-memory/test_suites.encrypted
python -m app.memory_admin erase .agent-memory/test_suites.encrypted --confirm
```

`erase` removes ALL suites, reviews, workflow caches, converted outputs/scenarios and C# caches
from this store, compacts it, and writes a fresh encrypted snapshot. It is intentionally an
operator command, not a guest/user API. It does not erase lifecycle records, user accounts,
accepted output files, downloads, provider-side records, or backups. A person-specific deletion
request requires locating those copies and applying the organisation's legal-hold/deletion policy.

## Backup and recovery

Stop writers and copy the encrypted snapshot to approved restricted backup storage. Do not use
SQLite tools or `app.resilience backup` directly on this encrypted file. Back up the key through
a separate controlled recovery mechanism. To restore, copy into a NEW path and validate it with
`purge-expired` using the matching key, then verify retrieval before changing the application path.
Expired content is removed on opening a restored backup. Never restore legacy plaintext into a
live protected store. Apply retention/deletion to every backup independently.

For key rotation, stop writers, use a reviewed process to decrypt in memory and re-encrypt to a
new destination, and verify with the new key before cutover. Keep recovery keys only as long as
required for retained backups. This release does not automate key-manager integration or rotation.

## Validation recorded on 27 September 2026

- 101 focused Python checks passed across protected memory, suite/output/workflow/C# storage,
  guest policy and production hardening. Includes encryption/no plaintext files, wrong or missing
  keys, tampering, committed WAL migration, retention across all caches, erase confirmation,
  concurrent writes, transaction rollback and failed atomic replacement.
- 9 Chromium browser checks passed: guest previews at 390px/1440px and existing navigation/theme
  tests. Guest previews requested no protected workspace data.
- 14 ReqnRoll scenarios were discovered and executed against an isolated localhost application
  with synthetic credentials, temporary stores and guest access configured. All passed, none
  skipped: 10 guest scenarios plus the existing 2 API and 2 security scenarios. Actual TRX output:
  `automation/TestResults/Reports/privacy-controls/privacy-controls.trx`.
- Changed Python files pass Ruff; `mypy app` passes. Repository-wide Ruff also reports existing
  issues in requirements validation, PDF export and workflow routes, outside this change.
- The separate review-feedback suite has 4 passes and 8 failures because its generation tests lack
  effective approved business sources. The exact same 8 failures were reproduced from the
  unchanged HEAD revision in an isolated checkout; the requirements gate was not weakened.

These checks do not establish production deployment, migration of existing customer data,
backup deletion, or regulatory compliance. No generated quotation packs were changed or run.
