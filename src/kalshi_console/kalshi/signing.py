# src/kalshi_console/kalshi/signing.py
"""The single audited Kalshi request signer (RSA-PSS / SHA-256).

message = timestamp_ms + METHOD + path   (no separators)
- path INCLUDES /trade-api/v2 (REST) or is exactly /trade-api/ws/v2 (WS)
- path EXCLUDES any query string
- RSA-PSS, SHA-256 hash + MGF1, salt_length = digest length (32)
- signature is base64; timestamp is milliseconds
"""
from __future__ import annotations

import base64
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey

from kalshi_console.app.timeutil import now_ms
from kalshi_console.kalshi.endpoints import REST_PREFIX, WS_PATH

_PSS = padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH)
_CANONICAL_PATH = f"{REST_PREFIX}/portfolio/balance"
_CANONICAL_TS = 1703123456789
_CANONICAL_MESSAGE = "1703123456789GET/trade-api/v2/portfolio/balance"


class Signer:
    def __init__(self, api_key_id: str, private_key: RSAPrivateKey) -> None:
        self._api_key_id = api_key_id
        self._key = private_key

    @classmethod
    def from_pem_file(cls, api_key_id: str, pem_path: str | Path) -> "Signer":
        data = Path(pem_path).read_bytes()
        key = serialization.load_pem_private_key(data, password=None)
        if not isinstance(key, RSAPrivateKey):
            raise ValueError("Kalshi requires an RSA private key")
        return cls(api_key_id, key)

    @staticmethod
    def build_message(timestamp_ms: int, method: str, path: str) -> str:
        if not path.startswith("/"):
            raise ValueError("path must start with '/' and include the /trade-api/v2 prefix")
        if "?" in path:
            raise ValueError("signed path must not include a query string")
        return f"{timestamp_ms}{method.upper()}{path}"

    def _sign(self, message: str) -> str:
        signature = self._key.sign(message.encode("utf-8"), _PSS, hashes.SHA256())
        return base64.b64encode(signature).decode("ascii")

    def headers(self, method: str, path: str, *, timestamp_ms: int | None = None) -> dict[str, str]:
        ts = now_ms() if timestamp_ms is None else timestamp_ms
        message = self.build_message(ts, method, path)
        return {
            "KALSHI-ACCESS-KEY": self._api_key_id,
            "KALSHI-ACCESS-TIMESTAMP": str(ts),
            "KALSHI-ACCESS-SIGNATURE": self._sign(message),
        }

    def ws_headers(self, *, timestamp_ms: int | None = None) -> dict[str, str]:
        """Headers for the WebSocket handshake. Signs GET /trade-api/ws/v2."""
        return self.headers("GET", WS_PATH, timestamp_ms=timestamp_ms)

    def self_test(self) -> None:
        """Reproduce the canonical message and verify a fresh signature round-trips.

        Raises if signing/verification is misconfigured. Cheap; run at startup.
        """
        if self.build_message(_CANONICAL_TS, "GET", _CANONICAL_PATH) != _CANONICAL_MESSAGE:
            raise RuntimeError("canonical message vector mismatch — signing format is broken")
        h = self.headers("GET", _CANONICAL_PATH, timestamp_ms=_CANONICAL_TS)
        signature = base64.b64decode(h["KALSHI-ACCESS-SIGNATURE"])
        # Raises cryptography.exceptions.InvalidSignature on failure.
        self._key.public_key().verify(
            signature, _CANONICAL_MESSAGE.encode("utf-8"), _PSS, hashes.SHA256()
        )
