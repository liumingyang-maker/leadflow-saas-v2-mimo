from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURE_ROOT = Path(__file__).parent.parent / "fixtures" / "acquisition" / "global_quality"


def test_load_replay_cases_reads_versioned_redacted_fixture() -> None:
    from tools.acquisition_quality_replay import load_replay_cases

    suite = load_replay_cases(FIXTURE_ROOT / "cases.json")

    assert suite.version == "acquisition-global-quality-v1"
    assert suite.cases[0].case_id == "mx-official-address"
    assert suite.cases[0].source_path.name == "mx_official.html"
    assert "Dirección oficial" in suite.cases[0].source_text
    assert suite.cases[0].expected["opportunity_country_code"] == "MX"


def test_load_replay_cases_rejects_source_outside_fixture_directory(tmp_path: Path) -> None:
    from tools.acquisition_quality_replay import load_replay_cases

    fixture_root = tmp_path / "fixtures"
    fixture_root.mkdir()
    (tmp_path / "outside.html").write_text("outside", encoding="utf-8")
    output = {
        "hq_country_code": "",
        "opportunity_country_code": "",
        "country_resolution_status": "unknown",
        "contact_kinds": [],
        "entity_kind": "unknown",
    }
    (fixture_root / "cases.json").write_text(
        json.dumps(
            {
                "version": "acquisition-global-quality-v1",
                "cases": [
                    {
                        "id": "escape",
                        "scenario": "path traversal",
                        "source": "../outside.html",
                        "target_country_code": "",
                        "legacy_output": output,
                        "expected": output,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="stay inside"):
        load_replay_cases(fixture_root / "cases.json")


def test_load_replay_cases_rejects_unsupported_fixture_version(tmp_path: Path) -> None:
    from tools.acquisition_quality_replay import load_replay_cases

    source = tmp_path / "source.html"
    source.write_text("fixture", encoding="utf-8")
    output = {
        "hq_country_code": "",
        "opportunity_country_code": "",
        "country_resolution_status": "unknown",
        "contact_kinds": [],
        "entity_kind": "unknown",
    }
    manifest = tmp_path / "cases.json"
    manifest.write_text(
        json.dumps(
            {
                "version": "unsupported-v9",
                "cases": [
                    {
                        "id": "case-1",
                        "scenario": "invalid version",
                        "source": source.name,
                        "target_country_code": "",
                        "legacy_output": output,
                        "expected": output,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="unsupported replay fixture version"):
        load_replay_cases(manifest)


@pytest.mark.parametrize(
    ("invalid_kind", "message"),
    [
        ("empty", "replay fixture cases are required"),
        ("duplicate", "present and unique"),
        ("missing_field", "fixed field contract"),
    ],
)
def test_load_replay_cases_rejects_invalid_case_contract(
    tmp_path: Path, invalid_kind: str, message: str
) -> None:
    from tools.acquisition_quality_replay import load_replay_cases

    source = tmp_path / "source.html"
    source.write_text("fixture", encoding="utf-8")
    output = {
        "hq_country_code": "",
        "opportunity_country_code": "",
        "country_resolution_status": "unknown",
        "contact_kinds": [],
        "entity_kind": "unknown",
    }
    case = {
        "id": "case-1",
        "scenario": "contract validation",
        "source": source.name,
        "target_country_code": "",
        "legacy_output": output,
        "expected": output,
    }
    if invalid_kind == "empty":
        cases = []
    elif invalid_kind == "duplicate":
        cases = [case, dict(case)]
    else:
        case = {
            **case,
            "expected": {key: value for key, value in output.items() if key != "entity_kind"},
        }
        cases = [case]
    manifest = tmp_path / "cases.json"
    manifest.write_text(
        json.dumps({"version": "acquisition-global-quality-v1", "cases": cases}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=message):
        load_replay_cases(manifest)
