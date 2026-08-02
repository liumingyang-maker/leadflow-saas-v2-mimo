def test_windows_uses_simple_worker():
    from rq import SimpleWorker

    import run_worker

    assert run_worker._worker_class_for("nt") is SimpleWorker


def test_non_windows_keeps_worker():
    from rq import Worker

    import run_worker

    assert run_worker._worker_class_for("posix") is Worker
