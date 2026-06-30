"""Collection adapter protocol — output normalization contract."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class Candidate:
    """Normalized output from any collection adapter.

    All fields are safe strings — no raw HTML, no secrets, no
    full third-party API responses.
    """

    email: str = ""
    first_name: str = ""
    last_name: str = ""
    company: str = ""
    title: str = ""
    phone: str = ""
    website: str = ""
    domain: str = ""
    address: str = ""
    country: str = ""
    source: str = ""
    source_url: str = ""
    industry: str = ""
    metadata_json: str = "{}"


@dataclass
class CollectionResult:
    """Result summary from a collection adapter run."""

    candidates: list[Candidate] = field(default_factory=list)
    found_count: int = 0
    error_code: str = ""
    error_summary: str = ""
    is_transient: bool = False


class CollectionAdapter(Protocol):
    """Interface every collection adapter must implement."""

    def collect(self, *, payload: dict, max_results: int) -> CollectionResult:
        """Run a collection and return normalized candidates."""
        ...
