from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_makefile_exposes_local_quality_gates() -> None:
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")

    for target in ["lint:", "format-check:", "test:", "diff-check:", "check:"]:
        assert target in makefile

    assert "ruff check ." in makefile
    assert "ruff format --check ." in makefile
    assert "pytest" in makefile
    assert "git diff --check" in makefile


def test_ci_workflow_runs_same_quality_gates() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "python-version: '3.12'" in workflow
    assert "pip install -r requirements-dev.txt" in workflow
    assert "python -m ruff check ." in workflow
    assert "python -m ruff format --check ." in workflow
    assert "python -m pytest" in workflow
    assert "git diff --check" in workflow


def test_windows_check_script_runs_same_quality_gates() -> None:
    script = (ROOT / "scripts" / "check.ps1").read_text(encoding="utf-8")

    assert "-m ruff check ." in script
    assert "-m ruff format --check ." in script
    assert "-m pytest" in script
    assert "git diff --check" in script
