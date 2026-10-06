"""The ledger's Ed25519 signing key: prod refuses to start without one, dev generates and
persists one, and the public half is published so signatures verify outside the ledger.

Audit (2026-10-06): birth certificates and ledger events were unsigned, so nothing the
ledger issued could be checked by a party that does not trust its database.
"""

from __future__ import annotations

import base64

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings
from app.main import create_app
from app.services.signing_service import (
    LedgerSigner,
    canonical_json_bytes,
    generate_private_key_pem,
    get_signer,
)

PROD = {
    "environment": "prod",
    "api_key_secret": "signing-test-secret-that-is-at-least-32-characters",
    "bootstrap_admin_token": "bootstrap-admin-test-secret",
}


def _b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def test_production_refuses_to_start_without_a_signing_key():
    with pytest.raises(ValidationError, match="PGL_SIGNING_KEY_PEM or PGL_SIGNING_KEY_PATH"):
        Settings(**PROD)


def test_production_rejects_unloadable_or_non_ed25519_keys(tmp_path):
    with pytest.raises(ValidationError, match="could not be loaded"):
        Settings(**PROD, pgl_signing_key_pem="not a pem")
    with pytest.raises(ValidationError, match="could not be loaded"):
        Settings(**PROD, pgl_signing_key_path=str(tmp_path / "missing.pem"))

    ec_pem = (
        ec.generate_private_key(ec.SECP256R1())
        .private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
        .decode()
    )
    with pytest.raises(ValidationError, match="Ed25519"):
        Settings(**PROD, pgl_signing_key_pem=ec_pem)


def test_production_accepts_pem_inline_escaped_or_from_file(tmp_path):
    pem = generate_private_key_pem()
    key_file = tmp_path / "pgl.pem"
    key_file.write_text(pem)

    inline = LedgerSigner.from_settings(Settings(**PROD, pgl_signing_key_pem=pem))
    escaped = LedgerSigner.from_settings(
        Settings(**PROD, pgl_signing_key_pem=pem.replace("\n", "\n"))
    )
    from_file = LedgerSigner.from_settings(Settings(**PROD, pgl_signing_key_path=str(key_file)))

    assert inline.key_id == escaped.key_id == from_file.key_id
    assert inline.key_id.startswith("pgl-ed25519-")


def test_dev_generates_a_key_once_and_reuses_it(tmp_path):
    settings = Settings(
        environment="dev",
        api_key_secret="dev-secret-at-least-16",
        certificate_storage_path=str(tmp_path / "data" / "certificates"),
    )
    first = LedgerSigner.from_settings(settings)
    second = LedgerSigner.from_settings(settings)

    assert (tmp_path / "data" / "keys" / "pgl-signing-key.pem").exists()
    assert first.key_id == second.key_id


def test_signature_verifies_and_fails_after_any_change():
    signer = get_signer()
    payload = {"agent_id": "agent_x", "event_count": 3, "nested": {"a": [1, 2]}}
    signature = signer.sign(payload)

    assert signer.verify(payload, signature)
    assert not signer.verify({**payload, "event_count": 4}, signature)
    assert not signer.verify({**payload, "nested": {"a": [2, 1]}}, signature)
    assert not signer.verify(payload, {**signature, "key_id": "pgl-ed25519-other"})
    assert not signer.verify(payload, {**signature, "value": signature["value"][::-1]})
    assert not signer.verify(payload, None)


def test_public_key_is_published_and_verifies_signatures_independently():
    client = TestClient(create_app())
    well_known = client.get("/.well-known/pgl-signing-key")
    api_alias = client.get("/api/v1/ledger/signing-key")  # no API key: public

    assert well_known.status_code == 200
    assert api_alias.status_code == 200
    assert well_known.json() == api_alias.json()
    descriptor = well_known.json()
    assert descriptor["algorithm"] == "Ed25519"
    assert descriptor["jwk"]["kid"] == descriptor["key_id"] == get_signer().key_id
    assert "PRIVATE" not in descriptor["public_key_pem"]

    payload = {"certificate_id": "cert_1", "genome_hash": "ab" * 32}
    signature = get_signer().sign(payload)

    from_jwk = Ed25519PublicKey.from_public_bytes(_b64url_decode(descriptor["jwk"]["x"]))
    from_pem = serialization.load_pem_public_key(descriptor["public_key_pem"].encode())
    for public_key in (from_jwk, from_pem):
        public_key.verify(_b64url_decode(signature["value"]), canonical_json_bytes(payload))
