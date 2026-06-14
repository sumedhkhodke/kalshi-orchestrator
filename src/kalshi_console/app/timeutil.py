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
