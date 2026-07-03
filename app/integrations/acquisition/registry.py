from __future__ import annotations

from app.integrations.acquisition.base import AcquisitionChannel


def acquisition_channels(*, advanced_web_search_enabled: bool = False) -> list[AcquisitionChannel]:
    advanced_status = "enabled_advanced" if advanced_web_search_enabled else "requires_config"
    advanced_href = "#advanced-web-search" if advanced_web_search_enabled else ""
    return [
        AcquisitionChannel(
            channel_key="ai_basic_search",
            channel_name="AI basic search",
            status="enabled_basic",
            tier="basic",
            description=(
                "Let the AI foreign trade operator create overseas buyer search terms, "
                "search links, and organize pasted results."
            ),
            enabled=True,
            href="#ai-basic-search",
        ),
        AcquisitionChannel(
            channel_key="csv_import",
            channel_name="CSV import",
            status="enabled_basic",
            tier="basic",
            description="Import trade fair lists, old customer lists, or company spreadsheets.",
            enabled=True,
            href="/leads/import",
        ),
        AcquisitionChannel(
            channel_key="manual_add",
            channel_name="Manual add",
            status="enabled_basic",
            tier="basic",
            description="Manually add companies you already know.",
            enabled=True,
            href="/leads",
        ),
        AcquisitionChannel(
            channel_key="auto_web_search_api",
            channel_name="Advanced automatic search",
            status=advanced_status,
            tier="advanced",
            description="Automatically call approved search APIs to find candidate companies.",
            requires_api_key=True,
            requires_paid_api=True,
            enabled=advanced_web_search_enabled,
            planned_version="alpha.7",
            risk_level="medium",
            compliance_note="Requires approved paid search API and quota controls.",
            href=advanced_href,
        ),
        AcquisitionChannel(
            channel_key="map_businesses",
            channel_name="Map businesses",
            status="coming_soon",
            tier="advanced",
            description="Find local distributors, wholesalers, stores, and service businesses.",
            requires_api_key=True,
            requires_paid_api=True,
            planned_version="future",
            risk_level="medium",
        ),
        AcquisitionChannel(
            channel_key="b2b_directories",
            channel_name="B2B directories",
            status="planned",
            tier="planned",
            description="Plan for directories such as Europages, Kompass, and Thomasnet.",
            requires_paid_api=True,
            planned_version="future",
            risk_level="high",
            compliance_note="No crawling without explicit legal review.",
        ),
        AcquisitionChannel(
            channel_key="trade_fair_directories",
            channel_name="Trade fair directories",
            status="planned",
            tier="planned",
            description="Find prospects from industry trade fair and exhibitor directories.",
            requires_paid_api=True,
            planned_version="future",
            risk_level="medium",
        ),
        AcquisitionChannel(
            channel_key="customs_data",
            channel_name="Customs data",
            status="planned",
            tier="premium",
            description="Find buyers with import records through compliant licensed data sources.",
            requires_paid_api=True,
            planned_version="future",
            risk_level="high",
            compliance_note="Requires licensed compliant data source.",
        ),
        AcquisitionChannel(
            channel_key="contact_enrichment",
            channel_name="Contact enrichment",
            status="coming_soon",
            tier="advanced",
            description="Enrich reviewed companies with public contact data in a later release.",
            requires_api_key=True,
            requires_paid_api=True,
            planned_version="future",
            risk_level="high",
            compliance_note="No private email or phone enrichment in alpha.6.",
        ),
        AcquisitionChannel(
            channel_key="social_public_profiles",
            channel_name="Social public profiles",
            status="planned",
            tier="planned",
            description="Carefully use public profiles later, without unauthorized scraping.",
            planned_version="future",
            risk_level="high",
            compliance_note="No social scraping in alpha.6.",
        ),
    ]
