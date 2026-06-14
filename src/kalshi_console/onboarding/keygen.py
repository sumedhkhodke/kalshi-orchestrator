"""Secure local storage and validation of the Kalshi private key PEM."""
from __future__ import annotations

import os
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
from cryptography.hazmat.primitives.serialization import load_pem_private_key


def private_key_path(secrets_dir: str | Path, env: str) -> Path:
    """Return the canonical path for the private key under secrets_dir/env/."""
    return Path(secrets_dir) / env / "private_key.pem"


def validate_private_key_pem(pem: bytes) -> None:
    """Raise ValueError if `pem` is not a loadable RSA private key (PKCS#1 or PKCS#8)."""
    try:
        key = load_pem_private_key(pem, password=None)
    except Exception as exc:  # cryptography raises ValueError/TypeError on bad input
        raise ValueError(f"invalid private key PEM: {exc}") from exc
    if not isinstance(key, RSAPrivateKey):
        raise ValueError("Kalshi requires an RSA private key")


def store_private_key_pem(secrets_dir: str | Path, env: str, pem: str | bytes) -> Path:
    """Validate then write the PEM to <secrets_dir>/<env>/private_key.pem with 0600 perms."""
    data = pem.encode("utf-8") if isinstance(pem, str) else pem
    validate_private_key_pem(data)
    path = private_key_path(secrets_dir, env)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, data)
    finally:
        os.close(fd)
    return path


def generate_rsa_keypair() -> RSAPrivateKey:
    """Generate a 2048-bit RSA private key for onboarding or the upload flow."""
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


