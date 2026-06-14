# Project Status — Kalshi Trade Orchestrator

A Python, human-in-the-loop **assisted-execution console** for Kalshi: ingests live market data,
tracks positions/PnL, surfaces signals/alerts, and prepares one-click order tickets — **read-only,
no autonomous trading** in v1. Demo-first.

**Last updated:** 2026-06-14 · **Branch:** `main` · **Tests:** 40 passing

> Legend: `[x]` done · `[ ]` not started · `[~]` in progress / blocked on input

## Process artifacts
- [x] Verified Kalshi Trade API v2 research — [`docs/research/`](docs/research/)
- [x] Approved v1 design spec — [`docs/superpowers/specs/2026-06-13-kalshi-console-design.md`](docs/superpowers/specs/2026-06-13-kalshi-console-design.md)
- [x] M0 implementation plan (TDD) — [`docs/superpowers/plans/2026-06-14-kalshi-console-m0-onboarding-auth.md`](docs/superpowers/plans/2026-06-14-kalshi-console-m0-onboarding-auth.md)
- [ ] M1–M5 implementation plans (written just-in-time per milestone)

## Milestones

### [x] M0 — Onboarding & Secure Auth  ✅ shipped (39 tests green)
- [x] Project scaffolding & tooling (`pyproject.toml`, `src/` layout, pytest)
- [x] Host constants + demo/prod `Settings` switch (`.co` / `.com`)
- [x] Time helpers (milliseconds vs seconds)
- [x] Audited RSA-PSS `Signer` + canonical sign/verify self-test
- [x] Secure `0600` private-key PEM storage + validation
- [x] Minimal signed async REST client
- [x] `kalshi-onboard` CLI (`self-test` / `store-key` / `verify`)
- [x] Onboarding runbook (`README.md`)
- [x] **Manual onboarding done:** demo account created, API key stored (`0600`), `verify` confirms
  live signed reads against demo (`/exchange/status` + `/portfolio/balance`, $100 sandbox balance)

### [ ] M1 — Read core + dashboard shell
- [ ] `app/money.py` — `Decimal` parse/format for `*_dollars`/`*_fp` + integer-cent stragglers
- [ ] Full REST gateway: typed models, cursor pagination, read token-bucket rate limiter
- [ ] `domain/market_cache.py` — series/event/market hierarchy
- [ ] `store/` — SQLite (aiosqlite) + watchlist
- [ ] FastAPI app + browser WebSocket hub + Preact shell
- [ ] Positions/PnL/balance panel (REST poll) + env/status banner
- [ ] *Ship: dashboard showing real demo portfolio + markets*

### [ ] M2 — Live book + charts
- [ ] WebSocket feed handler (handshake, Ping/Pong, per-`sid` seq-gap → `get_snapshot`, reconnect)
- [ ] Local order book (bids-only → synthetic asks, best = last element)
- [ ] Order-book panel + imbalance, candlestick chart, trade tape
- [ ] Reconciliation v1 (periodic REST snapshot cross-check)
- [ ] *Ship: live streaming book + charts on demo*

### [ ] M3 — Signal engine + alerts
- [ ] Pluggable `Signal` Protocol + engine (dedupe / cooldown / hysteresis)
- [ ] Family 1 — fair-value / mispricing (pluggable estimator, market-derived default)
- [ ] Family 2 — orderbook & price/volume
- [ ] Family 3 — milestone / news-driven (`/milestones`)
- [ ] Family 4 — cross-market arbitrage
- [ ] Alerts-feed panel + per-signal config + alert persistence
- [ ] *Ship: live alerts across all 4 families*

### [ ] M4 — Ticket-prep
- [ ] Fee / collateral / max-loss / payout / breakeven / edge math (`Decimal`)
- [ ] Advisory pre-trade risk check
- [ ] Ticket modal: copy-ready payload + best-effort market deep link
- [ ] Disabled future API-submit seam (`NotImplementedError`)
- [ ] *Ship: alert → ticket → copy / open in Kalshi*

### [ ] M5 — Resilience & prod-readiness
- [ ] Full reconcile-on-reconnect
- [ ] Thursday 03:00–05:00 ET maintenance state machine + UI banner
- [ ] Observability (read-token utilization, WS gap counts, reconcile deltas)
- [ ] WS→browser backpressure tuning + demo→prod validation
- [ ] *Ship: robust read-only console ready to point at prod*

## Quick start
```bash
uv venv && uv pip install -e ".[dev]"
uv run pytest              # 39 passed
uv run kalshi-onboard --help
```

## Next action
M0 complete (demo onboarding verified). Say "plan M1" to write the M1 implementation plan.
