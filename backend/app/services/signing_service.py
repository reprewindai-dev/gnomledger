"""Ed25519 signing key held by the ledger.

The ledger signs birth certificates, chain checkpoints and audit bundles with one Ed25519
key so that an outside party can verify them against the public key published at
GET /.well-known/pgl-signing-key without trusting this service's database.

Key source, in order: PGL_SIGNING_KEY_PEM (PKCS#8 PEM text; literal "\\n" sequences are
accepted for single-line env files), PGL_SIGNING_KEY_PATH (path to a PEM file), and only
outside production a dev key generated once and persisted under the data directory.
Production refuses to start without one of the first two (see config.Settings).
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from ..config import Settings, get_settings

ALGORITHM = "Ed25519"
ISSUER = "gnomledger"
CANONICALIZATION = (
    "pgl-c14n-v1: UTF-8 JSON, object keys sorted, separators ',' and ':', "
    "no whitespace, non-ASCII characters escaped as \\uXXXX"
)


def canonical_json_bytes(data: Any) -> bytes:
    """The exact bytes that are signed. Verifiers must reproduce this serialization."""
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(
        "utf-8"
    )


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def load_private_key_pem(pem: str | bytes) -> Ed25519PrivateKey:
    if isinstance(pem, str):
        pem = pem.replace("\\n", "\n").encode("utf-8")
    key = serialization.load_pem_private_key(pem, password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError("PGL signing key must be an Ed25519 private key")
    return key


def generate_private_key_pem() -> str:
    return (
        Ed25519PrivateKey.generate()
        .private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        .decode("ascii")
    )


def dev_signing_key_path(settings: Settings) -> Path:
    # The data directory is the parent of the certificate store (./data or /tmp on Vercel).
    return Path(settings.certificate_storage_path).parent / "keys" / "pgl-signing-key.pem"


class LedgerSigner:
    def __init__(self, private_key: Ed25519PrivateKey, source: str):
        self._private_key = private_key
        self.public_key: Ed25519PublicKey = private_key.public_key()
        self.source = source
        raw = self.public_key.public_bytes(
            encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
        )
        self._public_raw = raw
        self.key_id = f"pgl-ed25519-{hashlib.sha256(raw).hexdigest()[:16]}"

    @classmethod
    def from_settings(cls, settings: Settings) -> "LedgerSigner":
        if settings.pgl_signing_key_pem:
            return cls(load_private_key_pem(settings.pgl_signing_key_pem), "env:PGL_SIGNING_KEY_PEM")
        if settings.pgl_signing_key_path:
            path = Path(settings.pgl_signing_key_path)
            return cls(load_private_key_pem(path.read_bytes()), f"file:{path}")
        if settings.environment == "prod":
            raise RuntimeError("PGL_SIGNING_KEY_PEM or PGL_SIGNING_KEY_PATH is required in production")
        path = dev_signing_key_path(settings)
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            # O_EXCL: two workers racing at first start must not overwrite each other's key.
            try:
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                pass
            else:
                with os.fdopen(fd, "w", encoding="ascii") as fp:
                    fp.write(generate_private_key_pem())
        return cls(load_private_key_pem(path.read_bytes()), f"dev-generated:{path}")

    # -- signing ---------------------------------------------------------------------------

    def sign(self, payload: dict[str, Any]) -> dict[str, str]:
        signature = self._private_key.sign(canonical_json_bytes(payload))
        return {"algorithm": ALGORITHM, "key_id": self.key_id, "value": _b64url(signature)}

    def verify(self, payload: dict[str, Any], signature: dict[str, Any] | None) -> bool:
        if not signature or signature.get("algorithm") != ALGORITHM:
            return False
        if signature.get("key_id") != self.key_id:
            return False
        try:
            self.public_key.verify(
                _b64url_decode(str(signature.get("value", ""))), canonical_json_bytes(payload)
            )
        except (InvalidSignature, ValueError, TypeError):
            return False
        return True

    # -- publication -----------------------------------------------------------------------

    def public_key_pem(self) -> str:
        return self.public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode("ascii")

    def public_jwk(self) -> dict[str, str]:
        return {
            "kty": "OKP",
            "crv": "Ed25519",
            "x": _b64url(self._public_raw),
            "kid": self.key_id,
            "alg": "EdDSA",
            "use": "sig",
        }

    def public_descriptor(self) -> dict[str, Any]:
        return {
            "issuer": ISSUER,
            "key_id": self.key_id,
            "algorithm": ALGORITHM,
            "public_key_pem": self.public_key_pem(),
            "jwk": self.public_jwk(),
            "canonicalization": CANONICALIZATION,
            "signature_encoding": "base64url without padding",
        }


@lru_cache(maxsize=1)
def get_signer() -> LedgerSigner:
    return LedgerSigner.from_settings(get_settings())
