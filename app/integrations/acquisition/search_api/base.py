from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    snippet: str
    source_provider: str
    rank: int
    country: str = ""
    language: str = ""
    raw_data: dict[str, object] = field(default_factory=dict)


class SearchProviderError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class SearchProvider(Protocol):
    def search(
        self,
        query: str,
        *,
        country: str | None = None,
        language: str | None = None,
        limit: int = 10,
    ) -> list[SearchResult]: ...
