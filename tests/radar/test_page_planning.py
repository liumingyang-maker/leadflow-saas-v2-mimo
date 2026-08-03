from __future__ import annotations


def _resolver(_host: str) -> list[str]:
    return ["93.184.216.34"]


def test_page_planner_keeps_home_configured_and_same_domain_observed_pages() -> None:
    from app.modules.radar.snapshots import plan_radar_pages

    planned = plan_radar_pages(
        official_url="https://rival.example/",
        canonical_domain="rival.example",
        tracking_config_json=(
            '{"seed_pages":[{"url":"https://rival.example/products","page_kind":"product"}]}'
        ),
        observed_links=(
            {"url": "/dealers", "anchor_text": "Distribuidores oficiales"},
            {"url": "https://foreign.example/partners", "anchor_text": "Partner"},
            {"url": "/news", "anchor_text": "News"},
        ),
        page_limit=10,
        resolver=_resolver,
    )

    assert [(item.canonical_url, item.page_kind) for item in planned] == [
        ("https://rival.example/", "home"),
        ("https://rival.example/products", "product"),
        ("https://rival.example/dealers", "dealers"),
        ("https://rival.example/news", "other"),
    ]


def test_page_planner_bounds_pages_and_rejects_invented_configured_urls() -> None:
    import pytest

    from app.modules.radar.snapshots import RadarSnapshotError, plan_radar_pages

    with pytest.raises(RadarSnapshotError, match="same competitor domain"):
        plan_radar_pages(
            official_url="https://rival.example/",
            canonical_domain="rival.example",
            tracking_config_json=(
                '{"seed_pages":[{"url":"https://foreign.example/dealers","page_kind":"dealers"}]}'
            ),
            observed_links=(),
            page_limit=10,
            resolver=_resolver,
        )
