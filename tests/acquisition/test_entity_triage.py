from __future__ import annotations


def test_article_and_directory_paths_are_high_confidence_non_company_sources():
    from app.modules.acquisition.entity_triage import classify_discovery_entity

    assert (
        classify_discovery_entity(
            url="https://industry-news.example/noticias/honda-production-record",
            title="Honda reaches production record",
            excerpt="Industry news article",
        )
        == "media_or_article"
    )
    assert (
        classify_discovery_entity(
            url="https://directory.example/listing/motocorp",
            title="Motocorp profile",
            excerpt="Business directory entry",
        )
        == "directory_or_marketplace"
    )


def test_company_homepage_remains_eligible_for_verification():
    from app.modules.acquisition.entity_triage import classify_discovery_entity

    assert (
        classify_discovery_entity(
            url="https://motocorp.pe/",
            title="Motocorp Perú",
            excerpt="Motorcycle spare parts distributor",
        )
        == "company"
    )
