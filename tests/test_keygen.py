import stat

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from kalshi_console.onboarding import keygen


def _pem(fmt: serialization.PrivateFormat) -> bytes:
    key = keygen.generate_rsa_keypair()
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=fmt,
        encryption_algorithm=serialization.NoEncryption(),
    )


def _ec_pem() -> bytes:
    key = ec.generate_private_key(ec.SECP256R1())
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


def test_private_key_path_layout(tmp_path):
    p = keygen.private_key_path(tmp_path, "demo")
    assert p == tmp_path / "demo" / "private_key.pem"


def test_validate_accepts_pkcs8():
    keygen.validate_private_key_pem(_pem(serialization.PrivateFormat.PKCS8))


def test_validate_accepts_pkcs1():
    keygen.validate_private_key_pem(_pem(serialization.PrivateFormat.TraditionalOpenSSL))


def test_validate_rejects_garbage():
    with pytest.raises(ValueError):
        keygen.validate_private_key_pem(b"not a pem")


def test_validate_rejects_ec_key():
    """Non-RSA keys must be rejected even though they deserialize successfully."""
    with pytest.raises(ValueError, match="RSA"):
        keygen.validate_private_key_pem(_ec_pem())


def test_store_writes_0600_and_roundtrips(tmp_path):
    pem = _pem(serialization.PrivateFormat.PKCS8)
    path = keygen.store_private_key_pem(tmp_path, "demo", pem)
    assert path == tmp_path / "demo" / "private_key.pem"
    assert path.read_bytes() == pem
    mode = stat.S_IMODE(path.stat().st_mode)
    assert mode == 0o600
    # parent dir is private too
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700


def test_store_rejects_invalid_pem(tmp_path):
    with pytest.raises(ValueError):
        keygen.store_private_key_pem(tmp_path, "demo", b"garbage")


def test_store_rejects_ec_key(tmp_path):
    """store_private_key_pem must propagate the RSA-type rejection from validate."""
    with pytest.raises(ValueError, match="RSA"):
        keygen.store_private_key_pem(tmp_path, "demo", _ec_pem())


def test_store_accepts_str_pem(tmp_path):
    """store_private_key_pem's str→bytes encoding branch must work end-to-end."""
    pem_bytes = _pem(serialization.PrivateFormat.PKCS8)
    pem_str = pem_bytes.decode("utf-8")
    path = keygen.store_private_key_pem(tmp_path, "demo", pem_str)
    assert path.read_bytes() == pem_bytes
