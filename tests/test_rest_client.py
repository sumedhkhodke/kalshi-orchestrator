# tests/test_rest_client.py
import base64

import httpx
import pytest
import respx

from kalshi_console.kalshi.endpoints import HOSTS, Env
from kalshi_console.kalshi.rest_client import KalshiRestClient
from kalshi_console.kalshi.signing import Signer


@pytest.fixture
def demo_hosts():
    return HOSTS[Env.demo]


async def test_get_public_no_auth_headers(demo_hosts):
    with respx.mock(assert_all_called=True) as mock:
        route = mock.get(
            "https://external-api.demo.kalshi.co/trade-api/v2/exchange/status"
        ).mock(return_value=httpx.Response(200, json={"exchange_active": True, "trading_active": True}))
        client = KalshiRestClient(demo_hosts)
        data = await client.get("/exchange/status")
        await client.aclose()
    assert data["exchange_active"] is True
    sent = route.calls.last.request
    assert "KALSHI-ACCESS-KEY" not in sent.headers


async def test_get_auth_adds_signed_headers(demo_hosts, rsa_private_key):
    signer = Signer("key-uuid", rsa_private_key)
    with respx.mock(assert_all_called=True) as mock:
        route = mock.get(
            "https://external-api.demo.kalshi.co/trade-api/v2/portfolio/balance"
        ).mock(return_value=httpx.Response(200, json={"balance": 12345}))
        client = KalshiRestClient(demo_hosts, signer=signer)
        data = await client.get("/portfolio/balance", auth=True)
        await client.aclose()
    assert data["balance"] == 12345
    sent = route.calls.last.request
    assert sent.headers["KALSHI-ACCESS-KEY"] == "key-uuid"
    assert sent.headers["KALSHI-ACCESS-TIMESTAMP"].isdigit()
    base64.b64decode(sent.headers["KALSHI-ACCESS-SIGNATURE"])  # decodes without error


async def test_get_auth_excludes_query_from_signature(demo_hosts, rsa_private_key):
    """A query param must reach the URL but NOT break signing (signed path has no query)."""
    signer = Signer("k", rsa_private_key)
    with respx.mock(assert_all_called=True) as mock:
        route = mock.get(
            "https://external-api.demo.kalshi.co/trade-api/v2/portfolio/orders"
        ).mock(return_value=httpx.Response(200, json={"orders": []}))
        client = KalshiRestClient(demo_hosts, signer=signer)
        await client.get("/portfolio/orders", auth=True, params={"limit": 5})
        await client.aclose()
    sent = route.calls.last.request
    assert sent.url.params["limit"] == "5"  # query present on the wire
    # signature was produced over the bare path; verify it round-trips
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding
    ts = sent.headers["KALSHI-ACCESS-TIMESTAMP"]
    msg = f"{ts}GET/trade-api/v2/portfolio/orders".encode()
    sig = base64.b64decode(sent.headers["KALSHI-ACCESS-SIGNATURE"])
    rsa_private_key.public_key().verify(
        sig, msg,
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
        hashes.SHA256(),
    )


async def test_get_auth_without_signer_raises(demo_hosts):
    client = KalshiRestClient(demo_hosts)
    with pytest.raises(RuntimeError, match="no signer"):
        await client.get("/portfolio/balance", auth=True)
    await client.aclose()
