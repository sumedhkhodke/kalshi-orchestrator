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
