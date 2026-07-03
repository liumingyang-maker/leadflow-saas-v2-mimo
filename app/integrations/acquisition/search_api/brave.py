from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

from app.integrations.acquisition.search_api.base import SearchProviderError, SearchResult

BRAVE_WEB_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"


class BraveSearchProvider:
    source_provider = "brave"

    def __init__(self, *, api_key: str, timeout_seconds: int = 10) -> None:
        self._api_key = api_key.strip()
        self._timeout_seconds = max(1, min(int(timeout_seconds or 10), 30))

    def search(
        self,
        query: str,
        *,
        country: str | None = None,
        language: str | None = None,
        limit: int = 10,
    ) -> list[SearchResult]:
        if not self._api_key:
            raise SearchProviderError("missing_api_key")
        clean_query = query.strip()
        if not clean_query:
            return []
        params = {
            "q": clean_query,
            "count": str(max(1, min(limit, 10))),
            "safesearch": "moderate",
        }
        if country:
            params["country"] = country.strip()[:8]
        if language:
            params["search_lang"] = language.strip()[:8]
        request = urllib.request.Request(
            f"{BRAVE_WEB_SEARCH_URL}?{urllib.parse.urlencode(params)}",
            headers={
                "Accept": "application/json",
                "X-Subscription-Token": self._api_key,
            },
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout_seconds) as response:
                payload = response.read(1_000_000)
        except TimeoutError as exc:
            raise SearchProviderError("provider_timeout") from exc
        except urllib.error.HTTPError as exc:
            raise SearchProviderError(f"provider_http_{exc.code}") from exc
        except urllib.error.URLError as exc:
            raise SearchProviderError("provider_unavailable") from exc

        try:
            data = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SearchProviderError("malformed_response") from exc
        web_results = data.get("web", {}).get("results", [])
        if not isinstance(web_results, list):
            raise SearchProviderError("malformed_response")

        results: list[SearchResult] = []
        for index, item in enumerate(web_results[: max(1, min(limit, 10))], start=1):
            if not isinstance(item, dict):
                continue
            results.append(
                SearchResult(
                    title=str(item.get("title", "")),
                    url=str(item.get("url", "")),
                    snippet=str(item.get("description", "")),
                    source_provider=self.source_provider,
                    rank=index,
                    country=str(country or ""),
                    language=str(language or ""),
                    raw_data={
                        "result_type": "web",
                        "age": str(item.get("age", ""))[:80],
                    },
                )
            )
        return results
