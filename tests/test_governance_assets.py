from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_third_party_skill_lock_has_pinned_commits_and_skill_docs() -> None:
    lock = json.loads((ROOT / ".agents" / "skill-lock.json").read_text(encoding="utf-8"))
    expected = {
        "ui-ux-pro-max",
        "frontend-design",
        "web-design-guidelines",
        "motion-design",
    }

    skills = {item["name"]: item for item in lock["skills"]}
    assert set(skills) == expected

    for name, item in skills.items():
        assert item["repo"].startswith("https://github.com/")
        assert len(item["commit"]) == 40
        int(item["commit"], 16)
        assert (ROOT / ".agents" / "skills" / name / "SKILL.md").is_file()


def test_skill_installer_does_not_execute_third_party_scripts() -> None:
    installer = (ROOT / "tools" / "install_ui_skills.py").read_text(encoding="utf-8")

    assert "shutil.copytree(source, target)" in installer
    assert "SKILL.md" in installer
    assert "No third-party skill scripts were executed." in installer
    assert "npm install" not in installer
    assert "pip install" not in installer


def test_autopilot_runtime_outputs_are_ignored_but_state_and_packets_persist() -> None:
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")

    for ignored in [
        ".autopilot/logs/",
        ".autopilot/screenshots/",
        ".autopilot/tmp/",
        ".autopilot/controller-output/",
    ]:
        assert ignored in ignore

    assert (ROOT / ".autopilot" / "state.json").is_file()
    assert (ROOT / ".autopilot" / "packets" / "V2-01-001.md").is_file()


def test_migration_matrix_captures_p0_security_contracts() -> None:
    matrix = (ROOT / "docs" / "OLD_TO_V2_MIGRATION_MATRIX.md").read_text(encoding="utf-8")

    for contract in [
        "P0-001 no default admin",
        "P0-002 global CSRF",
        "P0-003 tenant-owned tasks",
        "P0-004 signed click redirects",
        "P0-005 cookie/proxy/account guard",
        "P0-006 encrypted tenant secrets",
        "P0-007 hardened inbound API",
    ]:
        assert contract in matrix

    assert "Do not copy old `web/app.py`" in matrix
    assert "Old repository access remains read-only" in matrix
