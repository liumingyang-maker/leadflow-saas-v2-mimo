from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

SUITE_VERSION = "acquisition-global-quality-v1"
OUTPUT_FIELDS = (
    "hq_country_code",
    "opportunity_country_code",
    "country_resolution_status",
    "contact_kinds",
    "entity_kind",
)


@dataclass(frozen=True)
class ReplayCase:
    case_id: str
    scenario: str
    target_country_code: str
    source_url: str
    source_path: Path
    source_text: str
    legacy_output: dict[str, object]
    expected: dict[str, object]


@dataclass(frozen=True)
class ReplaySuite:
    version: str
    cases: tuple[ReplayCase, ...]


def load_replay_cases(manifest_path: Path) -> ReplaySuite:
    manifest = manifest_path.resolve(strict=True)
    root = manifest.parent
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("replay manifest must be an object")
    if payload.get("version") != SUITE_VERSION:
        raise ValueError("unsupported replay fixture version")
    raw_cases = payload.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise ValueError("replay fixture cases are required")
    cases: list[ReplayCase] = []
    seen: set[str] = set()
    for item in raw_cases:
        if not isinstance(item, dict):
            raise ValueError("replay case must be an object")
        case_id = str(item.get("id", "")).strip()
        if not case_id or case_id in seen:
            raise ValueError("replay case ids must be present and unique")
        seen.add(case_id)
        source = (root / item["source"]).resolve(strict=True)
        if root not in source.parents:
            raise ValueError("replay source must stay inside the fixture directory")
        legacy = item.get("legacy_output")
        expected = item.get("expected")
        if (
            not isinstance(legacy, dict)
            or not isinstance(expected, dict)
            or set(legacy) != set(OUTPUT_FIELDS)
            or set(expected) != set(OUTPUT_FIELDS)
        ):
            raise ValueError("replay outputs do not match the fixed field contract")
        cases.append(
            ReplayCase(
                case_id=case_id,
                scenario=item["scenario"],
                target_country_code=item["target_country_code"],
                source_url=item["source_url"],
                source_path=source,
                source_text=source.read_text(encoding="utf-8"),
                legacy_output=dict(legacy),
                expected=dict(expected),
            )
        )
    return ReplaySuite(version=payload["version"], cases=tuple(cases))


def compare_legacy_to_expected(suite: ReplaySuite) -> dict[str, object]:
    rows: list[dict[str, object]] = []
    matched = 0
    for case in suite.cases:
        mismatches = [
            field for field in OUTPUT_FIELDS if case.legacy_output[field] != case.expected[field]
        ]
        matched += len(OUTPUT_FIELDS) - len(mismatches)
        rows.append(
            {
                "id": case.case_id,
                "scenario": case.scenario,
                "mismatches": mismatches,
                "legacy_output": case.legacy_output,
                "expected": case.expected,
            }
        )
    field_count = len(suite.cases) * len(OUTPUT_FIELDS)
    return {
        "suite_version": suite.version,
        "case_count": len(suite.cases),
        "field_count": field_count,
        "matched_fields": matched,
        "gap_fields": field_count - matched,
        "cases": rows,
    }


def _main() -> int:
    parser = argparse.ArgumentParser(description="Compare frozen acquisition output with labels")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = compare_legacy_to_expected(load_replay_cases(args.manifest))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"wrote replay report: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
