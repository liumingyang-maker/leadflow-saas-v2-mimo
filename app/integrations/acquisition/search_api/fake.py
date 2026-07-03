from __future__ import annotations

from app.integrations.acquisition.search_api.base import SearchResult


class FakeSearchProvider:
    source_provider = "fake"

    def search(
        self,
        query: str,
        *,
        country: str | None = None,
        language: str | None = None,
        limit: int = 10,
    ) -> list[SearchResult]:
        clean_country = (country or "Global").strip() or "Global"
        clean_language = (language or "en").strip() or "en"
        templates = [
            ("Atlas Global Imports", "https://atlas-global-imports.example"),
            ("Northstar Distribution Group", "https://northstar-distribution.example"),
            ("Meridian Wholesale Partners", "https://meridian-wholesale.example"),
            ("Harbor Retail Sourcing", "https://harbor-retail-sourcing.example"),
            ("Summit Procurement Co", "https://summit-procurement.example"),
        ]
        results: list[SearchResult] = []
        for index, (name, url) in enumerate(templates[: max(0, min(limit, 10))], start=1):
            results.append(
                SearchResult(
                    title=f"{name} - buyer profile",
                    url=url,
                    snippet=f"{name} may match search query: {query}",
                    source_provider=self.source_provider,
                    rank=index,
                    country=clean_country,
                    language=clean_language,
                    raw_data={"result_type": "fake_web"},
                )
            )
        return results
