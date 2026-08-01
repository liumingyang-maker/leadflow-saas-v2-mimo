from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

try:
    import pycountry
except ImportError:  # pragma: no cover - deployment installs the locked dependency
    pycountry = None


DEFAULT_LANGUAGES: dict[str, list[str]] = {
    "MX": ["es"],
    "PE": ["es"],
    "CO": ["es"],
    "BR": ["pt"],
    "US": ["en"],
    "GB": ["en"],
    "FR": ["fr"],
    "DE": ["de"],
}

ALLOWED_BUYER_TYPES = {
    "importer",
    "distributor",
    "wholesaler",
    "assembler",
    "repair_network",
}
ALLOWED_CHANNELS = {"mimo_web", "manual_url"}

_ISO_ALPHA2_CODES = frozenset(
    """
    AD AE AF AG AI AL AM AO AQ AR AS AT AU AW AX AZ BA BB BD BE BF BG BH BI BJ BL BM
    BN BO BQ BR BS BT BV BW BY BZ CA CC CD CF CG CH CI CK CL CM CN CO CR CU CV CW CX CY
    CZ DE DJ DK DM DO DZ EC EE EG EH ER ES ET FI FJ FK FM FO FR GA GB GD GE GF GG GH GI
    GL GM GN GP GQ GR GS GT GU GW GY HK HM HN HR HT HU ID IE IL IM IN IO IQ IR IS IT JE
    JM JO JP KE KG KH KI KM KN KP KR KW KY KZ LA LB LC LI LK LR LS LT LU LV LY MA MC MD
    ME MF MG MH MK ML MM MN MO MP MQ MR MS MT MU MV MW MX MY MZ NA NC NE NF NG NI NL NO
    NP NR NU NZ OM PA PE PF PG PH PK PL PM PN PR PS PT PW PY QA RE RO RS RU RW SA SB SC
    SD SE SG SH SI SJ SK SL SM SN SO SR SS ST SV SX SY SZ TC TD TF TG TH TJ TK TL TM TN
    TO TR TT TV TW TZ UA UG UM US UY UZ VA VC VE VG VI VN VU WF WS YE YT ZA ZM ZW
    """.split()
)


def _is_country_code(value: str) -> bool:
    if pycountry is not None:
        return pycountry.countries.get(alpha_2=value) is not None
    return value in _ISO_ALPHA2_CODES


class MissionCreateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_snapshot_id: str = Field(min_length=1, max_length=64)
    country_codes: list[str] = Field(min_length=1, max_length=20)
    buyer_types: list[str] = Field(min_length=1, max_length=10)
    industries: list[str] = Field(default_factory=list, max_length=20)
    company_sizes: list[str] = Field(default_factory=list, max_length=10)
    include_terms: list[str] = Field(default_factory=list, max_length=30)
    exclude_terms: list[str] = Field(default_factory=list, max_length=30)
    allowed_channels: list[str] = Field(default_factory=lambda: ["mimo_web", "manual_url"])
    max_candidates: int = Field(default=30, ge=1, le=100)
    max_verify: int = Field(default=10, ge=1, le=30)
    max_search_actions: int = Field(default=5, ge=1, le=20)
    max_seconds: int = Field(default=900, ge=30, le=1800)
    languages: dict[str, list[str]] = Field(default_factory=dict)

    @field_validator("country_codes")
    @classmethod
    def validate_countries(cls, values: list[str]) -> list[str]:
        normalized = list(dict.fromkeys(value.strip().upper() for value in values))
        invalid = [value for value in normalized if not _is_country_code(value)]
        if invalid:
            raise ValueError(f"invalid ISO alpha-2 country codes: {invalid}")
        return normalized

    @field_validator("buyer_types")
    @classmethod
    def validate_buyer_types(cls, values: list[str]) -> list[str]:
        normalized = list(dict.fromkeys(value.strip().lower() for value in values))
        invalid = [value for value in normalized if value not in ALLOWED_BUYER_TYPES]
        if invalid:
            raise ValueError(f"unsupported buyer types: {invalid}")
        return normalized

    @field_validator("allowed_channels")
    @classmethod
    def validate_channels(cls, values: list[str]) -> list[str]:
        normalized = list(dict.fromkeys(value.strip().lower() for value in values))
        invalid = [value for value in normalized if value not in ALLOWED_CHANNELS]
        if invalid:
            raise ValueError(f"unsupported acquisition channels: {invalid}")
        return normalized

    @model_validator(mode="after")
    def apply_language_defaults(self) -> MissionCreateInput:
        unknown_keys = set(self.languages) - set(self.country_codes)
        if unknown_keys:
            raise ValueError(f"languages contain countries outside mission: {unknown_keys}")
        normalized_languages: dict[str, list[str]] = {}
        for country in self.country_codes:
            values = self.languages.get(country, DEFAULT_LANGUAGES.get(country, ["en"]))
            clean = list(dict.fromkeys(value.strip().lower() for value in values if value.strip()))
            if not clean:
                raise ValueError(f"at least one language is required for {country}")
            normalized_languages[country] = clean
        self.languages = normalized_languages
        return self


DecisionAction = Literal["accept", "reject", "needs_evidence"]
DecisionReason = Literal[
    "",
    "country_unknown",
    "country_conflicting",
    "wrong_buyer_type",
    "excluded_business",
    "missing_identity",
    "missing_product_evidence",
    "missing_contact_path",
    "duplicate",
    "other",
]


class CandidateDecisionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: DecisionAction
    reason_code: DecisionReason = ""
    note: str = Field(default="", max_length=1000)

    @model_validator(mode="after")
    def validate_reason(self) -> CandidateDecisionInput:
        if self.action == "reject" and not self.reason_code:
            raise ValueError("reason_code is required for reject")
        if self.action == "accept" and self.reason_code in {
            "country_unknown",
            "country_conflicting",
        }:
            raise ValueError("country evidence must be resolved before accept")
        return self
