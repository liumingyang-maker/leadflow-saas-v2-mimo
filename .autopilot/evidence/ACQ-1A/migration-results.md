# Phase 1A migration round-trip evidence

Date: 2026-08-02

The check used a new disposable SQLite database inside the isolated worktree and set `DATABASE_URL` explicitly. The migration environment now honors that override.

Commands executed in order:

```text
python -m alembic upgrade head
python -m alembic downgrade 0013_admin_auth_version
python -m alembic upgrade head
python -m alembic current
```

Result: PASS

Final revision:

```text
0014_acquisition_core (head)
```

The disposable database path was validated as a direct child of the worktree and deleted after the successful check.

This evidence is a local SQLite migration round trip. It does not replace the required PostgreSQL staging migration and concurrency gate.
