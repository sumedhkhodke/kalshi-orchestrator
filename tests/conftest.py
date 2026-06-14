# tests/conftest.py
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa


@pytest.fixture
def rsa_private_key():
    """A 2048-bit RSA private key object for signing tests."""
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)
