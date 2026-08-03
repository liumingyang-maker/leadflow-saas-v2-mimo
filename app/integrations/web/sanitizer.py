"""Reduce untrusted HTML to bounded visible evidence text."""

from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser

try:
    from bs4 import BeautifulSoup
except ImportError:  # lightweight/test environments retain the safe stdlib path
    BeautifulSoup = None  # type: ignore[assignment,misc]


_REMOVED_TAGS = {
    "script",
    "style",
    "noscript",
    "svg",
    "iframe",
    "form",
    "input",
    "button",
}
_VOID_TAGS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}
_INJECTION_PATTERNS = (
    re.compile(
        r"\bignore\s+(?:all\s+)?(?:previous|prior|system)\s+(?:instructions?|prompts?)\b",
        re.I,
    ),
    re.compile(r"\bsystem\s+prompt\b", re.I),
    re.compile(r"\btool\s+calls?\b", re.I),
    re.compile(r"\breveal\s+(?:the\s+)?(?:secret|password|api\s*key)\b", re.I),
)


@dataclass(frozen=True)
class SanitizedSnapshot:
    title: str
    text: str
    detected_prompt_injection: bool


def _normalise(value: str, *, limit: int = 20_000) -> str:
    return " ".join(value.split())[:limit].strip()


def _has_injection(text: str) -> bool:
    return any(pattern.search(text) for pattern in _INJECTION_PATTERNS)


def sanitize_text(text: str) -> SanitizedSnapshot:
    clean = _normalise(text)
    return SanitizedSnapshot("", clean, _has_injection(clean))


def sanitize_html(html: str) -> SanitizedSnapshot:
    if BeautifulSoup is not None:
        return _sanitize_with_beautiful_soup(html)
    parser = _VisibleTextParser()
    parser.feed(html)
    parser.close()
    title = _normalise(" ".join(parser.title_parts), limit=500)
    text = _normalise(" ".join(parser.text_parts))
    return SanitizedSnapshot(title, text, _has_injection(text))


def _sanitize_with_beautiful_soup(html: str) -> SanitizedSnapshot:
    soup = BeautifulSoup(html, "html.parser")
    for node in soup.find_all(_REMOVED_TAGS):
        node.decompose()
    for node in soup.find_all(True):
        if node.attrs is None:
            continue
        style = re.sub(r"\s+", "", str(node.get("style", "")).lower())
        if (
            node.has_attr("hidden")
            or str(node.get("aria-hidden", "")).lower() == "true"
            or "display:none" in style
            or "visibility:hidden" in style
        ):
            node.decompose()
    title = _normalise(soup.title.get_text(" ", strip=True), limit=500) if soup.title else ""
    text = _normalise(soup.get_text(" ", strip=True))
    return SanitizedSnapshot(title, text, _has_injection(text))


class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._title_depth = 0
        self.text_parts: list[str] = []
        self.title_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if self._skip_depth:
            if tag not in _VOID_TAGS:
                self._skip_depth += 1
            return
        attributes = {name.lower(): value for name, value in attrs}
        style = re.sub(r"\s+", "", (attributes.get("style") or "").lower())
        hidden = (
            tag in _REMOVED_TAGS
            or "hidden" in attributes
            or (attributes.get("aria-hidden") or "").lower() == "true"
            or "display:none" in style
            or "visibility:hidden" in style
        )
        if hidden:
            if tag not in _VOID_TAGS:
                self._skip_depth = 1
        elif tag == "title":
            self._title_depth = 1

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        return

    def handle_endtag(self, tag: str) -> None:
        if self._skip_depth:
            self._skip_depth -= 1
        elif tag.lower() == "title":
            self._title_depth = 0

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if self._title_depth:
            self.title_parts.append(data)
        self.text_parts.append(data)
