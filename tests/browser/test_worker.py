from __future__ import annotations

from pathlib import Path

import pytest


def test_worker_rejects_application_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.integrations.browser.worker import assert_isolated_environment

    monkeypatch.setenv("DATABASE_URL", "sqlite:///secret.db")
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        assert_isolated_environment()


def test_artifact_subdirectory_cannot_escape(tmp_path: Path) -> None:
    from app.integrations.browser.worker import resolve_artifact_directory

    with pytest.raises(ValueError, match="artifact_path_invalid"):
        resolve_artifact_directory(tmp_path, "../escape")


def test_worker_uses_only_bounded_browser_transport_keys() -> None:
    from app.integrations.browser.worker import cancel_key, heartbeat_key

    assert heartbeat_key("run-1", 2) == "browser:heartbeat:run-1:2"
    assert cancel_key("run-1", 2) == "browser:cancel:run-1:2"


def test_orphan_cleanup_preserves_active_and_retain_markers(tmp_path: Path) -> None:
    from app.integrations.browser.worker import cleanup_orphan_artifacts

    stale = tmp_path / "stale"
    active = tmp_path / "active"
    retained = tmp_path / "retained"
    for directory in (stale, active, retained):
        directory.mkdir()
    (active / ".active").touch()
    (retained / ".retain").touch()

    removed = cleanup_orphan_artifacts(tmp_path, older_than_seconds=0)

    assert removed == ["stale"]
    assert not stale.exists()
    assert active.exists()
    assert retained.exists()
