from __future__ import annotations

SEARCH_ENGINES = (
    ("Google", "https://www.google.com/search?q={query}"),
    ("Bing", "https://www.bing.com/search?q={query}"),
)


def build_search_links(
    *, keywords: list[str], country: str = "", max_links: int = 8
) -> list[dict[str, str]]:
    links: list[dict[str, str]] = []
    for keyword in keywords[: max(1, max_links // 2)]:
        query = _search_query(keyword, country=country)
        encoded = _encode_query(query)
        for engine, template in SEARCH_ENGINES:
            links.append(
                {
                    "engine": engine,
                    "query": query,
                    "url": template.format(query=encoded),
                }
            )
            if len(links) >= max_links:
                return links
    return links


def _search_query(keyword: str, *, country: str) -> str:
    clean = (keyword or "").strip()
    if country:
        return f"{clean} {country}".strip()
    return clean


def _encode_query(value: str) -> str:
    allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_."
    output: list[str] = []
    for char in value.strip():
        if char == " ":
            output.append("+")
        elif char in allowed:
            output.append(char)
        else:
            for byte in char.encode("utf-8"):
                output.append(f"%{byte:02X}")
    return "".join(output)
