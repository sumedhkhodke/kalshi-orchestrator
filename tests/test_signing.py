# tests/test_signing.py
import base64

import pytest
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding

from kalshi_console.kalshi.signing import Signer
from kalshi_console.kalshi.endpoints import REST_PREFIX, WS_PATH


def test_build_message_exact_canonical_vector():
    msg = Signer.build_message(1703123456789, "GET", "/trade-api/v2/portfolio/balance")
    assert msg == "1703123456789GET/trade-api/v2/portfolio/balance"


def test_build_message_uppercases_method():
    assert Signer.build_message(1, "get", "/trade-api/v2/x").startswith("1GET/")


def test_build_message_rejects_query_string():
    with pytest.raises(ValueError, match="query string"):
        Signer.build_message(1, "GET", "/trade-api/v2/portfolio/orders?limit=5")


def test_build_message_rejects_relative_path():
    with pytest.raises(ValueError, match="must start with"):
        Signer.build_message(1, "GET", "trade-api/v2/x")


def test_build_message_ws_path():
    assert Signer.build_message(1, "GET", WS_PATH) == "1GET/trade-api/ws/v2"


def test_headers_shape_and_units(rsa_private_key):
    signer = Signer("key-id-uuid", rsa_private_key)
    h = signer.headers("GET", f"{REST_PREFIX}/portfolio/balance", timestamp_ms=1703123456789)
    assert h["KALSHI-ACCESS-KEY"] == "key-id-uuid"
    assert h["KALSHI-ACCESS-TIMESTAMP"] == "1703123456789"  # ms, as string
    # base64-decodable signature (not hex)
    raw = base64.b64decode(h["KALSHI-ACCESS-SIGNATURE"])
    assert len(raw) == 256  # 2048-bit RSA -> 256-byte signature


def test_signature_verifies_with_public_key(rsa_private_key):
    signer = Signer("k", rsa_private_key)
    path = f"{REST_PREFIX}/portfolio/balance"
    h = signer.headers("GET", path, timestamp_ms=1703123456789)
    message = Signer.build_message(1703123456789, "GET", path).encode()
    sig = base64.b64decode(h["KALSHI-ACCESS-SIGNATURE"])
    # must NOT raise
    rsa_private_key.public_key().verify(
        sig, message,
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
        hashes.SHA256(),
    )


def test_tampered_message_fails_verification(rsa_private_key):
    signer = Signer("k", rsa_private_key)
    path = f"{REST_PREFIX}/portfolio/balance"
    h = signer.headers("GET", path, timestamp_ms=1703123456789)
    sig = base64.b64decode(h["KALSHI-ACCESS-SIGNATURE"])
    tampered = b"1703123456789GET/trade-api/v2/portfolio/positions"
    with pytest.raises(InvalidSignature):
        rsa_private_key.public_key().verify(
            sig, tampered,
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
            hashes.SHA256(),
        )


def test_ws_headers_sign_ws_path(rsa_private_key):
    signer = Signer("k", rsa_private_key)
    h = signer.ws_headers(timestamp_ms=42)
    sig = base64.b64decode(h["KALSHI-ACCESS-SIGNATURE"])
    rsa_private_key.public_key().verify(
        sig, b"42GET/trade-api/ws/v2",
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
        hashes.SHA256(),
    )


def test_self_test_passes_for_valid_key(rsa_private_key):
    Signer("k", rsa_private_key).self_test()  # must not raise


def test_from_pem_file_round_trip(rsa_private_key, tmp_path):
    """from_pem_file is the production entry point; it must load a PKCS#8 PEM and pass self_test."""
    pem = rsa_private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    pem_file = tmp_path / "private_key.pem"
    pem_file.write_bytes(pem)
    signer = Signer.from_pem_file("key-id", pem_file)
    signer.self_test()  # must not raise


def test_from_pem_file_rejects_ec_key(tmp_path):
    """from_pem_file must raise ValueError when the PEM contains a non-RSA key."""
    ec_key = ec.generate_private_key(ec.SECP256R1())
    ec_pem = ec_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    pem_file = tmp_path / "ec_key.pem"
    pem_file.write_bytes(ec_pem)
    with pytest.raises(ValueError, match="RSA"):
        Signer.from_pem_file("key-id", pem_file)
