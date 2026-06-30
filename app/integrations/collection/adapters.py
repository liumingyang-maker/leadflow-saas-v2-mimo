"""Collection adapters: Google Search, Google Maps, CSV/XLSX."""

from __future__ import annotations

import json
import random

from app.integrations.collection.contracts import Candidate, CollectionResult

# ---------------------------------------------------------------------------
# Fake search adapter — for development / testing
# ---------------------------------------------------------------------------


class FakeSearchAdapter:
    """Simulates a Google Search collection without real network calls.

    Returns plausible-looking candidates.  Register with:
    ``register_adapter("google_search", FakeSearchAdapter())``
    """

    _DOMAINS = ["example.com", "acme.org", "testcorp.io", "sample.net", "demo.co"]
    _FIRST_NAMES = ["Alice", "Bob", "Carol", "Dave", "Eve", "Frank"]
    _LAST_NAMES = ["Smith", "Jones", "Lee", "Garcia", "Brown", "Wilson"]
    _COMPANIES = ["Acme Corp", "Beta Inc", "Gamma LLC", "Delta Co", "Echo Ltd"]
    _TITLES = ["CEO", "CTO", "VP Sales", "Marketing Director", "Founder"]
    _INDUSTRIES = ["Technology", "Healthcare", "Finance", "Manufacturing"]

    def collect(self, *, payload: dict, max_results: int = 20) -> CollectionResult:
        query = payload.get("query", "")
        max_results = min(max_results, 100)

        if not query:
            return CollectionResult(
                found_count=0,
                error_code="invalid_input",
                error_summary="Search query is required",
                is_transient=False,
            )

        count = min(max_results, random.randint(1, 20))
        candidates = []
        for i in range(count):
            first = random.choice(self._FIRST_NAMES)
            last = random.choice(self._LAST_NAMES)
            domain = random.choice(self._DOMAINS)
            email = f"{first.lower()}.{last.lower()}{i}@{domain}"
            candidates.append(
                Candidate(
                    email=email,
                    first_name=first,
                    last_name=last,
                    company=random.choice(self._COMPANIES),
                    title=random.choice(self._TITLES),
                    website=f"https://{domain}",
                    domain=domain,
                    source="google_search",
                    source_url=f"https://google.com/search?q={query}&start={i * 10}",
                    industry=random.choice(self._INDUSTRIES),
                    metadata_json=json.dumps({"query": query, "rank": i + 1}),
                )
            )

        return CollectionResult(
            candidates=candidates,
            found_count=len(candidates),
        )


# ---------------------------------------------------------------------------
# Fake Maps adapter — for development / testing
# ---------------------------------------------------------------------------


class FakeMapsAdapter:
    """Simulates Google Maps Places collection without real network calls."""

    _PLACES = [
        ("Tech Hub", "123 Main St", "San Francisco"),
        ("Innovation Lab", "456 Oak Ave", "New York"),
        ("Data Center Pro", "789 Pine Rd", "Chicago"),
        ("Cloud Solutions", "321 Elm St", "Austin"),
        ("AI Research Inc", "654 Birch Ln", "Seattle"),
    ]

    def collect(self, *, payload: dict, max_results: int = 20) -> CollectionResult:
        query = payload.get("query", "")
        location = payload.get("location", "")
        max_results = min(max_results, 100)

        if not query or not location:
            return CollectionResult(
                found_count=0,
                error_code="invalid_input",
                error_summary="Both query and location are required",
                is_transient=False,
            )

        count = min(max_results, len(self._PLACES))
        candidates = []
        for i in range(count):
            name, address, city = self._PLACES[i]
            domain = name.lower().replace(" ", "") + ".com"
            candidates.append(
                Candidate(
                    company=name,
                    address=f"{address}, {city}",
                    country="United States",
                    website=f"https://{domain}",
                    domain=domain,
                    phone=f"+1-555-{random.randint(100, 999):03d}-{random.randint(1000, 9999):04d}",
                    source="google_maps",
                    source_url=f"https://maps.google.com/?q={query}+{location}",
                    metadata_json=json.dumps({"query": query, "location": location}),
                )
            )

        return CollectionResult(
            candidates=candidates,
            found_count=len(candidates),
        )


# ---------------------------------------------------------------------------
# CSV/XLSX collection adapter — reuses V2-03 import parser
# ---------------------------------------------------------------------------


class CsvXlsxAdapter:
    """Wraps the V2-03 import parser as a collection adapter.

    The file content must be provided in the payload as ``file_bytes``
    (base64-encoded) or via a pre-uploaded ImportBatch.
    """

    def collect(self, *, payload: dict, max_results: int = 5000) -> CollectionResult:
        filename = payload.get("filename", "")
        content_b64 = payload.get("file_bytes_base64", "")

        if not filename or not content_b64:
            return CollectionResult(
                found_count=0,
                error_code="invalid_input",
                error_summary="Filename and file content required",
                is_transient=False,
            )

        import base64

        try:
            content = base64.b64decode(content_b64)
        except Exception:
            return CollectionResult(
                found_count=0,
                error_code="invalid_input",
                error_summary="Invalid file data",
                is_transient=False,
            )

        from app.modules.leads.import_service import parse_import_file

        try:
            result = parse_import_file(filename, content, max_rows=max_results)
        except Exception as exc:
            return CollectionResult(
                found_count=0,
                error_code="parse_error",
                error_summary=str(exc)[:200],
                is_transient=False,
            )

        candidates = []
        for row in result.rows:
            if not row.is_valid:
                continue
            candidates.append(
                Candidate(
                    email=row.email,
                    first_name=row.first_name,
                    last_name=row.last_name,
                    company=row.company,
                    title=row.title,
                    phone=row.phone,
                    website=row.website,
                    domain=__import__(
                        "app.modules.leads.import_service", fromlist=["extract_domain"]
                    ).extract_domain(row.email or row.website or ""),
                    source="csv_import" if filename.endswith(".csv") else "xlsx_import",
                    industry=row.industry,
                )
            )

        return CollectionResult(
            candidates=candidates,
            found_count=len(candidates),
        )


# ---------------------------------------------------------------------------
# Real Google Search adapter — uses Custom Search JSON API
# ---------------------------------------------------------------------------


class GoogleSearchAdapter:
    """Real Google Custom Search API adapter.

    Requires GOOGLE_SEARCH_API_KEY and GOOGLE_SEARCH_CX environment variables.
    """

    API_URL = "https://www.googleapis.com/customsearch/v1"

    def __init__(self, *, api_key: str, cx: str) -> None:
        self._api_key = api_key
        self._cx = cx

    def collect(self, *, payload: dict, max_results: int = 20) -> CollectionResult:
        import urllib.parse

        query = payload.get("query", "")
        max_results = min(max_results, 100)

        if not query:
            return CollectionResult(
                found_count=0,
                error_code="invalid_input",
                error_summary="Search query is required",
                is_transient=False,
            )

        candidates: list[Candidate] = []
        start = 1
        while len(candidates) < max_results and start <= 100:
            batch_size = min(10, max_results - len(candidates))
            url = (
                f"{self.API_URL}?key={self._api_key}"
                f"&cx={self._cx}&q={urllib.parse.quote(query)}"
                f"&start={start}&num={batch_size}"
            )
            try:
                req = urllib.request.Request(url, headers={"Accept": "application/json"})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    data = json.loads(resp.read().decode())
            except urllib.error.HTTPError as exc:
                if exc.code == 429:
                    return CollectionResult(
                        found_count=len(candidates),
                        error_code="rate_limited",
                        error_summary="Google API rate limit exceeded",
                        is_transient=True,
                    )
                return CollectionResult(
                    found_count=0,
                    error_code="api_error",
                    error_summary=f"Google API returned {exc.code}",
                    is_transient=exc.code >= 500,
                )
            except (OSError, TimeoutError):
                return CollectionResult(
                    found_count=0,
                    error_code="connection_error",
                    error_summary="Could not connect to Google API",
                    is_transient=True,
                )

            items = data.get("items", [])
            if not items:
                break

            for item in items:
                link = item.get("link", "")
                domain = _extract_domain_from_url(link)
                snippet = item.get("snippet", "")
                candidates.append(
                    Candidate(
                        company=item.get("title", "")[:200],
                        website=link,
                        domain=domain,
                        source="google_search",
                        source_url=link,
                        metadata_json=json.dumps(
                            {
                                "query": query,
                                "snippet": snippet[:500],
                            }
                        ),
                    )
                )
            start += len(items)

        return CollectionResult(
            candidates=candidates[:max_results],
            found_count=len(candidates[:max_results]),
        )


# ---------------------------------------------------------------------------
# Real Google Maps adapter — uses Places API (Text Search)
# ---------------------------------------------------------------------------


class GoogleMapsAdapter:
    """Real Google Places API adapter (Text Search).

    Requires GOOGLE_MAPS_API_KEY environment variable.
    """

    API_URL = "https://maps.googleapis.com/maps/api/place/textsearch/json"

    def __init__(self, *, api_key: str) -> None:
        self._api_key = api_key

    def collect(self, *, payload: dict, max_results: int = 20) -> CollectionResult:
        import urllib.parse

        query = payload.get("query", "")
        location = payload.get("location", "")
        max_results = min(max_results, 60)

        if not query or not location:
            return CollectionResult(
                found_count=0,
                error_code="invalid_input",
                error_summary="Both query and location are required",
                is_transient=False,
            )

        search_query = f"{query} in {location}"
        candidates: list[Candidate] = []
        next_page_token: str | None = None

        while len(candidates) < max_results:
            url = (
                f"{self.API_URL}?key={self._api_key}"
                f"&query={urllib.parse.quote(search_query)}"
                f"&type=establishment"
            )
            if next_page_token:
                url += f"&pagetoken={next_page_token}"

            try:
                req = urllib.request.Request(url, headers={"Accept": "application/json"})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    data = json.loads(resp.read().decode())
            except urllib.error.HTTPError as exc:
                if exc.code == 429:
                    return CollectionResult(
                        found_count=len(candidates),
                        error_code="rate_limited",
                        error_summary="Google Maps API rate limit exceeded",
                        is_transient=True,
                    )
                return CollectionResult(
                    found_count=0,
                    error_code="api_error",
                    error_summary=f"Google Maps API returned {exc.code}",
                    is_transient=exc.code >= 500,
                )
            except (OSError, TimeoutError):
                return CollectionResult(
                    found_count=0,
                    error_code="connection_error",
                    error_summary="Could not connect to Google Maps API",
                    is_transient=True,
                )

            status = data.get("status", "")
            if status == "ZERO_RESULTS":
                break
            if status != "OK":
                return CollectionResult(
                    found_count=0,
                    error_code="api_error",
                    error_summary=f"Google Maps API status: {status}",
                    is_transient=False,
                )

            for place in data.get("results", []):
                if len(candidates) >= max_results:
                    break
                name = place.get("name", "")
                addr = place.get("formatted_address", "")
                website = place.get("website", "")
                domain = _extract_domain_from_url(website)
                phone = place.get("formatted_phone_number", "")
                candidates.append(
                    Candidate(
                        company=name,
                        address=addr,
                        website=website,
                        domain=domain,
                        phone=phone,
                        source="google_maps",
                        source_url=f"https://maps.google.com/?q={urllib.parse.quote(search_query)}",
                        metadata_json=json.dumps(
                            {
                                "query": query,
                                "location": location,
                                "rating": place.get("rating"),
                                "place_id": place.get("place_id", ""),
                            }
                        ),
                    )
                )

            next_page_token = data.get("next_page_token")
            if not next_page_token:
                break

        return CollectionResult(
            candidates=candidates,
            found_count=len(candidates),
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_domain_from_url(url: str) -> str:
    """Extract domain from a URL, stripping www. prefix."""
    if not url:
        return ""
    try:
        from urllib.parse import urlparse

        parsed = urlparse(url)
        host = parsed.hostname or ""
        if host.startswith("www."):
            host = host[4:]
        return host
    except Exception:
        return ""
