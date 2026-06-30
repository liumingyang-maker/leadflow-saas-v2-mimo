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
from rq import Worker
from rq.serializers import JSONSerializer

redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

# Parse --skip-recovery before RQ args
skip_recovery = "--skip-recovery" in sys.argv
queue_names = [a for a in (sys.argv[1:] or ["default"]) if a != "--skip-recovery"]

redis_conn = Redis.from_url(redis_url)


def _run_recovery() -> None:
    """Run stale-job recovery with its own DB connection."""
    from app import create_app
    from app.modules.jobs.worker import recover_stale_jobs

    app = create_app(os.environ.get("APP_ENV", "development"))
    count = recover_stale_jobs(app)
    if count:
        print(f"Recovered {count} stale job(s)")


if __name__ == "__main__":
    if not skip_recovery:
        print("Running stale-job recovery...")
        _run_recovery()
        print("Recovery complete.")

    worker = Worker(queue_names, connection=redis_conn, serializer=JSONSerializer)
    worker.work()
