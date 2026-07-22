"""CSV/XLSX import parser with safety guards and column mapping."""

from __future__ import annotations

import csv
import io
import re
from collections.abc import Callable
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB
MAX_ROWS = 5000
MIN_ROWS = 1
EXPECTED_HEADERS = {
    "email",
    "first_name",
    "last_name",
    "company",
    "title",
    "phone",
    "website",
    "industry",
}

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ImportRow:
    """A single parsed row with normalized fields."""

    row_index: int
    email: str = ""
    first_name: str = ""
    last_name: str = ""
    company: str = ""
    title: str = ""
    phone: str = ""
    website: str = ""
    industry: str = ""
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    is_valid: bool = True


@dataclass(frozen=True)
class ImportResult:
    """Result of parsing an import file."""

    filename: str
    total_rows: int
    valid_rows: int
    invalid_rows: int
    rows: list[ImportRow]
    detected_headers: list[str]
    unmapped_columns: list[str]
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Normalisation helpers (also used by V2-03-004)
# ---------------------------------------------------------------------------


def normalize_email(email: str) -> str:
    """Lowercase, strip whitespace."""
    return (email or "").strip().lower()


def normalize_phone(phone: str) -> str:
    """Remove non-digit characters except leading +."""
    cleaned = re.sub(r"[^\d+]", "", (phone or "").strip())
    if cleaned.startswith("+"):
        return cleaned
    if cleaned.startswith("00"):
        return "+" + cleaned[2:]
    return cleaned


def extract_domain(email_or_url: str) -> str:
    """Extract domain from email address or URL."""
    val = (email_or_url or "").strip().lower()
    if "@" in val:
        val = val.split("@", 1)[1]
    val = re.sub(r"^https?://(www\.)?", "", val)
    val = val.split("/")[0].split("?")[0]
    return val


def strip_name(name: str) -> str:
    return (name or "").strip()[:120]


def strip_long(value: str, max_len: int = 500) -> str:
    return (value or "").strip()[:max_len]


# ---------------------------------------------------------------------------
# Formula injection prevention
# ---------------------------------------------------------------------------

_INJECTION_PREFIXES = ("=", "+", "-", "@", "\t", "\r", "\n")

_FIELD_VALIDATORS: dict[str, Callable[[str], str | None]] = {
    "email": lambda v: normalize_email(v) if "@" in (v or "") else None,
    "first_name": strip_name,
    "last_name": strip_name,
    "company": strip_name,
    "title": strip_name,
    "phone": normalize_phone,
    "website": strip_long,
    "industry": strip_name,
}


def _sanitize(value: str) -> str:
    """Strip formula injection prefixes from a cell value."""
    if value and value.startswith(_INJECTION_PREFIXES):
        return "'" + value
    return value


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def parse_import_file(
    filename: str,
    content: bytes,
    max_file_size: int = MAX_FILE_SIZE,
    max_rows: int = MAX_ROWS,
) -> ImportResult:
    """Parse a CSV or XLSX file into an ``ImportResult``.

    * File size is checked before parsing.
    * Row count is capped to ``max_rows``.
    * Formula injection is sanitised.
    * Unknown columns are reported but not rejected.
    """
    errors: list[str] = []
    filename_lower = (filename or "").lower()

    # Size check
    if len(content) > max_file_size:
        raise ImportError(f"File too large ({len(content)} bytes); max {max_file_size} bytes")

    # Detect format and parse
    if filename_lower.endswith(".csv"):
        return _parse_csv(filename, content, max_rows, errors)
    if filename_lower.endswith(".xlsx"):
        return _parse_xlsx(filename, content, max_rows, errors)

    raise ImportError(f"Unsupported file format: {filename!r} (only .csv and .xlsx)")


def _build_rows(
    filename: str,
    raw_headers: list[str],
    raw_rows: list[list[str]],
    errors: list[str],
) -> ImportResult:
    """Convert raw CSV/xlsx rows into structured ImportRows."""
    headers = [h.strip().lower() for h in raw_headers]
    mapped = _map_headers(headers)

    parsed: list[ImportRow] = []
    valid_count = 0
    invalid_count = 0

    for idx, raw in enumerate(raw_rows):
        row_errors: list[str] = []
        row_warnings: list[str] = []
        values: dict[str, str] = {}

        for col_idx, (_header_name, field_key) in enumerate(mapped):
            raw_value = (
                (raw[col_idx] if col_idx < len(raw) else "").strip() if col_idx < len(raw) else ""
            )
            # Check for injection BEFORE sanitising
            if raw_value and raw_value.startswith(_INJECTION_PREFIXES):
                row_warnings.append(f"Row {idx + 2}: {field_key} sanitised for injection")
            safe_value = _sanitize(raw_value)
            values[field_key] = safe_value

        # Validate required fields
        email = normalize_email(values.get("email", ""))
        if not email or "@" not in email:
            row_errors.append(f"Row {idx + 2}: invalid or missing email")

        row = ImportRow(
            row_index=idx,
            email=email,
            first_name=strip_name(values.get("first_name", "")),
            last_name=strip_name(values.get("last_name", "")),
            company=strip_name(values.get("company", "")),
            title=strip_name(values.get("title", "")),
            phone=normalize_phone(values.get("phone", "")),
            website=strip_long(values.get("website", "")),
            industry=strip_name(values.get("industry", "")),
            errors=row_errors,
            warnings=row_warnings,
            is_valid=not row_errors,
        )
        if row.is_valid:
            valid_count += 1
        else:
            invalid_count += 1
        parsed.append(row)

    unmapped = [h for h in headers if h not in {v[0] for v in mapped}]

    return ImportResult(
        filename=filename,
        total_rows=len(parsed),
        valid_rows=valid_count,
        invalid_rows=invalid_count,
        rows=parsed,
        detected_headers=headers,
        unmapped_columns=unmapped,
        errors=errors,
    )


_HEADER_MAP: dict[str, str] = {
    "email": "email",
    "e-mail": "email",
    "first_name": "first_name",
    "first name": "first_name",
    "firstname": "first_name",
    "first": "first_name",
    "given name": "first_name",
    "last_name": "last_name",
    "last name": "last_name",
    "lastname": "last_name",
    "last": "last_name",
    "surname": "last_name",
    "company": "company",
    "company name": "company",
    "company_name": "company",
    "organization": "company",
    "organisation": "company",
    "title": "title",
    "job title": "title",
    "position": "title",
    "phone": "phone",
    "telephone": "phone",
    "mobile": "phone",
    "phone number": "phone",
    "phone_number": "phone",
    "website": "website",
    "web": "website",
    "url": "website",
    "industry": "industry",
}


def _map_headers(headers: list[str]) -> list[tuple[str, str]]:
    """Map import headers to canonical field names."""
    result: list[tuple[str, str]] = []
    for h in headers:
        key = _HEADER_MAP.get(h, "")
        if key:
            result.append((h, key))
    return result


def _parse_csv(filename: str, content: bytes, max_rows: int, errors: list[str]) -> ImportResult:
    """Parse CSV content."""
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("latin-1")

    reader = csv.reader(io.StringIO(text))
    raw_rows = list(reader)

    if not raw_rows:
        raise ImportError("CSV file is empty")

    if len(raw_rows) - 1 > max_rows:
        raise ImportError(f"Too many rows ({len(raw_rows) - 1}); max {max_rows}")

    headers = raw_rows[0]
    # Strip BOM from first header if present
    if headers and headers[0].startswith("\ufeff"):
        headers[0] = headers[0].lstrip("\ufeff")
    data_rows = raw_rows[1:]

    return _build_rows(filename, headers, data_rows, errors)


def _parse_xlsx(filename: str, content: bytes, max_rows: int, errors: list[str]) -> ImportResult:
    """Parse XLSX content using openpyxl."""
    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    ws = wb.active
    if ws is None:
        raise ImportError("XLSX file has no active sheet")

    raw_rows: list[list[str]] = []
    for row in ws.iter_rows(values_only=True):
        raw_rows.append([(str(v) if v is not None else "") for v in row])

    wb.close()

    if not raw_rows:
        raise ImportError("XLSX file is empty")

    if len(raw_rows) - 1 > max_rows:
        raise ImportError(f"Too many rows ({len(raw_rows) - 1}); max {max_rows}")

    headers = raw_rows[0]
    data_rows = raw_rows[1:]

    return _build_rows(filename, headers, data_rows, errors)


class ImportError(ValueError):
    """Raised when the import file cannot be processed."""
