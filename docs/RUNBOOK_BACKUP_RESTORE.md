# Runbook: Backup & Restore

## Recovery objective and data ownership

Phase 1A is a single-operator deployment with a daily backup target: **RPO 24 hours, RTO 4 hours**. Product knowledge, Mission, Candidate, Evidence, Assessment, Suggestion, Notification, Lead and Job records live in SQL and must be backed up together. Redis is transient queue transport, not a source of truth; it does not need a durable restore.

Store backups outside the application volume and test a restore at least monthly. A backup is not considered successful until its file size is non-zero and the latest restore drill passes.

## Daily backup

Stop the Worker and reconciler, or use SQLite's online backup command, so the copy is consistent.

```bash
# SQLite inside the Docker volume
mkdir -p /backups
sqlite3 /data/leadflow-v2.db ".backup '/backups/leadflow-latest.db'"
test -s /backups/leadflow-latest.db

# PostgreSQL after the staging migration
pg_dump --format=custom --file=/backups/leadflow-latest.dump "$DATABASE_URL"
test -s /backups/leadflow-latest.dump
```

Retain seven daily backups and four weekly backups. Encrypt backups at rest and keep database credentials outside filenames, logs and shell history.

## Restore

Restore into a new volume/database first; do not overwrite the only known-good database.

```bash
# SQLite
sqlite3 /restore/leadflow-v2.db ".restore '/backups/leadflow-latest.db'"
DATABASE_URL=sqlite:////restore/leadflow-v2.db alembic upgrade head

# PostgreSQL
createdb leadflow_restore
pg_restore --clean --if-exists --no-owner --dbname=leadflow_restore /backups/leadflow-latest.dump
DATABASE_URL=postgresql://localhost/leadflow_restore alembic upgrade head
```

## Required restore verification

1. Run `alembic current` and confirm it equals `alembic heads`.
2. Compare per-tenant counts for ProductKnowledgeSnapshot, AcquisitionMission, AcquisitionCandidate, CandidateEvidence, CandidateAssessment, MissionSuggestion, Notification and Lead against the backup manifest.
3. Sample at least five Evidence rows and verify canonical URL, content hash and Candidate foreign key.
4. Sample accepted Candidates and confirm each Candidate-to-Lead promotion is present and tenant-scoped.
5. Start Redis, one `default` Worker and the reconciler. Run `/health/live` and `/health/ready`.
6. Open the workbench and confirm review, reply, failed-job and notification counts render without cross-tenant data.

If any check fails, keep the original environment read-only, discard the failed restore target, record a safe incident summary and repeat from another backup.

## Queue recovery

After SQL is restored, start Redis empty. Start exactly one Worker, then run:

```bash
python -m app.modules.acquisition.jobs reconcile
```

Persistent Job rows are used to recover stale work. Never restore an old Redis snapshot over newer SQL state.

## Migration and secret safety

- Back up before `alembic upgrade head`; verify downgrade/upgrade on a disposable database first.
- Never edit a migration already deployed to a shared environment.
- Rotate `SECRET_KEY`, `TENANT_SECRET_KEY`, `TRACKING_SIGNING_KEY`, `UNSUBSCRIBE_SIGNING_KEY` and `INBOUND_TOKEN_KEY` separately. Restart Web/Worker/reconciler after rotation.
- Inbound tokens must be regenerated after their signing key changes.
