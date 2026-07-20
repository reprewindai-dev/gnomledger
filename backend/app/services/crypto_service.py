from __future__ import annotations

import base64
import json
from typing import Any

from nacl.signing import SigningKey
from nacl.encoding import HexEncoder

from ..config import get_settings


class CryptoService:
    def __init__(self):
        settings = get_settings()
        self._signing_key_hex = settings.pgl_signing_key
        
        # We expect a 64-character hex string for Ed25519 seed (32 bytes)
        if len(self._signing_key_hex) == 64:
            self._signing_key = SigningKey(self._signing_key_hex, encoder=HexEncoder)
            self._verify_key = self._signing_key.verify_key
        else:
            # During dev/tests if the key isn't a valid hex, we hash it to create a deterministic seed
            from ..utils import stable_hash
            seed_hex = stable_hash({"seed": self._signing_key_hex})
            self._signing_key = SigningKey(seed_hex, encoder=HexEncoder)
            self._verify_key = self._signing_key.verify_key

    def sign_payload(self, payload: dict[str, Any]) -> str:
        """
        Deterministically serializes the payload, signs it using Ed25519,
        and returns a base64 encoded signature.
        """
        # Create canonical representation
        serialized = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        signed = self._signing_key.sign(serialized)
        
        # Return base64 encoded signature
        return base64.b64encode(signed.signature).decode("utf-8")
        
    def get_public_key_hex(self) -> str:
        """Returns the public key in hex format for independent verification."""
        return self._verify_key.encode(encoder=HexEncoder).decode("utf-8")
