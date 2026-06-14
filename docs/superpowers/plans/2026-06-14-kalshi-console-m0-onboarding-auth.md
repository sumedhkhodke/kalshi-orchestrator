# Kalshi Console — M0 (Onboarding & Secure Auth) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish the project skeleton and a correct, audited RSA-PSS signing path so a user can securely store their Kalshi private key and make authenticated read requests against the demo environment.

**Architecture:** A single installable Python package (`kalshi_console`) under `src/`. M0 builds the foundation modules every later milestone depends on: environment/host config with a demo↔prod switch, time helpers (ms vs seconds), the one audited `Signer` (RSA-PSS/SHA-256 with a sign↔verify self-test), secure on-disk PEM storage (`0600`), a minimal signed async REST client, and an onboarding CLI that validates end-to-end signed reads against demo.

**Tech Stack:** Python 3.12, `asyncio`, `httpx` (async HTTP), `cryptography` (RSA-PSS), `pydantic-settings` (config), stdlib `argparse` (CLI). Tests: `pytest`, `pytest-asyncio` (auto mode), `respx` (httpx mock).

**Spec:** [`docs/superpowers/specs/2026-06-13-kalshi-console-design.md`](../specs/2026-06-13-kalshi-console-design.md) — this plan implements **Milestone M0** (§L) and the §K onboarding flow.

**Conventions:**
- TDD: write the failing test, watch it fail, implement minimally, watch it pass, commit.
- All money/quantity work uses `Decimal` (arrives in M1); M0 has no money math.
- Commit messages: Conventional Commits, no co-author/agent trailers.
- Run tests with `uv run pytest` (or `pytest` inside the activated venv). Examples below use `pytest`.

---

## File Structure (created in M0)

```
Kalshi-Orchestrator/
├── pyproject.toml                       # package metadata, deps, pytest config, console script
├── .env.example                         # KALSHI_ENV, KALSHI_API_KEY_ID, KALSHI_PRIVATE_KEY_PATH, KALSHI_HTTP_PORT
├── src/kalshi_console/
│   ├── __init__.py
│   ├── app/
│   │   ├── __init__.py
│   │   ├── config.py                    # Settings (pydantic-settings); demo/prod switch
│   │   └── timeutil.py                  # now_ms / now_s / ms_to_s
│   ├── kalshi/
│   │   ├── __init__.py
│   │   ├── endpoints.py                 # Env, Hosts, HOSTS, REST_PREFIX, WS_PATH (single source of truth)
│   │   ├── signing.py                   # Signer (RSA-PSS) + canonical self-test
│   │   └── rest_client.py               # minimal signed async GET (grows in M1)
│   └── onboarding/
│       ├── __init__.py
│       ├── keygen.py                    # secure PEM storage + validation + (test) keypair generator
│       └── cli.py                       # `kalshi-onboard` CLI: self-test / store-key / verify
├── scripts/
│   └── onboard.py                       # thin shim -> kalshi_console.onboarding.cli:main
└── tests/
    ├── __init__.py
    ├── conftest.py                      # shared fixtures (generated RSA key, tmp secrets dir)
    ├── test_endpoints_config.py
    ├── test_timeutil.py
    ├── test_signing.py
    ├── test_keygen.py
    ├── test_rest_client.py
    └── test_onboard_cli.py
```

**Layout note vs spec:** the spec's tree lists these modules under a bare app root; here they live under one importable root package `kalshi_console` in `src/` (standard src-layout) to avoid top-level name collisions (`app`, `kalshi`). Internal sub-package names match the spec. Later milestones add `domain/`, `signals/`, `ticket/`, `web/`, `store/`, and `frontend/`.

---

## Task 1: Project scaffolding & tooling

**Files:**
- Create: `pyproject.toml`
- Create: `.env.example`
- Create: `src/kalshi_console/__init__.py`, `src/kalshi_console/app/__init__.py`, `src/kalshi_console/kalshi/__init__.py`, `src/kalshi_console/onboarding/__init__.py`
- Create: `tests/__init__.py` (the shared `tests/conftest.py` fixture file is authored in Task 4)
- Create: `tests/test_smoke.py` (temporary; deleted at end of task)

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[project]
name = "kalshi-console"
version = "0.1.0"
description = "Assisted-execution console for Kalshi (read-only v1)"
requires-python = ">=3.12"
dependencies = [
    "httpx>=0.27",
    "cryptography>=42",
    "pydantic>=2.7",
    "pydantic-settings>=2.3",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.2",
    "pytest-asyncio>=0.23",
    "respx>=0.21",
]

[project.scripts]
kalshi-onboard = "kalshi_console.onboarding.cli:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/kalshi_console"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "function"
testpaths = ["tests"]
pythonpath = ["src"]
```

- [ ] **Step 2: Create the package and test `__init__.py` files (all empty)**

Create empty files: `src/kalshi_console/__init__.py`, `src/kalshi_console/app/__init__.py`, `src/kalshi_console/kalshi/__init__.py`, `src/kalshi_console/onboarding/__init__.py`, `tests/__init__.py`.

- [ ] **Step 3: Write `.env.example`**

```bash
# Kalshi environment: "demo" (.co sandbox) or "prod" (.com)
KALSHI_ENV=demo
# Your API key id (UUID) from Kalshi Settings > API Keys
KALSHI_API_KEY_ID=
# Absolute path to your RSA private key PEM (chmod 600). If unset, the CLI uses
# <secrets_dir>/<env>/private_key.pem
KALSHI_PRIVATE_KEY_PATH=
# Where secrets are stored locally (default: ~/.kalshi-console)
KALSHI_SECRETS_DIR=
# Local dashboard port (used from M1 onward)
KALSHI_HTTP_PORT=8000
```

- [ ] **Step 4: Write a temporary smoke test**

```python
# tests/test_smoke.py
def test_import_package():
    import kalshi_console
    assert kalshi_console is not None
```

- [ ] **Step 5: Create the virtualenv and install, then run the smoke test**

Run:
```bash
uv venv && uv pip install -e ".[dev]"
uv run pytest tests/test_smoke.py -v
```
Expected: PASS (`test_import_package`). If you use `pip` instead of `uv`: `python -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]" && pytest tests/test_smoke.py -v`.

- [ ] **Step 6: Delete the smoke test and commit the scaffolding**

```bash
rm tests/test_smoke.py
git add pyproject.toml .env.example src/ tests/
git commit -m "chore: scaffold kalshi_console package and test tooling"
```

---

## Task 2: Hosts/endpoints constants + Settings config (demo↔prod switch)

**Files:**
- Create: `src/kalshi_console/kalshi/endpoints.py`
- Create: `src/kalshi_console/app/config.py`
- Test: `tests/test_endpoints_config.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_endpoints_config.py
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_endpoints_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'kalshi_console.kalshi.endpoints'`.

- [ ] **Step 3: Implement `endpoints.py`**

```python
# src/kalshi_console/kalshi/endpoints.py
"""Single source of truth for Kalshi hosts and signed-path prefixes."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Env(str, Enum):
    demo = "demo"
    prod = "prod"


@dataclass(frozen=True)
class Hosts:
    rest_base: str  # includes the /trade-api/v2 prefix
    ws_url: str
    web_base: str   # public website base for deep links (used from M4)


# Demo = kalshi.co, Prod = kalshi.com. `demo.kalshi.com` is NOT a valid domain.
HOSTS: dict[Env, Hosts] = {
    Env.demo: Hosts(
        rest_base="https://external-api.demo.kalshi.co/trade-api/v2",
        ws_url="wss://external-api-ws.demo.kalshi.co/trade-api/ws/v2",
        web_base="https://demo.kalshi.co",
    ),
    Env.prod: Hosts(
        rest_base="https://external-api.kalshi.com/trade-api/v2",
        ws_url="wss://external-api-ws.kalshi.com/trade-api/ws/v2",
        web_base="https://kalshi.com",
    ),
}

# The signed path always includes this prefix (REST) or is exactly WS_PATH (WebSocket).
REST_PREFIX = "/trade-api/v2"
WS_PATH = "/trade-api/ws/v2"
```

- [ ] **Step 4: Implement `config.py`**

```python
# src/kalshi_console/app/config.py
"""Application settings with a single demo/prod environment switch."""
from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from kalshi_console.kalshi.endpoints import HOSTS, Env, Hosts


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="KALSHI_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: Env = Env.demo
    api_key_id: str | None = None
    private_key_path: Path | None = None
    secrets_dir: Path = Field(default_factory=lambda: Path.home() / ".kalshi-console")
    http_port: int = 8000

    @property
    def hosts(self) -> Hosts:
        return HOSTS[self.env]

    def resolved_private_key_path(self) -> Path:
        """Explicit path if set, else <secrets_dir>/<env>/private_key.pem."""
        if self.private_key_path is not None:
            return self.private_key_path
        return self.secrets_dir / self.env.value / "private_key.pem"
```

Note: `private_key_path` is the raw optional setting; `resolved_private_key_path()` derives the default `<secrets_dir>/<env>/private_key.pem` when it is unset. The Task 2 test asserts on `resolved_private_key_path()`.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/test_endpoints_config.py -v`
Expected: PASS (6 tests).

- [ ] **Step 6: Commit**

```bash
git add src/kalshi_console/kalshi/endpoints.py src/kalshi_console/app/config.py tests/test_endpoints_config.py
git commit -m "feat: add Kalshi host constants and demo/prod settings"
```

---

## Task 3: Time helpers (milliseconds vs seconds)

**Files:**
- Create: `src/kalshi_console/app/timeutil.py`
- Test: `tests/test_timeutil.py`

Context: the auth header and WS data channels use **milliseconds**; REST query filters and WS lifecycle channels use **seconds**. One module owns the conversions so call sites can't confuse units.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_timeutil.py
from kalshi_console.app import timeutil


def test_now_ms_is_int_and_plausible():
    ms = timeutil.now_ms()
    assert isinstance(ms, int)
    # after 2025-01-01 and before 2100-01-01, in milliseconds
    assert 1_735_689_600_000 < ms < 4_102_444_800_000


def test_now_s_is_int_and_plausible():
    s = timeutil.now_s()
    assert isinstance(s, int)
    assert 1_735_689_600 < s < 4_102_444_800


def test_ms_to_s_truncates():
    assert timeutil.ms_to_s(1703123456789) == 1703123456


def test_now_ms_roughly_thousand_times_now_s():
    s = timeutil.now_s()
    ms = timeutil.now_ms()
    assert abs(ms - s * 1000) < 2000
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_timeutil.py -v`
Expected: FAIL with `ModuleNotFoundError` / `AttributeError: module ... has no attribute 'now_ms'`.

- [ ] **Step 3: Implement `timeutil.py`**

```python
# src/kalshi_console/app/timeutil.py
"""Time helpers. Auth header + WS data = milliseconds; REST filters + WS lifecycle = seconds."""
from __future__ import annotations

import time


def now_ms() -> int:
    """Current Unix time in MILLISECONDS (used by the auth signature)."""
    return int(time.time() * 1000)


def now_s() -> int:
    """Current Unix time in SECONDS (used by REST query filters)."""
    return int(time.time())


def ms_to_s(ms: int) -> int:
    """Truncate milliseconds to whole seconds."""
    return ms // 1000
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_timeutil.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add src/kalshi_console/app/timeutil.py tests/test_timeutil.py
git commit -m "feat: add ms/seconds time helpers"
```

---

## Task 4: RSA-PSS Signer (the load-bearing module)

**Files:**
- Create: `src/kalshi_console/kalshi/signing.py`
- Test: `tests/test_signing.py`
- Modify: `tests/conftest.py` (add a shared RSA key fixture)

Context (from the capability map): `message = timestamp_ms + METHOD + path`, **no separators**, path **includes** `/trade-api/v2` (REST) or is exactly `/trade-api/ws/v2` (WS), **excludes the query string**. Algorithm: RSA-PSS, SHA-256, MGF1-SHA-256, salt length = digest length (32). Signature is **base64** (not hex), timestamp in **milliseconds**. RSA-PSS is randomized (random salt), so we verify the **sign↔verify round-trip**, not a fixed signature string.

- [ ] **Step 1: Add a shared RSA key fixture to `tests/conftest.py`**

```python
# tests/conftest.py
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa


@pytest.fixture
def rsa_private_key():
    """A 2048-bit RSA private key object for signing tests."""
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)
```

- [ ] **Step 2: Write the failing test**

```python
# tests/test_signing.py
import base64

import pytest
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding

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


def test_build_message_ws_path(rsa_private_key):
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
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `uv run pytest tests/test_signing.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'kalshi_console.kalshi.signing'`.

- [ ] **Step 4: Implement `signing.py`**

```python
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
        assert self.build_message(_CANONICAL_TS, "GET", _CANONICAL_PATH) == _CANONICAL_MESSAGE
        h = self.headers("GET", _CANONICAL_PATH, timestamp_ms=_CANONICAL_TS)
        signature = base64.b64decode(h["KALSHI-ACCESS-SIGNATURE"])
        # Raises cryptography.exceptions.InvalidSignature on failure.
        self._key.public_key().verify(
            signature, _CANONICAL_MESSAGE.encode("utf-8"), _PSS, hashes.SHA256()
        )
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/test_signing.py -v`
Expected: PASS (10 tests).

- [ ] **Step 6: Commit**

```bash
git add src/kalshi_console/kalshi/signing.py tests/test_signing.py tests/conftest.py
git commit -m "feat: add audited RSA-PSS request signer with self-test"
```

---

## Task 5: Secure key storage + validation

**Files:**
- Create: `src/kalshi_console/onboarding/keygen.py`
- Test: `tests/test_keygen.py`

Context: the server-generated private key PEM is shown **once**. Persist it immediately to a `0600` file outside the repo/DB. `cryptography.load_pem_private_key` transparently handles PKCS#1 (`BEGIN RSA PRIVATE KEY`) and PKCS#8 (`BEGIN PRIVATE KEY`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_keygen.py
import stat

import pytest
from cryptography.hazmat.primitives import serialization

from kalshi_console.onboarding import keygen


def _pem(fmt: serialization.PrivateFormat) -> bytes:
    key = keygen.generate_rsa_keypair_object()
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=fmt,
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_keygen.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'kalshi_console.onboarding.keygen'`.

- [ ] **Step 3: Implement `keygen.py`**

```python
# src/kalshi_console/onboarding/keygen.py
"""Secure local storage and validation of the Kalshi private key PEM."""
from __future__ import annotations

from pathlib import Path

from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey
from cryptography.hazmat.primitives.serialization import load_pem_private_key


def private_key_path(secrets_dir: str | Path, env: str) -> Path:
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
    path.write_bytes(data)
    path.chmod(0o600)
    return path


def generate_rsa_keypair_object() -> RSAPrivateKey:
    """Generate a 2048-bit RSA private key (used in tests and the optional upload flow)."""
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_keygen.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add src/kalshi_console/onboarding/keygen.py tests/test_keygen.py
git commit -m "feat: add secure private-key PEM storage and validation"
```

---

## Task 6: Minimal signed async REST client

**Files:**
- Create: `src/kalshi_console/kalshi/rest_client.py`
- Test: `tests/test_rest_client.py`

Context: M0 needs just enough HTTP to validate auth: a `get(path, auth=...)` that builds the URL from the env's `rest_base`, and when `auth=True` signs `REST_PREFIX + path` (query excluded from signing). Pagination, rate-limiting, and Decimal models arrive in M1.

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_rest_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'kalshi_console.kalshi.rest_client'`.

- [ ] **Step 3: Implement `rest_client.py`**

```python
# src/kalshi_console/kalshi/rest_client.py
"""Minimal signed async REST client. Grows into the full gateway in M1."""
from __future__ import annotations

from typing import Any

import httpx

from kalshi_console.kalshi.endpoints import REST_PREFIX, Hosts
from kalshi_console.kalshi.signing import Signer


class KalshiRestClient:
    def __init__(
        self,
        hosts: Hosts,
        signer: Signer | None = None,
        *,
        client: httpx.AsyncClient | None = None,
        timeout: float = 10.0,
    ) -> None:
        self._hosts = hosts
        self._signer = signer
        self._client = client or httpx.AsyncClient(timeout=timeout)

    async def get(
        self, path: str, *, auth: bool = False, params: dict[str, Any] | None = None
    ) -> Any:
        """GET `path` (relative to the /trade-api/v2 base). Query params are excluded from signing."""
        url = f"{self._hosts.rest_base}{path}"
        headers: dict[str, str] = {}
        if auth:
            if self._signer is None:
                raise RuntimeError("auth required but no signer configured")
            headers = self._signer.headers("GET", f"{REST_PREFIX}{path}")
        resp = await self._client.get(url, headers=headers, params=params)
        resp.raise_for_status()
        return resp.json()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "KalshiRestClient":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_rest_client.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add src/kalshi_console/kalshi/rest_client.py tests/test_rest_client.py
git commit -m "feat: add minimal signed async REST client"
```

---

## Task 7: Onboarding CLI (`self-test` / `store-key` / `verify`)

**Files:**
- Create: `src/kalshi_console/onboarding/cli.py`
- Create: `scripts/onboard.py`
- Test: `tests/test_onboard_cli.py`

Context: the CLI is the M0 deliverable. `self-test` runs the signer round-trip offline (no key/network beyond a loaded key). `store-key` securely persists a PEM. `verify` makes a public read (`/exchange/status`) and an authed read (`/portfolio/balance`) against the configured env to prove end-to-end auth.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_onboard_cli.py
import base64

import httpx
import pytest
import respx
from cryptography.hazmat.primitives import serialization

from kalshi_console.app.config import Settings
from kalshi_console.kalshi.endpoints import Env
from kalshi_console.onboarding import cli, keygen


def _write_key(tmp_path) -> Settings:
    key = keygen.generate_rsa_keypair_object()
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
    key = keygen.generate_rsa_keypair_object()
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_onboard_cli.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'kalshi_console.onboarding.cli'`.

- [ ] **Step 3: Implement `cli.py`**

```python
# src/kalshi_console/onboarding/cli.py
"""`kalshi-onboard` CLI: validate signing and authenticated reads against an environment."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from kalshi_console.app.config import Settings
from kalshi_console.kalshi.rest_client import KalshiRestClient
from kalshi_console.kalshi.signing import Signer
from kalshi_console.onboarding import keygen


def _load_signer(settings: Settings) -> Signer | None:
    key_path = settings.resolved_private_key_path()
    if not key_path.exists() or not settings.api_key_id:
        return None
    return Signer.from_pem_file(settings.api_key_id, key_path)


def run_self_test(settings: Settings) -> int:
    signer = _load_signer(settings)
    if signer is None:
        print(
            f"[{settings.env.value}] no private key at {settings.resolved_private_key_path()} "
            "or KALSHI_API_KEY_ID unset",
            file=sys.stderr,
        )
        return 1
    signer.self_test()
    print(f"[{settings.env.value}] signer self-test OK (canonical vector + round-trip verify)")
    return 0


def run_store_key(settings: Settings, pem_file: Path) -> int:
    pem = Path(pem_file).read_bytes()
    path = keygen.store_private_key_pem(settings.secrets_dir, settings.env.value, pem)
    print(f"[{settings.env.value}] stored private key at {path} (mode 0600)")
    return 0


async def run_verify(settings: Settings) -> int:
    signer = _load_signer(settings)
    if signer is None:
        print(
            f"[{settings.env.value}] cannot verify: missing key or KALSHI_API_KEY_ID",
            file=sys.stderr,
        )
        return 1
    signer.self_test()
    async with KalshiRestClient(settings.hosts, signer=signer) as client:
        status = await client.get("/exchange/status")
        balance = await client.get("/portfolio/balance", auth=True)
    print(f"[{settings.env.value}] /exchange/status -> {json.dumps(status)}")
    print(f"[{settings.env.value}] /portfolio/balance -> {json.dumps(balance)}")
    print(f"[{settings.env.value}] auth verified end-to-end.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="kalshi-onboard", description="Kalshi onboarding & auth checks")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("self-test", help="run the signer self-test (offline)")
    p_store = sub.add_parser("store-key", help="securely store a private key PEM")
    p_store.add_argument("pem_file", type=Path, help="path to the downloaded private key PEM")
    sub.add_parser("verify", help="live signed reads against the configured env")
    args = parser.parse_args(argv)

    settings = Settings()
    if args.command == "self-test":
        return run_self_test(settings)
    if args.command == "store-key":
        return run_store_key(settings, args.pem_file)
    if args.command == "verify":
        return asyncio.run(run_verify(settings))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Implement the `scripts/onboard.py` shim**

```python
# scripts/onboard.py
"""Convenience shim: `python scripts/onboard.py <command>`."""
from kalshi_console.onboarding.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/test_onboard_cli.py -v`
Expected: PASS (4 tests).

- [ ] **Step 6: Run the full suite**

Run: `uv run pytest -v`
Expected: PASS (all tests across tasks 2–7, 34 tests).

- [ ] **Step 7: Commit**

```bash
git add src/kalshi_console/onboarding/cli.py scripts/onboard.py tests/test_onboard_cli.py
git commit -m "feat: add onboarding CLI (self-test, store-key, verify)"
```

---

## Task 8: M0 README + manual onboarding runbook

**Files:**
- Create: `README.md`
- Test: none (documentation)

- [ ] **Step 1: Write `README.md`**

````markdown
# Kalshi Console

A read-only, human-in-the-loop assisted-execution console for Kalshi. See the design spec in
[`docs/superpowers/specs/2026-06-13-kalshi-console-design.md`](docs/superpowers/specs/2026-06-13-kalshi-console-design.md)
and verified API research in [`docs/research/`](docs/research/).

## Setup

```bash
uv venv && uv pip install -e ".[dev]"
uv run pytest            # all tests should pass
cp .env.example .env     # then edit values
```

## Onboarding (Milestone 0) — get authenticated read access, demo first

1. **Create a demo account** at https://demo.kalshi.co/sign-up (note: `.co`, the sandbox).
   Fund it with the sandbox test card if needed. (Repeat later on https://kalshi.com for prod.)
2. **Generate an API key.** In the Kalshi web app, go to **Settings → API Keys** and create a key.
   Kalshi generates the keypair and shows the **private key PEM exactly once** — download it now.
   Copy the **API Key ID** (a UUID).
   - The REST endpoint `POST /trade-api/v2/api_keys/generate` does the same thing but is
     typically authenticated by your existing logged-in member session (not by an RSA key you don't
     have yet), so the web UI is the practical path for the first key.
3. **Store the key securely:**
   ```bash
   export KALSHI_ENV=demo
   export KALSHI_API_KEY_ID=<your-uuid>
   uv run kalshi-onboard store-key /path/to/downloaded_private_key.pem
   ```
   This writes `~/.kalshi-console/demo/private_key.pem` with `0600` perms. Never commit it.
4. **Validate signing offline:**
   ```bash
   uv run kalshi-onboard self-test
   ```
   Expect: `signer self-test OK`.
5. **Validate live signed reads against demo:**
   ```bash
   uv run kalshi-onboard verify
   ```
   Expect printed `/exchange/status` and `/portfolio/balance` responses and `auth verified end-to-end.`
6. **Repeat steps 1–5 with `KALSHI_ENV=prod`** when you're ready; prod keys are stored separately and
   are not interchangeable with demo keys.

## Environments

`KALSHI_ENV=demo` uses `*.kalshi.co`; `KALSHI_ENV=prod` uses `*.kalshi.com`. Credentials are
environment-scoped (a demo key on prod, or vice versa, returns 401).
````

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add M0 onboarding runbook"
```

---

## Self-Review (M0 plan vs spec §K and §L-M0)

- **Spec §K onboarding steps 1–5** → Task 7 (`store-key`, `self-test`, `verify`) + Task 8 runbook. ✓
- **Spec M0 deliverable "CLI that authenticates to demo"** → Task 7 `verify`. ✓
- **Signer exactness (ms, no separators, no query, salt=32, base64, WS path)** → Task 4 tests assert each. ✓
- **Secure PEM `0600` outside repo/DB** → Task 5 (`store_private_key_pem`, perms test) + `.gitignore` already excludes `*.pem`/`.kalshi-console/`. ✓
- **Demo/prod single switch, `.co`/`.com`** → Task 2 (`HOSTS`, `Settings.env`). ✓
- **No write path** → M0 client exposes only `get()`; no order endpoints. ✓
- **Type consistency** → `Signer(api_key_id, private_key)`, `Signer.from_pem_file`, `Signer.headers/ws_headers/self_test/build_message`, `KalshiRestClient(hosts, signer=...).get(path, auth=, params=)`, `Settings.hosts`/`resolved_private_key_path()`, `keygen.store_private_key_pem/validate_private_key_pem/private_key_path` are referenced identically across Tasks 4–8. ✓
- **Placeholder scan** → no TBD/TODO; every code/test step is complete. ✓
- **Note:** the Task 2 test asserts on `resolved_private_key_path()` directly; `private_key_path` is the raw optional setting and may be unset.

---

## Milestone Roadmap (M1–M5)

Each milestone gets its own detailed TDD plan written just-in-time (so it reflects what earlier
milestones establish). Summary of scope and the interfaces they build on M0:

- **M1 — Read core + dashboard shell.** Grow `KalshiRestClient` into the full gateway: `app/money.py`
  (`Decimal` parse/format for `*_dollars`/`*_fp` + integer-cent stragglers), typed `kalshi/models.py`,
  cursor pagination, the read token-bucket mirror (`kalshi/ratelimit.py` seeded from `/account/limits`
  + `/account/endpoint_costs`), `domain/market_cache.py`, `store/` (aiosqlite + watchlist), and the
  FastAPI app (`web/`) with the browser WS hub and a Preact shell showing positions/PnL/balance via
  REST poll + an env/status banner. *Ship: dashboard showing real demo portfolio + markets.*
- **M2 — Live book + charts.** `kalshi/ws_client.py` (handshake via `Signer.ws_headers`, Ping/Pong,
  subscribe, per-`sid` seq-gap → `get_snapshot`, reconnect), `domain/orderbook.py` (bids-only →
  synthetic asks, best=last), order-book + candlestick + trade-tape panels, `domain/reconcile.py` v1
  (periodic REST snapshot cross-check). *Ship: live streaming book + charts on demo.*
- **M3 — Signal engine + alerts.** `signals/` (the `Signal` Protocol, `SignalContext`, `engine.py`
  with dedupe/cooldown/hysteresis) + the four families (`fair_value`, `orderbook_flow`, `milestones`,
  `arbitrage`) + the alerts-feed panel + per-signal config + alert persistence. *Ship: live alerts.*
- **M4 — Ticket-prep.** `ticket/builder.py` (quadratic fee, collateral/max-loss, payout, breakeven,
  edge — all `Decimal`), `ticket/risk.py` (advisory checks), `ticket/deeplink.py` (copy payload +
  best-effort market-page link, verified during M0/M1), `ticket/submit_seam.py` (`NotImplementedError`),
  and the `TicketModal`. *Ship: alert → ticket → copy/open-in-Kalshi.*
- **M5 — Resilience & prod-readiness.** Full reconcile-on-reconnect, Thursday 03:00–05:00 ET
  maintenance state machine + UI banner, observability (read-token utilization, WS gap counts,
  reconcile deltas), WS→browser backpressure tuning, demo→prod validation. *Ship: robust read-only
  console ready to point at prod.*

When M0 is implemented and green, say "plan M1" and I'll write the M1 plan in this same TDD format.
