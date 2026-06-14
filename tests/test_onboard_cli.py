import httpx
import respx
from cryptography.hazmat.primitives import serialization

from kalshi_console.app.config import Settings
from kalshi_console.kalshi.endpoints import Env
from kalshi_console.onboarding import cli, keygen


def _write_key(tmp_path) -> Settings:
    key = keygen.generate_rsa_keypair()
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    keygen.store_private_key_pem(tmp_path, "demo", pem)
    return Settings(
        _env_file=None,
        env=Env.demo,
        api_key_id="key-uuid",
        secrets_dir=tmp_path,
    )


def test_run_self_test_ok(tmp_path, capsys):
    settings = _write_key(tmp_path)
    rc = cli.run_self_test(settings)
    assert rc == 0
    assert "self-test OK" in capsys.readouterr().out


def test_run_self_test_missing_key(tmp_path, capsys):
    settings = Settings(
        _env_file=None, env=Env.demo, api_key_id="k",
        secrets_dir=tmp_path, private_key_path=tmp_path / "nope.pem",
    )
    rc = cli.run_self_test(settings)
    assert rc == 1
    assert "no private key" in capsys.readouterr().err.lower()


def test_run_store_key(tmp_path, capsys):
    src = tmp_path / "downloaded.pem"
    key = keygen.generate_rsa_keypair()
    src.write_bytes(key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ))
    settings = Settings(_env_file=None, env=Env.demo, api_key_id="k", secrets_dir=tmp_path)
    rc = cli.run_store_key(settings, src)
    assert rc == 0
    assert keygen.private_key_path(tmp_path, "demo").exists()


async def test_run_verify_hits_public_and_authed(tmp_path, capsys):
    settings = _write_key(tmp_path)
    base = "https://external-api.demo.kalshi.co/trade-api/v2"
    with respx.mock(assert_all_called=True) as mock:
        mock.get(f"{base}/exchange/status").mock(
            return_value=httpx.Response(200, json={"exchange_active": True, "trading_active": True})
        )
        bal = mock.get(f"{base}/portfolio/balance").mock(
            return_value=httpx.Response(200, json={"balance": 9999, "balance_dollars": "99.99"})
        )
        rc = await cli.run_verify(settings)
    assert rc == 0
    out = capsys.readouterr().out
    assert "exchange_active" in out and "balance" in out
    # the balance call was authenticated
    assert "KALSHI-ACCESS-SIGNATURE" in bal.calls.last.request.headers
