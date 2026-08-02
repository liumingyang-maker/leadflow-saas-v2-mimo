"""Worker process entry point.

Stale-job recovery runs automatically before the worker starts.
Use ``--skip-recovery`` to skip (testing/maintenance only).

Run:  python run_worker.py [--skip-recovery] [queue_name ...]
"""

from __future__ import annotations

import os
import sys

os.environ["APP_ENV"] = os.environ.get("APP_ENV", "development")

from redis import Redis
from rq import SimpleWorker, Worker
from rq.serializers import JSONSerializer

redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

# Parse --skip-recovery before RQ args
skip_recovery = "--skip-recovery" in sys.argv
queue_names = [a for a in (sys.argv[1:] or ["default"]) if a != "--skip-recovery"]

redis_conn = Redis.from_url(redis_url)


def _worker_class_for(platform_name: str):
    return SimpleWorker if platform_name == "nt" else Worker


def _run_recovery() -> None:
    """Run stale-job recovery and mission reconciliation with their own DB connection."""
    from datetime import UTC, datetime

    from app import create_app
    from app.modules.acquisition.jobs import reconcile_missions

    app = create_app(os.environ.get("APP_ENV", "development"))
    count = reconcile_missions(app, now=datetime.now(UTC))
    if count:
        print(f"Reconciled {count} acquisition mission(s)")


if __name__ == "__main__":
    if not skip_recovery:
        print("Running stale-job recovery...")
        _run_recovery()
        print("Recovery complete.")

    worker_class = _worker_class_for(os.name)
    worker = worker_class(queue_names, connection=redis_conn, serializer=JSONSerializer)
    worker.work()
