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
    pem = pem_file.read_bytes()
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
