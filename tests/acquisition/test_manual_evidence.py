from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.integrations.web.fetcher import FetchResult
from app.modules.acquisition.contracts import CountryEvidenceInput, ManualCompanyFactsInput
from app.modules.acquisition.manual_evidence import (
    ManualEvidenceError,
    build_manual_company_facts,
    contact_url,
    normalise_domain,
    normalize_evidence_text,
    require_supported_text,
)


def _snapshot(
    *, final_url: str, text: str, requested_url: str | None = None
) -> FetchResult:
    return FetchResult(
        requested_url=requested_url or final_url,
        final_url=final_url,
        status_code=200,
        content_type="text/html",
        title="Example",
        text=text,
        content_hash="0" * 64,
        retrieved_at=datetime(2026, 8, 2, tzinfo=UTC),
        redirect_chain=(),
    )


def _input(**overrides: object) -> ManualCompanyFactsInput:
    values: dict[str, object] = {
        "url": "https://submitted.example/products",
        "company_name": "Example Trading",
        "opportunity_country_code": "MX",
        "buyer_type": "distributor",
        "evidence_text": "Industrial pumps for regional distributors.",
        "contact_path": "sales@example.com",
    }
    values.update(overrides)
    return ManualCompanyFactsInput(**values)


def test_evidence_matching_uses_nfkc_casefold_and_collapsed_whitespace() -> None:
    page_text = "Unsere Straße INDUSTRIAL\n  pumps serve México."

    assert normalize_evidence_text("  ＳＴＲＡＳＳＥ  INDUSTRIAL\tpumps ") == (
        "strasse industrial pumps"
    )
    assert require_supported_text(
        claim="  ＳＴＲＡＳＳＥ  INDUSTRIAL\tpumps ", page_text=page_text
    ) == "ＳＴＲＡＳＳＥ INDUSTRIAL pumps"


def test_rejects_evidence_sentence_absent_from_primary_page() -> None:
    with pytest.raises(ManualEvidenceError, match="^Evidence text is not supported by"):
        require_supported_text(
            claim="We distribute solar panels.",
            page_text="We manufacture industrial pumps.",
        )


@pytest.mark.parametrize(
    ("contact", "page_text", "expected"),
    [
        ("Sales@Example.com", "Email sales@example.com for quotes.", "sales@example.com"),
        ("mailto:Sales@Example.com", "Email sales@example.com.", "mailto:sales@example.com"),
        ("+52 (55) 1234-5678", "Call +52 (55) 1234-5678 today.", "+52 (55) 1234-5678"),
    ],
)
def test_accepts_supported_email_mailto_and_bounded_phone(
    contact: str, page_text: str, expected: str
) -> None:
    facts = build_manual_company_facts(
        _input(contact_path=contact),
        primary=_snapshot(
            final_url="https://www.example.com/products",
            text=f"Industrial pumps for regional distributors. {page_text}",
        ),
        contact_snapshot=None,
    )

    assert facts.contact_paths == [expected]


@pytest.mark.parametrize(
    "contact",
    ["other@example.com", "+52 (55) 0000-9999"],
)
def test_rejects_email_or_phone_absent_from_page(contact: str) -> None:
    with pytest.raises(ManualEvidenceError, match="^Contact path is not supported by"):
        build_manual_company_facts(
            _input(contact_path=contact),
            primary=_snapshot(
                final_url="https://example.com/products",
                text=(
                    "Industrial pumps for regional distributors. "
                    "Contact sales@example.com or +52 (55) 1234-5678."
                ),
            ),
            contact_snapshot=None,
        )


@pytest.mark.parametrize(
    "page_text",
    [
        "Contact sales@example.com.evil for quotes.",
        "Contact longer.sales@example.com for quotes.",
    ],
)
def test_email_does_not_match_inside_a_longer_email_token(page_text: str) -> None:
    with pytest.raises(ManualEvidenceError, match="^Contact path is not supported by"):
        build_manual_company_facts(
            _input(contact_path="sales@example.com"),
            primary=_snapshot(
                final_url="https://example.com/products",
                text=f"Industrial pumps for regional distributors. {page_text}",
            ),
            contact_snapshot=None,
        )


def test_email_matches_at_normal_punctuation_boundaries() -> None:
    facts = build_manual_company_facts(
        _input(contact_path="sales@example.com"),
        primary=_snapshot(
            final_url="https://example.com/products",
            text="Industrial pumps for regional distributors. Email: sales@example.com, today.",
        ),
        contact_snapshot=None,
    )

    assert facts.contact_paths == ["sales@example.com"]


@pytest.mark.parametrize("contact", [".sales@example.com", "sales..team@example.com"])
def test_rejects_malformed_email_even_when_page_contains_it(contact: str) -> None:
    with pytest.raises(
        ManualEvidenceError, match="^Contact path must be a supported email or phone$"
    ):
        build_manual_company_facts(
            _input(contact_path=contact),
            primary=_snapshot(
                final_url="https://example.com/products",
                text=f"Industrial pumps for regional distributors. Contact {contact}.",
            ),
            contact_snapshot=None,
        )


@pytest.mark.parametrize(
    "contact",
    ["123-456", "+12 345 678 901 234 567 890", "1234567 ext 9"],
)
def test_rejects_phone_outside_allowed_boundaries(contact: str) -> None:
    with pytest.raises(
        ManualEvidenceError, match="^Contact path must be a supported email or phone$"
    ):
        build_manual_company_facts(
            _input(contact_path=contact),
            primary=_snapshot(
                final_url="https://example.com/products",
                text=f"Industrial pumps for regional distributors. Call {contact}.",
            ),
            contact_snapshot=None,
        )


def test_accepts_phone_at_exact_minimum_boundary() -> None:
    facts = build_manual_company_facts(
        _input(contact_path="1234567"),
        primary=_snapshot(
            final_url="https://example.com/products",
            text="Industrial pumps for regional distributors. Call 1234567.",
        ),
        contact_snapshot=None,
    )

    assert facts.contact_paths == ["1234567"]


def test_phone_does_not_match_inside_a_longer_digit_token() -> None:
    with pytest.raises(ManualEvidenceError, match="^Contact path is not supported by"):
        build_manual_company_facts(
            _input(contact_path="1234567"),
            primary=_snapshot(
                final_url="https://example.com/products",
                text="Industrial pumps for regional distributors. Reference 012345678.",
            ),
            contact_snapshot=None,
        )


@pytest.mark.parametrize(
    ("contact", "page_contact"),
    [
        ("1234567", "1234567-890"),
        ("123-4567", "123-4567-8900"),
        ("1234567", "1234567 890"),
        ("1234567", "1234567(890)"),
        ("1234567", "1234567.890"),
        ("1234567", "890-1234567"),
        ("1234567", "890 1234567"),
        ("1234567", "(890)1234567"),
        ("1234567", "890.1234567"),
    ],
)
def test_phone_does_not_match_with_digits_joined_through_phone_separators(
    contact: str, page_contact: str
) -> None:
    with pytest.raises(ManualEvidenceError, match="^Contact path is not supported by"):
        build_manual_company_facts(
            _input(contact_path=contact),
            primary=_snapshot(
                final_url="https://example.com/products",
                text=(
                    "Industrial pumps for regional distributors. "
                    f"Call {page_contact}."
                ),
            ),
            contact_snapshot=None,
        )


@pytest.mark.parametrize(
    "page_contact",
    ["(1234567), now", "1234567.", "1234567, now", "1234567 ext 890"],
)
def test_phone_accepts_standalone_text_and_punctuation_boundaries(
    page_contact: str,
) -> None:
    facts = build_manual_company_facts(
        _input(contact_path="1234567"),
        primary=_snapshot(
            final_url="https://example.com/products",
            text=(
                "Industrial pumps for regional distributors. "
                f"Call {page_contact}"
            ),
        ),
        contact_snapshot=None,
    )

    assert facts.contact_paths == ["1234567"]


@pytest.mark.parametrize(
    "page_text",
    [
        "Call 1234567. 890 employees.",
        "Reference 890. 1234567",
        "Call 1234567.\n890 employees.",
    ],
)
def test_phone_accepts_period_whitespace_sentence_boundaries(page_text: str) -> None:
    facts = build_manual_company_facts(
        _input(contact_path="1234567"),
        primary=_snapshot(
            final_url="https://example.com/products",
            text=f"Industrial pumps for regional distributors. {page_text}",
        ),
        contact_snapshot=None,
    )

    assert facts.contact_paths == ["1234567"]


def test_formatted_phone_matches_at_non_digit_boundaries() -> None:
    facts = build_manual_company_facts(
        _input(contact_path="+52 (55) 1234-5678"),
        primary=_snapshot(
            final_url="https://example.com/products",
            text=(
                "Industrial pumps for regional distributors. "
                "Call: +52 (55) 1234-5678, weekdays."
            ),
        ),
        contact_snapshot=None,
    )

    assert facts.contact_paths == ["+52 (55) 1234-5678"]


@pytest.mark.parametrize(
    ("contact", "snapshot_text", "expected"),
    [
        ("Support@Example.com", "Email support@example.com.", "support@example.com"),
        ("+52 (55) 7654-3210", "Call +52 (55) 7654-3210.", "+52 (55) 7654-3210"),
    ],
)
def test_accepts_contact_found_only_in_contact_snapshot(
    contact: str, snapshot_text: str, expected: str
) -> None:
    facts = build_manual_company_facts(
        _input(contact_path=contact),
        primary=_snapshot(
            final_url="https://example.com/products",
            text="Industrial pumps for regional distributors.",
        ),
        contact_snapshot=_snapshot(
            final_url="https://example.com/contact",
            text=snapshot_text,
        ),
    )

    assert facts.contact_paths == [expected]


def test_accepts_same_domain_contact_url_and_same_domain_redirect_result() -> None:
    facts = build_manual_company_facts(
        _input(contact_path="https://www.example.com/contact"),
        primary=_snapshot(
            final_url="https://example.com/products",
            text="Industrial pumps for regional distributors.",
        ),
        contact_snapshot=_snapshot(
            requested_url="https://www.example.com/contact",
            final_url="https://example.com/en/contact-us",
            text="Contact sales@example.com.",
        ),
    )

    assert facts.canonical_domain == "example.com"
    assert facts.contact_paths == ["https://www.example.com/contact"]


def test_accepts_unicode_contact_domain_equivalent_to_primary_punycode() -> None:
    submitted_url = "https://bücher.example/contact"
    facts = build_manual_company_facts(
        _input(contact_path=submitted_url),
        primary=_snapshot(
            final_url="https://xn--bcher-kva.example/products",
            text="Industrial pumps for regional distributors.",
        ),
        contact_snapshot=_snapshot(
            requested_url=submitted_url,
            final_url="https://xn--bcher-kva.example/contact-us",
            text="Contact us.",
        ),
    )

    assert facts.canonical_domain == "xn--bcher-kva.example"
    assert facts.contact_paths == [submitted_url]


def test_rejects_invalid_idna_domain_with_safe_error() -> None:
    invalid_domain = "\ud800.example"

    with pytest.raises(ManualEvidenceError) as exc_info:
        normalise_domain(f"https://{invalid_domain}/contact")

    assert str(exc_info.value) == "URL domain is malformed"
    assert invalid_domain not in str(exc_info.value)


def test_rejects_same_domain_contact_url_without_snapshot() -> None:
    with pytest.raises(
        ManualEvidenceError, match="^Contact URL requires a fetched contact page$"
    ):
        build_manual_company_facts(
            _input(contact_path="https://example.com/contact"),
            primary=_snapshot(
                final_url="https://example.com/products",
                text="Industrial pumps for regional distributors.",
            ),
            contact_snapshot=None,
        )


def test_rejects_contact_snapshot_requested_for_a_different_url() -> None:
    with pytest.raises(
        ManualEvidenceError,
        match="^Contact snapshot does not match the submitted URL$",
    ):
        build_manual_company_facts(
            _input(contact_path="https://example.com/contact"),
            primary=_snapshot(
                final_url="https://example.com/products",
                text="Industrial pumps for regional distributors.",
            ),
            contact_snapshot=_snapshot(
                requested_url="https://example.com/about",
                final_url="https://example.com/contact-us",
                text="Contact us.",
            ),
        )


def test_rejects_cross_domain_contact_url_without_external_calls() -> None:
    with pytest.raises(ManualEvidenceError, match="^Contact URL must use the company domain$"):
        build_manual_company_facts(
            _input(contact_path="https://attacker.example/contact"),
            primary=_snapshot(
                final_url="https://example.com/products",
                text="Industrial pumps for regional distributors.",
            ),
            contact_snapshot=None,
        )


def test_rejects_malformed_http_contact_with_safe_error() -> None:
    malformed = "http://[invalid"

    with pytest.raises(ManualEvidenceError) as exc_info:
        build_manual_company_facts(
            _input(contact_path=malformed),
            primary=_snapshot(
                final_url="https://example.com/products",
                text="Industrial pumps for regional distributors.",
            ),
            contact_snapshot=None,
        )

    assert str(exc_info.value) == "URL is malformed"
    assert malformed not in str(exc_info.value)


@pytest.mark.parametrize("parse", [contact_url, normalise_domain])
def test_public_url_helpers_reject_malformed_url_safely(
    parse: Callable[[str], str | None],
) -> None:
    malformed = "http://[invalid"

    with pytest.raises(ManualEvidenceError) as exc_info:
        parse(malformed)

    assert str(exc_info.value) == "URL is malformed"
    assert malformed not in str(exc_info.value)


def test_rejects_malformed_primary_final_url_safely() -> None:
    malformed = "http://[invalid"

    with pytest.raises(ManualEvidenceError) as exc_info:
        build_manual_company_facts(
            _input(),
            primary=_snapshot(
                final_url=malformed,
                text=(
                    "Industrial pumps for regional distributors. "
                    "Contact sales@example.com."
                ),
            ),
            contact_snapshot=None,
        )

    assert str(exc_info.value) == "URL is malformed"
    assert malformed not in str(exc_info.value)


def test_rejects_contact_snapshot_redirected_to_another_domain() -> None:
    with pytest.raises(
        ManualEvidenceError, match="^Contact URL redirected off the company domain$"
    ):
        build_manual_company_facts(
            _input(contact_path="https://example.com/contact"),
            primary=_snapshot(
                final_url="https://example.com/products",
                text="Industrial pumps for regional distributors.",
            ),
            contact_snapshot=_snapshot(
                requested_url="https://example.com/contact",
                final_url="https://attacker.example/landing",
                text="Contact us.",
            ),
        )


def test_claim_source_is_primary_final_url_not_submitted_or_contact_url() -> None:
    primary = _snapshot(
        final_url="https://www.real-company.example/catalogue",
        text="Industrial pumps for regional distributors.",
    )
    facts = build_manual_company_facts(
        _input(
            url="https://submitted.example/form",
            contact_path="https://real-company.example/contact",
        ),
        primary=primary,
        contact_snapshot=_snapshot(
            requested_url="https://real-company.example/contact",
            final_url="https://www.real-company.example/contact-us", text="Contact us."
        ),
    )

    assert facts.canonical_domain == "real-company.example"
    assert facts.observed_claims[0].claim_id == "manual-product-evidence"
    assert str(facts.observed_claims[0].source_url) == primary.final_url
    assert facts.unknowns == ["hq_country_code"]


def test_manual_company_contract_normalizes_country_and_buyer_type() -> None:
    value = _input(opportunity_country_code=" mx ", buyer_type=" Distributor ")

    assert value.opportunity_country_code == "MX"
    assert value.buyer_type == "distributor"


def test_manual_company_contract_strips_company_name() -> None:
    value = _input(company_name=" \tExample Trading\n")

    assert value.company_name == "Example Trading"


def test_manual_company_contract_rejects_301_character_company_name() -> None:
    with pytest.raises(ValidationError):
        _input(company_name="A" * 301)


def test_manual_company_contract_rejects_long_raw_name_even_when_clean_is_short() -> None:
    with pytest.raises(ValidationError):
        _input(company_name=f"{' ' * 500}A{' ' * 500}")


def test_manual_company_contract_accepts_raw_name_at_limit_and_strips_it() -> None:
    raw_name = f" {'A' * 298} "

    value = _input(company_name=raw_name)

    assert len(raw_name) == 300
    assert value.company_name == "A" * 298


@pytest.mark.parametrize("company_name", ["   ", "\t", "\n", " \t\r\n "])
def test_manual_company_contract_rejects_blank_company_name(company_name: str) -> None:
    with pytest.raises(ValidationError):
        _input(company_name=company_name)


@pytest.mark.parametrize(
    "country",
    [None, 123, ["M", "X"], {"country": "MX"}, "ß", "ſi", "ıd"],
)
def test_manual_company_contract_rejects_non_ascii_country(country: object) -> None:
    with pytest.raises(ValidationError):
        _input(opportunity_country_code=country)


@pytest.mark.parametrize(
    "overrides",
    [
        {"extra_field": "nope"},
        {"opportunity_country_code": "ZZ"},
        {"buyer_type": "retailer"},
    ],
)
def test_manual_company_contract_rejects_extra_country_and_buyer(
    overrides: dict[str, str],
) -> None:
    with pytest.raises(ValidationError):
        _input(**overrides)


def test_country_evidence_contract_normalizes_country() -> None:
    value = CountryEvidenceInput(
        country_code=" mx ",
        source_url="https://registry.example/company/1",
        evidence_text="Registered in Mexico.",
        reason_code="registry_record",
    )

    assert value.country_code == "MX"


@pytest.mark.parametrize(
    "country",
    [None, 123, ["M", "X"], {"country": "MX"}, "ß", "ſi", "ıd"],
)
def test_country_evidence_contract_rejects_non_ascii_country(country: object) -> None:
    with pytest.raises(ValidationError):
        CountryEvidenceInput(
            country_code=country,
            source_url="https://registry.example/company/1",
            evidence_text="Registered in Mexico.",
            reason_code="registry_record",
        )


@pytest.mark.parametrize(
    "overrides",
    [
        {"country_code": "ZZ"},
        {"reason_code": "guessed"},
        {"extra_field": "nope"},
    ],
)
def test_country_evidence_contract_rejects_invalid_values(
    overrides: dict[str, str],
) -> None:
    values = {
        "country_code": "MX",
        "source_url": "https://registry.example/company/1",
        "evidence_text": "Registered in Mexico.",
        "reason_code": "registry_record",
    }
    values.update(overrides)
    with pytest.raises(ValidationError):
        CountryEvidenceInput(**values)
