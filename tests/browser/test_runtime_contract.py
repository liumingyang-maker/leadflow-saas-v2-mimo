from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_browser_compose_contract_is_isolated() -> None:
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert "browser-redis:" in compose
    assert "browser-worker:" in compose
    assert "browser-egress:" in compose
    assert "browser-control:" in compose
    assert "internal: true" in compose
    assert "leadflow_browser_artifacts:" in compose
    assert "BROWSER_REDIS_URL=redis://browser-redis:6379/0" in compose
    assert "HTTPS_PROXY=http://browser-egress:8080" in compose
    assert "browser-redis:\n    image: redis:7.4.2-alpine\n    ports:" not in compose
    assert 'browser-redis:\n    image: redis:7.4.2-alpine\n    user: "999:1000"' in compose
    browser_worker_with_port = (
        "browser-worker:\n    build:\n      context: .\n"
        "      dockerfile: Dockerfile.browser\n    ports:"
    )
    assert browser_worker_with_port not in compose


def test_browser_images_are_minimal_and_sandboxed() -> None:
    worker = (ROOT / "Dockerfile.browser").read_text(encoding="utf-8")
    egress = (ROOT / "Dockerfile.browser-egress").read_text(encoding="utf-8")

    assert "USER browser" in worker
    assert "--no-sandbox" not in worker
    assert "--ignore-https-errors" not in worker
    assert "COPY app/integrations/browser ./app/integrations/browser" not in worker
    assert "models.py" not in worker
    assert "repository.py" not in worker
    assert "service.py" not in worker
    assert "COPY app/integrations/browser/restricted_playwright_mcp.cjs ./" in worker
    assert 'CMD ["python", "run_browser_worker.py", "browser"]' in worker
    assert "USER browserproxy" in egress
    assert 'CMD ["python", "run_browser_egress.py"]' in egress
