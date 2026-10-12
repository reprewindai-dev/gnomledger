from __future__ import annotations

from fastapi.testclient import TestClient

from app import config
from app.main import create_app


def _preflight(client: TestClient, origin: str):
    return client.options(
        "/health/live",
        headers={"Origin": origin, "Access-Control-Request-Method": "GET"},
    )


def test_configured_origins_are_allowed_alongside_defaults(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", '["https://www.veklom.dev/"]')
    monkeypatch.setenv("FRONTEND_ORIGIN", "https://pgl.veklom.dev")
    config.get_settings.cache_clear()
    try:
        client = TestClient(create_app())
        for origin in ("https://veklom.com", "https://www.veklom.dev", "https://pgl.veklom.dev"):
            response = _preflight(client, origin)
            assert response.headers.get("access-control-allow-origin") == origin
        assert "access-control-allow-origin" not in _preflight(client, "https://evil.example").headers
    finally:
        config.get_settings.cache_clear()
