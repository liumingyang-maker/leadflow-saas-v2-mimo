from __future__ import annotations

import json
import subprocess
import sys
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
                        "source_url": "https://escape.example/",
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
                        "source_url": "https://invalid.example/",
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
        "source_url": "https://contract.example/",
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


def test_fixture_matrix_covers_global_and_negative_cases() -> None:
    from tools.acquisition_quality_replay import load_replay_cases

    suite = load_replay_cases(FIXTURE_ROOT / "cases.json")
    case_ids = {case.case_id for case in suite.cases}
    by_id = {case.case_id: case for case in suite.cases}

    assert {
        "mx-official-address",
        "br-local-phone",
        "de-eu-cross-border",
        "us-dot-com-address",
        "cn-headquarters-serves-mx",
        "generic-dot-co",
        "global-headquarters-opportunity-split",
        "sparse-single-page",
        "association-or-chamber",
        "directory-or-marketplace",
        "government",
        "media-or-article",
        "careers-page",
        "dealer-counterexample",
    } <= case_ids
    assert len(case_ids) == len(suite.cases)
    assert all(case.source_text.strip() for case in suite.cases)
    assert all("<script" not in case.source_text.casefold() for case in suite.cases)
    assert by_id["mx-official-address"].source_url.endswith(".com.mx/")
    assert by_id["br-local-phone"].source_url.endswith(".com.br/")
    assert by_id["de-eu-cross-border"].source_url.endswith(".de/")
    assert by_id["cn-headquarters-serves-mx"].source_url.endswith(".com.cn/")
    assert by_id["generic-dot-co"].source_url.endswith(".co/")


def test_compare_legacy_to_expected_is_deterministic_and_field_level() -> None:
    from tools.acquisition_quality_replay import compare_legacy_to_expected, load_replay_cases

    suite = load_replay_cases(FIXTURE_ROOT / "cases.json")
    first = compare_legacy_to_expected(suite)
    second = compare_legacy_to_expected(suite)

    assert first == second
    assert first["suite_version"] == "acquisition-global-quality-v1"
    assert first["case_count"] == 14
    assert first["field_count"] == 70
    mexico = next(item for item in first["cases"] if item["id"] == "mx-official-address")
    assert set(mexico["mismatches"]) == {
        "hq_country_code",
        "opportunity_country_code",
        "country_resolution_status",
        "contact_kinds",
        "entity_kind",
    }
    generic_co = next(item for item in first["cases"] if item["id"] == "generic-dot-co")
    assert "opportunity_country_code" not in generic_co["mismatches"]


def test_replay_cli_writes_only_the_deterministic_report(tmp_path: Path) -> None:
    from tools.acquisition_quality_replay import compare_legacy_to_expected, load_replay_cases

    repository = Path(__file__).resolve().parents[2]
    output = tmp_path / "replay.json"
    completed = subprocess.run(
        [
            sys.executable,
            str(repository / "tools" / "acquisition_quality_replay.py"),
            "--manifest",
            str(FIXTURE_ROOT / "cases.json"),
            "--output",
            str(output),
        ],
        cwd=repository,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )

    assert completed.returncode == 0
    assert json.loads(output.read_text(encoding="utf-8")) == compare_legacy_to_expected(
        load_replay_cases(FIXTURE_ROOT / "cases.json")
    )
    assert completed.stdout.strip() == f"wrote replay report: {output}"
    assert completed.stderr == ""
