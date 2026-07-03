from __future__ import annotations

from dataclasses import dataclass

CHANNEL_STATUSES = (
    "enabled_basic",
    "enabled_advanced",
    "requires_config",
    "coming_soon",
    "planned",
    "disabled",
)
CHANNEL_TIERS = ("basic", "advanced", "premium", "planned")


@dataclass(frozen=True)
class AcquisitionChannel:
    channel_key: str
    channel_name: str
    status: str
    tier: str
    description: str
    requires_api_key: bool = False
    requires_paid_api: bool = False
    enabled: bool = False
    planned_version: str = ""
    risk_level: str = "low"
    compliance_note: str = ""
    href: str = ""
