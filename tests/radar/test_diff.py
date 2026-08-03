from __future__ import annotations


def test_snapshot_diff_is_byte_identical_and_ignores_fact_order() -> None:
    from app.modules.radar.diff import diff_snapshots

    previous = '{"facts":[{"key":"product","value":"engine"},{"key":"market","value":"MX"}]}'
    current = '{"facts":[{"key":"market","value":"BR"},{"key":"product","value":"engine"}]}'

    first = diff_snapshots(previous, current, detector_version="radar-diff-v1")
    second = diff_snapshots(previous, current, detector_version="radar-diff-v1")

    assert first == second
    assert b'"changed"' in first
    assert b'"market"' in first


def test_baseline_drift_requires_three_comparable_pages_and_detects_parser_change() -> None:
    from app.modules.radar.diff import detect_baseline_drift

    result = detect_baseline_drift(
        previous_run={"parser_version": "v1"},
        current_run={"parser_version": "v2"},
        previous_pages=("home", "products", "dealers"),
        current_pages=("home", "products", "dealers"),
        policy_version="radar-drift-v1",
    )

    assert result.is_drift is True
    assert result.reason_codes == ("parser_version_changed",)


def test_snapshot_diff_keeps_each_observed_link_and_drift_detects_fact_disappearance() -> None:
    from app.modules.radar.diff import detect_baseline_drift, diff_snapshots

    previous = (
        '{"facts":['
        '{"key":"page.observed_link","value":{"url":"https://one.example/"}}'
        ',{"key":"page.observed_link","value":{"url":"https://two.example/"}}]}'
    )
    changed = '{"facts":[{"key":"page.observed_link","value":{"url":"https://one.example/"}}]}'
    delta = diff_snapshots(previous, changed, detector_version="radar-diff-v1")
    assert b"two.example" in delta

    result = detect_baseline_drift(
        previous_run={"parser_version": "v1"},
        current_run={"parser_version": "v1"},
        previous_pages=("home", "dealers", "products"),
        current_pages=("home", "dealers", "products"),
        previous_facts_by_page={
            "home": ("page.title=Acme", "page.visible_text=Products"),
            "dealers": ("page.visible_text=Dealer list",),
            "products": ("page.visible_text=Engines",),
        },
        current_facts_by_page={
            "home": (),
            "dealers": (),
            "products": ("page.visible_text=Engines",),
        },
        page_kinds={"home": "home", "dealers": "dealers", "products": "product"},
        policy_version="radar-drift-v1",
    )

    assert result.is_drift is True
    assert "stable_fact_disappearance" in result.reason_codes
