from __future__ import annotations

from fastapi.testclient import TestClient

from app import models
from app.dependencies import get_db
from app.main import create_app
from app.schemas import ApiKeyCreateRequest
from app.services.key_service import ApiKeyService
from app.utils import short_id


def test_notary_rejects_unapproved_base_url(session):
    account = models.Account(name=f"acct-{short_id('acc')}", tier="launch")
    session.add(account)
    session.flush()

    raw_key, _ = ApiKeyService(session).issue_api_key(
        account_id=account.id,
        payload=ApiKeyCreateRequest(name="viewer", role="viewer", scopes=["*"], account_id=account.id),
    )

    app = create_app()

    def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    response = client.post(
        "/api/v1/notary/chat",
        headers={"x-api-key": raw_key},
        json={
            "message": "hello",
            "provider": "ollama",
            "provider_base_url": "http://169.254.169.254",
        },
    )

    assert response.status_code == 400
