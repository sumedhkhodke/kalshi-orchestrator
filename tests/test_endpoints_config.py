from pathlib import Path

from kalshi_console.kalshi.endpoints import Env, HOSTS, REST_PREFIX, WS_PATH
from kalshi_console.app.config import Settings


def test_demo_hosts_use_co_tld():
    h = HOSTS[Env.demo]
    assert h.rest_base == "https://external-api.demo.kalshi.co/trade-api/v2"
    assert h.ws_url == "wss://external-api-ws.demo.kalshi.co/trade-api/ws/v2"
    assert h.web_base == "https://demo.kalshi.co"


def test_prod_hosts_use_com_tld():
    h = HOSTS[Env.prod]
    assert h.rest_base == "https://external-api.kalshi.com/trade-api/v2"
    assert h.ws_url == "wss://external-api-ws.kalshi.com/trade-api/ws/v2"
    assert h.web_base == "https://kalshi.com"


def test_path_constants():
    assert REST_PREFIX == "/trade-api/v2"
    assert WS_PATH == "/trade-api/ws/v2"


def test_settings_defaults_to_demo(monkeypatch):
    monkeypatch.delenv("KALSHI_ENV", raising=False)
    s = Settings(_env_file=None)
    assert s.env == Env.demo
    assert s.hosts.rest_base.endswith(".kalshi.co/trade-api/v2")


def test_settings_env_switch_reads_env_var(monkeypatch):
    monkeypatch.setenv("KALSHI_ENV", "prod")
    s = Settings(_env_file=None)
    assert s.env == Env.prod
    assert s.hosts.web_base == "https://kalshi.com"


def test_settings_derived_private_key_path(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("KALSHI_ENV", "demo")
    monkeypatch.setenv("KALSHI_SECRETS_DIR", str(tmp_path))
    monkeypatch.delenv("KALSHI_PRIVATE_KEY_PATH", raising=False)
    s = Settings(_env_file=None)
    assert s.resolved_private_key_path() == tmp_path / "demo" / "private_key.pem"


def test_settings_empty_env_strings_treated_as_unset(monkeypatch):
    """Empty values in a copied .env (e.g. `KALSHI_SECRETS_DIR=`) must mean "unset",
    not Path("."). Otherwise store-key writes into the repo and self-test reads a dir."""
    monkeypatch.setenv("KALSHI_ENV", "demo")
    monkeypatch.setenv("KALSHI_API_KEY_ID", "")
    monkeypatch.setenv("KALSHI_PRIVATE_KEY_PATH", "")
    monkeypatch.setenv("KALSHI_SECRETS_DIR", "")
    s = Settings(_env_file=None)
    assert s.api_key_id is None
    assert s.private_key_path is None
    assert s.secrets_dir == Path.home() / ".kalshi-console"
    assert (
        s.resolved_private_key_path()
        == Path.home() / ".kalshi-console" / "demo" / "private_key.pem"
    )
