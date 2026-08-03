"""Strict provider-independent contracts for acquisition AI output."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Protocol

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

if TYPE_CHECKING:
    from app.integrations.web.fetcher import FetchResult


class CountryResearchPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    country_code: str = Field(pattern=r"^[A-Z]{2}$")
    languages: list[str] = Field(min_length=1, max_length=5)
    queries: list[str] = Field(min_length=1, max_length=20)
    include_terms: list[str] = Field(default_factory=list, max_length=30)
    exclude_terms: list[str] = Field(default_factory=list, max_length=30)


class MissionPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_version: str = Field(pattern=r"^mission-plan-v1$")
    country_runs: list[CountryResearchPlan] = Field(min_length=1, max_length=20)


class SearchHit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: HttpUrl
    title: str = Field(max_length=500)
    excerpt: str = Field(max_length=2000)
    query: str = Field(max_length=500)


class SearchResults(BaseModel):
    model_config = ConfigDict(extra="forbid")

    search_hits: list[SearchHit] = Field(default_factory=list, max_length=100)


class CompetitorEvidenceProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_url: HttpUrl
    excerpt: str = Field(min_length=1, max_length=1000)


class CompetitorSuggestionProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company_name: str = Field(min_length=1, max_length=200)
    official_url: HttpUrl
    reason_codes: list[Annotated[str, Field(min_length=1, max_length=80)]] = Field(
        min_length=1,
        max_length=10,
    )
    evidence: list[CompetitorEvidenceProposal] = Field(min_length=1, max_length=2)


class CompetitorSuggestionResults(BaseModel):
    model_config = ConfigDict(extra="forbid")

    suggestions: list[CompetitorSuggestionProposal] = Field(default_factory=list, max_length=10)


class EvidenceClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_id: str = Field(min_length=1, max_length=100)
    text: str = Field(min_length=1, max_length=1000)
    source_url: HttpUrl


class ExtractedCompanyFacts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company_name: str = Field(min_length=1, max_length=300)
    canonical_domain: str = Field(min_length=1, max_length=253)
    hq_country_code: str = Field(default="", pattern=r"^$|^[A-Z]{2}$")
    opportunity_country_code: str = Field(default="", pattern=r"^$|^[A-Z]{2}$")
    buyer_type: str = Field(default="", max_length=120)
    product_terms: list[str] = Field(default_factory=list, max_length=30)
    contact_paths: list[str] = Field(default_factory=list, max_length=20)
    observed_claims: list[EvidenceClaim] = Field(default_factory=list, max_length=50)
    inferences: list[str] = Field(default_factory=list, max_length=20)
    unknowns: list[str] = Field(default_factory=list, max_length=20)


class CompanyExtractor(Protocol):
    def extract(self, snapshot: FetchResult) -> ExtractedCompanyFacts:
        raise NotImplementedError
