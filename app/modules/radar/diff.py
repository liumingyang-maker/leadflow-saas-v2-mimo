"""Pure, canonical Radar snapshot comparison and baseline-drift detection."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DriftResult:
    is_drift: bool
    reason_codes: tuple[str, ...]
    comparable_pages: int
    missing_pages: int


def diff_snapshots(previous: object, current: object, *, detector_version: str) -> bytes:
    """Return a byte-identical structural delta; no model is involved."""

    before = _fact_map(previous)
    after = _fact_map(current)
    added = {key: after[key] for key in sorted(after.keys() - before.keys())}
    removed = {key: before[key] for key in sorted(before.keys() - after.keys())}
    changed = {
        key: {"after": after[key], "before": before[key]}
        for key in sorted(after.keys() & before.keys())
        if after[key] != before[key]
    }
    return json.dumps(
        {
            "added": added,
            "changed": changed,
            "detector_version": detector_version,
            "removed": removed,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()


def detect_baseline_drift(
    *,
    previous_run: object,
    current_run: object,
    previous_pages: tuple[str, ...],
    current_pages: tuple[str, ...],
    previous_facts_by_page: dict[str, tuple[str, ...]] | None = None,
    current_facts_by_page: dict[str, tuple[str, ...]] | None = None,
    page_kinds: dict[str, str] | None = None,
    policy_version: str,
) -> DriftResult:
    """Detect coverage/version risk without resetting any historical baseline."""

    del policy_version  # The caller persists the version; the logic is intentionally pure.
    previous = set(previous_pages)
    current = set(current_pages)
    comparable = len(previous | current)
    if comparable < 3:
        return DriftResult(False, (), comparable, len(previous - current))
    reasons: list[str] = []
    if _field(previous_run, "parser_version") != _field(current_run, "parser_version"):
        reasons.append("parser_version_changed")
    missing = len(previous - current)
    if previous and missing / len(previous) >= 0.5:
        reasons.append("page_identity_loss")
    if (
        previous_facts_by_page is not None
        and current_facts_by_page is not None
        and page_kinds is not None
    ):
        stable = 0
        disappeared = 0
        disappeared_kinds: set[str] = set()
        for page in previous & current:
            before = set(previous_facts_by_page.get(page, ()))
            if not before:
                continue
            after = set(current_facts_by_page.get(page, ()))
            stable += len(before)
            missing_facts = before - after
            disappeared += len(missing_facts)
            if missing_facts:
                disappeared_kinds.add(page_kinds.get(page, "other"))
        if stable and disappeared / stable >= 0.6 and len(disappeared_kinds) >= 2:
            reasons.append("stable_fact_disappearance")
    return DriftResult(bool(reasons), tuple(reasons), comparable, missing)


def _fact_map(value: object) -> dict[str, Any]:
    parsed = _object(value)
    facts = parsed.get("facts", [])
    if not isinstance(facts, list):
        return {}
    grouped: dict[str, list[Any]] = {}
    for item in facts:
        if not isinstance(item, dict):
            continue
        key = item.get("key")
        if isinstance(key, str) and key:
            grouped.setdefault(key, []).append(item.get("value"))
    output: dict[str, Any] = {}
    for key, values in grouped.items():
        canonical = sorted(
            values,
            key=lambda item: json.dumps(
                item,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ),
        )
        output[key] = canonical[0] if len(canonical) == 1 else canonical
    return output


def _object(value: object) -> dict[str, Any]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return {}
    return value if isinstance(value, dict) else {}


def _field(value: object, name: str) -> str:
    if isinstance(value, dict):
        raw = value.get(name, "")
    else:
        raw = getattr(value, name, "")
    return raw if isinstance(raw, str) else ""
