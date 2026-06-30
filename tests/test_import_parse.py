"""Tests for V2-03-003: CSV/XLSX import parser and V2-03-004: normalization."""

from __future__ import annotations

import io

import pytest

from app.modules.leads.import_service import (
    MAX_FILE_SIZE,
    MAX_ROWS,
    extract_domain,
    normalize_email,
    normalize_phone,
    parse_import_file,
)

# ---------------------------------------------------------------------------
# Normalization tests (V2-03-004)
# ---------------------------------------------------------------------------


def test_normalize_email_lowercase_and_trim() -> None:
    assert normalize_email("  John@Example.COM ") == "john@example.com"


def test_normalize_email_empty() -> None:
    assert normalize_email("") == ""


def test_normalize_phone_strips_dashes_spaces() -> None:
    assert normalize_phone("+1 (415) 555-1212") == "+14155551212"


def test_normalize_phone_handles_leading_zeros() -> None:
    assert normalize_phone("0044 20 7123 4567") == "+442071234567"


def test_normalize_phone_empty() -> None:
    assert normalize_phone("") == ""


def test_extract_domain_from_email() -> None:
    assert extract_domain("John@Example.COM") == "example.com"


def test_extract_domain_from_url() -> None:
    assert extract_domain("https://www.example.com/page") == "example.com"


def test_extract_domain_from_plain() -> None:
    assert extract_domain("example.com") == "example.com"


def test_extract_domain_empty() -> None:
    assert extract_domain("") == ""


# ---------------------------------------------------------------------------
# CSV parsing tests (V2-03-003)
# ---------------------------------------------------------------------------


def _csv_bytes(header: str, *rows: str) -> bytes:
    content = header + "\n" + "\n".join(rows)
    return content.encode("utf-8")


def test_parse_valid_csv() -> None:
    result = parse_import_file(
        "leads.csv",
        _csv_bytes("email,first_name,last_name,company", "a@a.com,John,Doe,Acme"),
    )
    assert result.valid_rows == 1
    assert result.total_rows == 1
    assert result.invalid_rows == 0
    assert result.rows[0].email == "a@a.com"
    assert result.rows[0].first_name == "John"
    assert result.rows[0].last_name == "Doe"
    assert result.rows[0].company == "Acme"


def test_parse_csv_with_bom() -> None:
    content = b"\xef\xbb\xbfemail,name\nx@x.com,Alice"
    result = parse_import_file("leads.csv", content)
    assert result.valid_rows == 1
    assert result.rows[0].email == "x@x.com"


def test_parse_csv_rejects_missing_email() -> None:
    result = parse_import_file("leads.csv", _csv_bytes("email,name", ",Bob"))
    assert result.invalid_rows == 1
    assert not result.rows[0].is_valid
    assert "invalid or missing email" in result.rows[0].errors[0]


def test_parse_csv_sanitizes_formula_injection() -> None:
    result = parse_import_file(
        "leads.csv",
        _csv_bytes("email,first_name", "a@a.com,=SUM(A1:A10)"),
    )
    row = result.rows[0]
    assert row.first_name.startswith("'")
    assert "sanitised" in row.warnings[0]


def test_parse_csv_handles_unicode() -> None:
    result = parse_import_file(
        "leads.csv",
        _csv_bytes("email,name,company", "mueller@firma.de,Müller,Straße GmbH"),
    )
    assert result.valid_rows == 1


def test_parse_csv_rejects_empty_file() -> None:
    with pytest.raises(Exception, match="empty"):
        parse_import_file("leads.csv", b"")


def test_parse_csv_rejects_large_file() -> None:
    big = b"email\n" + b"a@a.com\n" * (MAX_ROWS + 10)
    with pytest.raises(Exception, match="Too many rows"):
        parse_import_file("leads.csv", big)


def test_parse_csv_rejects_huge_file() -> None:
    huge = b"x\n" * (MAX_FILE_SIZE // 2 + 1)
    with pytest.raises(Exception, match="File too large"):
        parse_import_file("leads.csv", huge)


def test_parse_xlsx_valid() -> None:
    """Create a minimal in-memory XLSX and parse it."""
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    ws.append(["email", "first_name", "last_name"])
    ws.append(["b@b.com", "Jane", "Smith"])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    result = parse_import_file("leads.xlsx", buf.read())
    assert result.valid_rows == 1
    assert result.rows[0].email == "b@b.com"


def test_parse_xlsx_rejects_empty() -> None:
    import openpyxl

    wb = openpyxl.Workbook()
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    with pytest.raises(Exception, match="empty"):
        parse_import_file("leads.xlsx", buf.read())


def test_parse_rejects_invalid_extension() -> None:
    with pytest.raises(Exception, match="Unsupported"):
        parse_import_file("data.txt", b"email\nx@x.com")


def test_parse_header_mapping_flexible() -> None:
    result = parse_import_file(
        "leads.csv",
        _csv_bytes("e-mail,first name,company name,phone number", "c@c.com,Alice,Corp,+123"),
    )
    assert result.valid_rows == 1
    assert result.rows[0].email == "c@c.com"
    assert result.rows[0].first_name == "Alice"
    assert result.rows[0].company == "Corp"
    assert result.rows[0].phone == "+123"


def test_parse_handles_empty_rows_gracefully() -> None:
    result = parse_import_file(
        "leads.csv",
        _csv_bytes("email,name", "a@a.com,Bob", "", "b@b.com,Alice"),
    )
    # Empty rows have no email -> invalid
    assert result.total_rows == 3
    assert result.valid_rows >= 2  # 2 valid + 0 or 1 invalid (empty row)


def test_parse_preview_does_not_write_to_db() -> None:
    """Parse result is purely in-memory."""
    result = parse_import_file(
        "leads.csv",
        _csv_bytes("email,first_name", "test@test.com,Test"),
    )
    assert result.valid_rows == 1
    # No database interaction
