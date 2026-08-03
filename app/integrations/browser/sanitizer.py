"""Sanitize untrusted Browser snapshots before they cross the worker boundary."""

from __future__ import annotations

import re
from dataclasses import dataclass

MAX_SNAPSHOT_TEXT = 20_000
_INJECTION = re.compile(
    r"\b(?:ignore\s+(?:all\s+)?(?:previous|prior|system)\s+(?:instructions?|prompts?)|"
    r"system\s+prompt|reveal\s+(?:the\s+)?(?:secret|password|api\s*key)|"
    r"(?:call|use|invoke)\s+(?:this\s+)?tool)\b",
    re.I,
)
_SENSITIVE_VALUE = re.compile(
    r"\b(?:authorization|cookie|password|secret|api[_ -]?key|access[_ -]?token)\b\s*[:=]\s*\S+",
    re.I,
)
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


@dataclass(frozen=True)
class SanitizedBrowserSnapshot:
    text: str
    prompt_injection_detected: bool


def sanitize_browser_snapshot(
    value: str, *, limit: int = MAX_SNAPSHOT_TEXT
) -> SanitizedBrowserSnapshot:
    """Drop instruction-like lines and sensitive values, retaining bounded visible evidence."""

    bounded_limit = max(1, min(int(limit), MAX_SNAPSHOT_TEXT))
    injection_detected = False
    kept: list[str] = []
    for raw_line in str(value).splitlines():
        line = _CONTROL.sub(" ", raw_line).strip()
        if not line:
            continue
        if _INJECTION.search(line):
            injection_detected = True
            continue
        kept.append(_SENSITIVE_VALUE.sub("[redacted]", line))
        if sum(len(item) + 1 for item in kept) >= bounded_limit:
            break
    text = "\n".join(kept)[:bounded_limit].strip()
    return SanitizedBrowserSnapshot(text=text, prompt_injection_detected=injection_detected)
