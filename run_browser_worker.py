"""Entrypoint for the database-free Browser RQ worker."""

from __future__ import annotations

import os
import sys

from redis import Redis
from rq import SimpleWorker, Worker
from rq.serializers import JSONSerializer

from app.integrations.browser.worker import assert_isolated_environment


def _worker_class_for(platform_name: str):
    return SimpleWorker if platform_name == "nt" else Worker


def main() -> None:
    assert_isolated_environment()
    redis_url = os.environ.get("BROWSER_REDIS_URL", "")
    if not redis_url:
        raise RuntimeError("BROWSER_REDIS_URL is required")
    queue_names = sys.argv[1:] or ["browser"]
    worker = _worker_class_for(os.name)(
        queue_names,
        connection=Redis.from_url(redis_url),
        serializer=JSONSerializer,
    )
    worker.work()


if __name__ == "__main__":
    main()
