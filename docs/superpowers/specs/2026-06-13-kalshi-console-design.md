# Kalshi Assisted-Execution Console — v1 Design Spec

- **Status:** Approved (2026-06-13)
- **Owner:** sumedh
- **Type:** Greenfield build — design specification
- **Research basis:** [`docs/research/`](../../research/) — verified Kalshi Trade API v2 capability map, orchestrator building-block analysis, and open-questions register (multi-agent sweep, all domains high-confidence).

## Overview

A single-user, **human-in-the-loop** decision-support console for trading on Kalshi (a CFTC-regulated
binary prediction-market exchange where each contract pays $1.00 to the winning side, so price ≈
implied probability). One Python `asyncio` process **is** both the orchestrator and a FastAPI server:
it signs and ingests Kalshi REST + WebSocket data, maintains in-memory order books / positions / PnL
as `Decimal`, runs a **pluggable signal engine** (four families) that emits alerts, and on demand
computes a fully-quantified **order ticket** (side, size, limit, fee, collateral/max-loss, payout,
edge, advisory risk check). A browser dashboard receives everything live over one server→browser
WebSocket.

**The console never submits, amends, or cancels an order via the Kalshi API in v1.** Execution is
"one-click ticket prep": the console computes the complete ticket and hands the user a copy-ready
payload + a best-effort deep link to the market page; the human executes inside Kalshi's own UI. The
API-submit path exists only as a disabled, clearly-marked future seam (`NotImplementedError`).

## Decisions locked with the user

| Decision | Choice |
|---|---|
| Product shape | Assisted execution console, human-in-the-loop, **no autonomous trading** |
| v1 execution capability | **One-click ticket prep** (compute + copy + deep-link); **no order writes via API** |
| Interface | **Web dashboard** — FastAPI backend + browser UI, live server→browser WebSocket push |
| Language / runtime | **Python**, async (`asyncio`) |
| Core API client | **Hand-rolled thin client** (optionally vendor SDK models); not the generated SDK at runtime |
| Signal families (v1) | **All four**, via a pluggable engine: fair-value/mispricing, orderbook & price/volume, milestone/news-driven, cross-market arbitrage |
| Fair-value source (Family 1) | **Pluggable estimator interface** with a market-derived default (microprice/last-trade blend); external probability feed wired later |
| Kalshi access | **None yet** → Milestone 0 is onboarding (accounts + server-side RSA keypair + secure PEM storage); **demo-first** |
| Hosting / uptime | **Local dev first, cloud-ready** (Railway later); not required 24/7 in v1 |
| Alert delivery | **In-UI feed only** for v1 (desktop/Telegram/email deferred) |
| Frontend stack | **Vite + Preact + TypeScript + lightweight-charts + decimal.js + Tailwind** |
| Persistence | **SQLite** (`aiosqlite`), Decimals stored as TEXT, no orders table |
| Watchlist size (start) | Small (**≤ ~25 markets**) to stay inside read budget + WS caps |
| Ticket fee headline | **Taker** fee headline (marketable-limit default); maker shown when `fee_type = quadratic_with_maker_fees` |

## Scope

**In scope (v1):** RSA-PSS signing; authed REST reads (market data, authed orderbooks, portfolio
positions/fills/balance/settlements) + WebSocket feeds; in-memory order book (bids-only → synthetic
asks), positions & PnL (read-only); pluggable signal engine with all four families; ticket-prep
decision support (fee/collateral/payout/edge math + advisory risk check + copy/deep-link); web
dashboard with live push; SQLite persistence; reconciliation (REST-truth) + Thursday-maintenance
handling; demo-first onboarding and a single demo/prod env switch.

**Out of scope (v1):** autonomous trading; any order **write** (submit/amend/cancel) via the API;
the FIX API; perpetuals/margin; multi-account beyond default subaccount 0; backtesting; alert
channels beyond the in-browser feed.

---

> Lead-architect consolidation. Grounded in `docs/research/kalshi-api-capability-map.md` and `docs/research/kalshi-orchestrator-architecture.md`. Honors the locked v1 scope: human-in-the-loop console, **no API order writes**, FastAPI orchestrator + browser dashboard with WS push, all 4 signal families, Decimal money, bids-only book, token-bucket reads, WS+REST reconciliation, demo-first.
>
> **Merge stance.** The general "orchestrator" research doc describes a full trading bot (order manager, write buckets, idempotency, kill-switch). I keep its read/signing/feed/reconcile/risk *analysis* but **delete every write-path component** and replace it with a **Ticket Builder + a future-only submit seam**. Where the three source designs diverged, I resolve in favor of: (1) a hand-rolled thin async core over the SDK, (2) a single async process (library-first internals), and (3) brutal honesty that Kalshi exposes **no order-prefill URL scheme** — so the "one-click" deliverable is compute-and-copy, not auto-fill. Reasoning is inline at each decision.

---

## A. Summary & Guiding Principles

A single Python `asyncio` process **is** the orchestrator and the FastAPI server. It signs and pulls Kalshi REST + WebSocket data (public market data, authed orderbooks, authed portfolio reads), maintains in-memory order books / positions / PnL as `Decimal`, runs a **pluggable signal engine** (4 families) that emits **alerts**, and on demand computes a fully-quantified **order ticket** (side, size, limit, fee, collateral/max-loss, payout, edge, risk pre-check). The browser dashboard receives everything live over one server→browser WebSocket. **The console never submits, amends, or cancels an order via the API in v1**; the human executes the ticket inside Kalshi's own UI, aided by a copy-to-clipboard payload and a best-effort deep link.

**Guiding principles**
1. **REST is truth, WS is fast-but-fallible.** Every WS-built structure is reconciled against a REST snapshot on a cadence and after every disconnect/maintenance window.
2. **Decimal everywhere, float nowhere.** All money/quantity flows through one fixed-point module. Strings cross the browser boundary; the browser never does money math.
3. **Read-only by construction.** There is no code path that can POST/DELETE an order. The submit interface exists but is a `NotImplementedError` seam.
4. **Demo-first, one switch.** `KALSHI_ENV ∈ {demo, prod}` selects host + key + TLD; every log line and UI element is environment-tagged. `.co` = demo, `.com` = prod.
5. **Signing is the load-bearing risk.** One audited signer with a self-test against the doc's canonical vector; nothing else may construct headers.
6. **Honest UX.** No invented Kalshi order-prefill URL. We pre-fill *our* ticket and hand the human exact values to type.
7. **Pluggable by default.** Signals are registered plugins; adding one touches no core code.

---

## B. Architecture & Components (consolidated set)

Single process, library-first internals (modules below are independently testable against a mocked gateway). Order-write components from the research doc are intentionally **omitted**.

| # | Component | Responsibility | Kalshi touchpoints | Tricky bits |
|---|---|---|---|---|
| B1 | **Signer** (`kalshi/signing.py`) | Produce the three `KALSHI-ACCESS-*` headers for every authed REST call + WS handshake; ms clock. | All authed reads; WS handshake; (M0) `POST /api_keys/generate`. | `message = ms + METHOD + path`, **no separators, no query string**, path includes `/trade-api/v2` (REST) or is exactly `/trade-api/ws/v2` (WS). RSA-PSS/SHA256, `salt_length=DIGEST_LENGTH(32)`, **base64 not hex**, **ms not s**. Ship a self-test reproducing `1703123456789GET/trade-api/v2/portfolio/balance`. NTP-sync the clock. |
| B2 | **REST Gateway** (`kalshi/rest_client.py`) | Typed async wrapper (httpx); Decimal coercion; cursor pagination; backoff; **read** token-bucket gating. | Market data (`/markets`, `/markets/{t}`, `/markets/{t}/orderbook`, `/markets/orderbooks`, `/markets/trades`, candlesticks, `/milestones`, `/events`, `/series`); portfolio reads (`/portfolio/balance|positions|fills|settlements|orders`); ops (`/exchange/status|schedule|announcements`, `/account/limits`, `/account/endpoint_costs`, `/margin/fee_tiers`). | Both orderbook endpoints **require auth** though the rest of market data is public. Parse `*_dollars`/`*_fp` → `Decimal`; keep the integer-cent stragglers straight (balance/portfolio_value, settlement revenue/value, total_resting_order_value). Query filters are **unix seconds**; auth header is **ms**. Stop paging on empty cursor, not short page. **No write bucket is used in v1.** |
| B3 | **Read Rate-Limiter** (`kalshi/ratelimit.py`) | Local mirror of the **read** token bucket; seed from `/account/limits` + `/account/endpoint_costs`; gate every send. | `/account/limits`, `/account/endpoint_costs`. | 429 has **no `Retry-After`/headers** — only your accounting tells you. Default cost 10 (Get Order = 2). Basic read = 200 tok/s ≈ 20 req/s; budget the polling loops against it. Exponential backoff + jitter on 429. |
| B4 | **WS Feed Handler** (`kalshi/ws_client.py`) | One authed socket; multiplex by `sid`; normalize; **per-sid seq-gap detection**; snapshot recovery; reply to Pings. | Handshake `wss://external-api-ws.demo.kalshi.co/trade-api/ws/v2`; `subscribe/unsubscribe/update_subscription`; public `orderbook_delta`, `ticker`, `trade`; private `fill`, `market_positions`, `user_orders`. | Server **Ping (0x9, body `heartbeat`) every 10s → must Pong (0xA)**; no JSON heartbeat. `seq` present on `orderbook_delta` (gap → `update_subscription action=get_snapshot`), **absent** on confirmations. Type≠channel (`market_positions`→`market_position`; `user_orders`→`user_order`, field `ticker`). Data channels ms, lifecycle channels seconds. Reconnect + re-sign + re-subscribe + re-snapshot after every drop. |
| B5 | **Local Order Book** (`domain/orderbook.py`) | Per-market replica of resting **bids** (yes+no); derive synthetic asks, mid, spread, microprice, depth, imbalance. | WS `orderbook_delta`; REST `/markets/{t}/orderbook` + `/markets/orderbooks` for cold-start/reconcile. | **Bids only**; **ascending → best bid = LAST element**. Synthetic: best YES ask = `1 − highest NO bid`; best NO ask = `1 − highest YES bid`. `delta_fp` is a **signed** string applied per `(side, price)`. Per-market tick from `price_ranges[].step` (not always 1¢). |
| B6 | **Position & PnL Tracker** (`domain/positions.py`) | Authoritative positions (market + event), cost basis, realized/unrealized PnL, fees paid; mark-to-market vs local book. **Read-only.** | `/portfolio/positions`, `/fills`, `/settlements`, `/balance`; WS `fill`, `market_positions`. | `position_fp` sign: **+YES / −NO**. `portfolio_value` = positions market value only (don't add to balance as equity). Determination ≠ settlement (`settlement_timer_seconds`); only **net** positions settle; payout $1/contract. Settlement `revenue`/`value` are **int cents** beside `*_dollars` cost basis. Dedupe fills by `fill_id`. Prefer `balance_dollars` for precision. |
| B7 | **Market/Event Cache** (`domain/market_cache.py`) | Series→Event→Market metadata, tick structure, fee_type/multiplier, mutually-exclusive flags, milestones; never parse tickers to infer relationships. | `/series`, `/events`, `/markets`, `/events/multivariate`, `/multivariate_event_collections/*`, `/milestones`, `/margin/fee_tiers`. | Use API fields (`series_ticker`, `event_ticker`, `Event.mutually_exclusive`, `associated_events[]`) — **never** parse ticker strings. `/events` excludes multivariate (use `/events/multivariate`). |
| B8 | **Signal Engine** (`signals/`) | Pluggable host that runs registered signals on WS-driven ticks + timers, dedupes/cooldowns, emits Alerts (+ optional `TicketDraft`). | Consumes B5/B6/B7 + trade tape + `/milestones`. | See §E. Probability-native (price = implied prob, YES+NO=$1); fee notch peaks at P=0.50. |
| B9 | **Ticket Builder + Risk Pre-Check** (`ticket/`) | Compute fully-quantified order ticket + advisory risk gate; build copy payload + deep link; expose future submit seam. | Reads B5/B6/B7 + `/margin/fee_tiers`, `/exchange/status`. | See §F. Honest "no URL prefill". Netting shown as **OFF/worst-case** (conservative; netting is locked at first order in an event, which we never place). |
| B10 | **Reconciliation Loop** (`domain/reconcile.py`) | Periodically + on reconnect, re-pull REST snapshots and re-anchor books/positions/balance; persist last seq-per-sid and last cursors. | `/portfolio/orders|positions|fills`, `/balance`, orderbook REST, `/exchange/status`. | WS best-effort → REST truth. Reconcile after every disconnect + Thursday 03:00–05:00 ET maintenance. |
| B11 | **Scheduler** (`app/scheduler.py`) | Drive polling cadences (candles, milestones, balance/positions), reconcile cadence, token-refill accounting, maintenance handling. | `/exchange/status`, `/exchange/schedule`, `/exchange/announcements`. | Thursday 03:00–05:00 ET pause; gate on `trading_active`/`exchange_active`; ET-aware. |
| B12 | **FastAPI App + Browser WS Hub** (`web/`) | HTTP routes for the UI, the `/ws` endpoint, fan-out of normalized state to browsers, backpressure/coalescing. | None (internal). | Serialize Decimal as **strings**; per-client outbound queue; coalesce orderbook to ~4–10 Hz/market; resend snapshots on browser reconnect. |
| B13 | **Persistence** (`store/`) | SQLite store: watchlist, alerts (append-only), signal config, reconcile cursors, computed-ticket audit log, optional WS event log. | None. | Decimals as TEXT; **no orders table** (no writes). PEM lives outside the DB. |
| B14 | **Observability** (`app/logging.py` + metrics) | Structured logs, metrics (read-token utilization, WS gap counts, reconcile deltas, signal/alert rates), env tag, health surface. | `/account/limits`, 429 counts, WS error codes 1–28. | Read-token budget is a first-class metric (no headers → self-accounting). Tag env on every line. |
| B15 | **Onboarding CLI** (`onboarding/`, `scripts/onboard.py`) | M0: validate keys, store PEM securely, signing self-test against demo. | `POST /api_keys/generate` (or web UI), `/portfolio/balance`, `/exchange/status`. | One-time PEM; chicken-and-egg auth (see §K). |

**Architecture style decision.** Library-first core (Style C) deployed as a single async process (Style A). Reasoning: Kalshi allows **one WS connection per key**, so a multi-service feed (Style B) buys nothing while adding IPC latency and ops cost; v1 has no writes and one account, so fault-isolation pressure is low. The library boundaries leave a clean seam to peel into services later if multi-account ever lands.

---

## C. Project Structure

```
kalshi-console/
├── pyproject.toml                # uv/poetry; pins httpx, websockets, cryptography, fastapi…
├── .env.example                  # KALSHI_ENV, key paths, ports, poll cadences
├── README.md
├── app/
│   ├── main.py                   # FastAPI factory + asyncio lifespan (starts feeds, scheduler, signals)
│   ├── config.py                 # pydantic-settings; demo/prod host+TLD+key switch
│   ├── scheduler.py              # periodic jobs, maintenance-window state machine
│   ├── logging.py                # structlog config, env tag
│   ├── money.py                  # Decimal context, fixed-point parse/format, fee math (§F)
│   └── timeutil.py               # ms/sec helpers, ET clock, maintenance windows
├── kalshi/
│   ├── signing.py                # RSA-PSS signer + canonical self-test vector
│   ├── ratelimit.py              # read token-bucket mirror + endpoint costs
│   ├── rest_client.py            # httpx async; Decimal coercion; pagination; backoff
│   ├── ws_client.py              # websockets; ping/pong; subscribe; seq-gap; get_snapshot
│   ├── endpoints.py              # path + host constants (single source of truth)
│   └── models.py                 # typed Decimal dataclasses of API objects
├── domain/
│   ├── orderbook.py              # bids-only book, synthetic asks, best=last
│   ├── positions.py              # positions/PnL/balance tracker (read-only)
│   ├── market_cache.py           # series/event/market/milestone metadata
│   └── reconcile.py              # REST-truth reconciliation, cursor/seq persistence
├── signals/
│   ├── base.py                   # Signal Protocol, SignalContext, Alert, TicketDraft
│   ├── registry.py               # register()/discover() (entry-points)
│   ├── engine.py                 # tick loop, dedupe/cooldown, emit
│   ├── fair_value.py             # Family 1
│   ├── orderbook_flow.py         # Family 2 (threshold/%move/volume/spread/imbalance/large-bid)
│   ├── milestones.py             # Family 3
│   └── arbitrage.py              # Family 4 (mutually-exclusive + combo)
├── ticket/
│   ├── builder.py                # compute ticket: fee/collateral/payout/edge
│   ├── risk.py                   # advisory pre-trade checks
│   ├── deeplink.py               # market-page URL (best-effort) + clipboard payload
│   └── submit_seam.py            # TicketSubmitter Protocol -> raise NotImplementedError (future)
├── web/
│   ├── ws_hub.py                 # browser WS manager, topics, backpressure/coalesce
│   ├── routes_ws.py              # GET /ws
│   ├── routes_api.py             # /api/watchlist, /api/ticket, /api/markets, /api/config
│   └── schemas.py                # pydantic DTOs (Decimal -> str) to browser
├── store/
│   ├── db.py                     # aiosqlite engine + schema/migrations
│   └── repos.py                  # watchlist, alerts, signal_config, cursors, ticket_audit
├── onboarding/
│   └── keygen.py                 # generate/validate key, store PEM (0600)
├── scripts/
│   └── onboard.py                # M0 CLI entry
├── tests/
│   ├── test_signing.py           # canonical vector + 401 traps
│   ├── test_money_fees.py        # quadratic fee, ceil-to-cent, cents stragglers
│   ├── test_orderbook.py         # best=last, synthetic asks, signed delta
│   ├── test_ticket_math.py       # collateral/payout/edge/breakeven
│   ├── test_signals_*.py         # each family
│   └── test_reconcile.py
└── frontend/
    ├── index.html
    ├── vite.config.ts
    ├── package.json              # preact, @preact/signals, lightweight-charts, decimal.js, tailwind
    ├── tailwind.config.js
    └── src/
        ├── main.tsx
        ├── ws.ts                 # native WebSocket client: reconnect, topic dispatch
        ├── store.ts              # @preact/signals state (books, positions, alerts…)
        ├── money.ts              # decimal.js formatting only (no math)
        ├── api.ts                # fetch wrappers for /api/*
        ├── panels/
        │   ├── Watchlist.tsx
        │   ├── OrderBook.tsx     # bids + synthetic asks, imbalance bar
        │   ├── Chart.tsx         # lightweight-charts candlesticks
        │   ├── Positions.tsx     # positions/PnL/balance
        │   ├── AlertsFeed.tsx
        │   └── TicketModal.tsx   # ticket + copy + deep link + risk badges
        └── components/
```
Frontend `npm run build` emits to `frontend/dist/`, served by FastAPI `StaticFiles` (one origin → same-origin WS, no CORS).

---

## D. End-to-End Data Flow

1. **Boot** (`app/main.py` lifespan): load `config` (env switch) → load PEM → `Signer.self_test()` → seed `ratelimit` from `/account/limits` + `/account/endpoint_costs` → warm `market_cache` (watchlisted series/events/markets, fee tiers, milestones) → REST cold-start each watched orderbook + positions/balance → open WS, subscribe `orderbook_delta|ticker|trade` (watchlist) + `fill|market_positions|user_orders` (private) → start `signals.engine`, `scheduler`, `reconcile`.
2. **Live ingest**: WS messages → normalize (Decimal, ms/sec) → update `orderbook` / `positions` / trade tape. `orderbook_delta` seq checked per sid; gap → `get_snapshot`.
3. **Signals**: each book/ticker/trade/position update (and timer ticks for milestone/candle polls) drives `engine.tick()` → registered signals evaluate over a `SignalContext` → `Alert`s (deduped/cooldowned) → persisted + pushed to browser.
4. **Browser push**: `ws_hub` fans normalized state to subscribed browser topics; orderbook coalesced to ~4–10 Hz; alerts/positions/balance/status pushed on change.
5. **Ticket request**: user clicks an alert or a market → browser `POST /api/ticket` (or WS request) → `ticket.builder` computes fee/collateral/payout/edge using live book + fee tiers → `ticket.risk` runs advisory checks → DTO back to `TicketModal`. User clicks **Copy** / **Open in Kalshi** and executes manually in Kalshi. Ticket is written to the audit log. **No API write occurs.**
6. **Reconcile**: scheduler triggers periodic REST re-pull (positions/balance/orderbook) + after any WS drop or maintenance window; divergences re-anchor in-memory state and emit observability deltas.

---

## E. Signal Engine (pluggable interface + 4 families + extension)

### E.1 The contract (`signals/base.py`)

```python
class Severity(IntEnum): INFO=1; WATCH=2; ACT=3

@dataclass(frozen=True)
class Alert:
    family: str                 # "fair_value" | "orderbook_flow" | "milestone" | "arbitrage"
    key: str                    # stable signal id, e.g. "fv_mispricing"
    tickers: tuple[str, ...]    # 1+ markets involved
    severity: Severity
    score: Decimal              # normalized strength / edge (probability or $)
    message: str
    dedupe_key: str             # e.g. f"{key}:{ticker}:{bucket}"
    ttl_s: int                  # auto-expire in the feed
    suggested_ticket: TicketDraft | None = None   # pre-fills the ticket modal
    created_ms: int = field(default_factory=now_ms)

class SignalContext(Protocol):
    def book(self, ticker: str) -> OrderBookView: ...        # best bid/ask(synthetic), mid, imbalance, depth
    def ticker_stats(self, ticker: str) -> TickerStats: ...  # last, %move, rolling vol/OI
    def trades(self, ticker: str, window_s: int) -> list[Trade]: ...
    def position(self, ticker: str) -> Position | None: ...
    def market(self, ticker: str) -> MarketMeta: ...         # fee_type, step, status, event, mutually_exclusive
    def event_markets(self, event_ticker: str) -> list[MarketMeta]: ...
    def milestones(self, since_ms: int) -> list[Milestone]: ...
    def fee_rate(self, ticker: str, role: Literal["taker","maker"]) -> Decimal: ...
    def params(self) -> dict: ...                            # per-signal config (thresholds)
    def now_ms(self) -> int: ...

@runtime_checkable
class Signal(Protocol):
    family: str
    key: str
    def inputs(self) -> InputSpec: ...                       # channels+markets it needs (drives WS subs)
    async def evaluate(self, ctx: SignalContext) -> list[Alert]: ...
```

**Engine** (`engine.py`): event-driven (runs affected signals on each relevant market update) plus timer ticks for poll-based inputs (milestones, candles). Per-`dedupe_key` **cooldown** + **hysteresis** to stop alert spam; alerts expire after `ttl_s`. Signals are cheap, pure-ish functions over the context — no I/O except declared poll inputs — so one slow plugin can't stall the feed (run with a per-signal timeout; offload heavy compute to a thread).

### E.2 The four families

1. **Fair-value / mispricing vs fees** (`fair_value.py`): compute a fair probability `p_fair` (pluggable estimator — default = reference blend of last trade + microprice + optional external feed; **the estimator itself is an injected strategy**, see Open Decision N2). Compare to the **executable** price net of fee: for buy-YES, `edge = p_fair − (best_yes_ask + taker_fee_per_contract)`. Alert `ACT` when `edge ≥ params.min_edge` and the level has sufficient size. Accounts for the quadratic fee notch at P=0.50.
2. **Orderbook & price/volume** (`orderbook_flow.py`): a bundle of sub-checks over book deltas + ticker + trade tape with rolling windows — **threshold cross** (price ≥/≤ X), **%move** over window, **volume/OI spike** (z-score vs trailing), **spread widening** (synthetic ask − best bid), **top-of-book imbalance** (`yes_bid_size_fp` vs derived ask size), **large resting bid appear/pull** (single-level size jump/drop ≥ threshold). Each is a config-toggled rule emitting `WATCH`/`ACT`.
3. **Milestone/news-driven** (`milestones.py`): poll `GET /milestones` (`limit` required, `min_updated_ts` cursor in **seconds**), map `related_event_tickers`/`primary_event_tickers` to watchlisted markets, emit an alert with the milestone `title`/`notification_message` when a new/updated milestone touches a watched event. Pure metadata link — **never** parse tickers; use the API fields.
4. **Cross-market arbitrage** (`arbitrage.py`): for `Event.mutually_exclusive == true`, sum the **executable** YES prices (synthetic asks, fee-aware) across legs; alert when `Σ yes_ask` deviates from `$1.00` beyond `fees + params.band`. For **combos/multivariate**, value = **product** of legs capped at $1.00, any leg at $0 ⇒ $0; flag mispricing vs the collection quote. Always net of fees + tick feasibility; conservative on stale books (require fresh seq).

### E.3 Adding a new signal
Implement the `Signal` Protocol in a new module, declare `inputs()` (so the engine knows which WS channels/markets to ensure are subscribed), expose a params schema, and `register()` it (entry-point or registry call). No core edits; the config UI auto-renders its params. Ship with a `test_signals_<name>.py` against `SignalContext` fixtures.

---

## F. Ticket-Prep Decision Support (exact math + risk + honest UX)

### F.1 Inputs & sides
User chooses an action mapped to Kalshi's single book: **Buy YES** (= `bid`), **Buy NO** (= buy the NO side; equivalently `ask` on YES), with **Sell-to-close** variants for existing positions. Limit price `P` in **dollars** for the chosen side, size `C` contracts (fixed-point, 0.01 granularity), validated against the market's tick `step` from `price_ranges`.

### F.2 Exact money math (all `Decimal`, fee symmetric in P)

```python
CENT = Decimal("0.01")
def ceil_cent(x: Decimal) -> Decimal:            # round UP on the ORDER TOTAL
    return (x / CENT).to_integral_value(rounding=ROUND_CEILING) * CENT

def quadratic_fee(C: Decimal, P: Decimal, coef: Decimal) -> Decimal:
    # P in DOLLARS (0..1); P*(1-P) identical for YES price P and NO price 1-P
    return ceil_cent(coef * C * P * (P.copy_negate() + 1))

taker_fee = quadratic_fee(C, P, Decimal("0.07"))                 # default coef
maker_fee = quadratic_fee(C, P, Decimal("0.0175"))               # only if fee_type == quadratic_with_maker_fees
# Prefer live coefs from /margin/fee_tiers keyed by ticker; apply series fee_multiplier/override.
```
Use the **taker** fee for the headline ticket (a marketable limit is the assisted default); show maker fee as a secondary line only when `fee_type = quadratic_with_maker_fees`.

**Collateral / max-loss / payout (long open):**
- `cost = P * C` ; `collateral = cost` ; **`max_loss = cost + taker_fee`** (premium + fee; you can't lose more than premium).
- Win payout = `1.00 * C`. **`pnl_win = (1 − P) * C − taker_fee`** ; **`pnl_lose = −(P * C) − taker_fee`**.
- `total_outlay = cost + taker_fee`.
- **Breakeven probability** `p* = P + taker_fee / C`.
- **Edge** (when a `p_fair` is available): `edge_prob = p_fair − p*` (Buy YES) or `(1 − p_fair) − p*` (Buy NO); also show `edge_$ = edge_prob * C`.

**Netting display:** show collateral **assuming netting OFF (worst case)**. Reasoning: `netting_enabled` is OFF by default and irreversibly **locked at the first order in an event** — and v1 never places that order, so we cannot assume netting and must not understate collateral. Surface a one-line note when a hedging/mutually-exclusive position exists ("netting could reduce collateral on Kalshi; not assumed here").

### F.3 Risk pre-check (`ticket/risk.py`) — advisory, never blocking a write (there is none)
Returns per-rule `PASS | WARN | BLOCK` badges shown on the ticket:
- **Fat-finger price**: `|P − mid| ≤ params.max_price_dev`; price on a valid tick `step`.
- **Size caps**: `C ≤ max_contracts_per_market`; projected market+**event-level** exposure ≤ caps (aggregate YES/NO and mutually-exclusive legs).
- **Balance sufficiency**: `total_outlay ≤ available balance_dollars` (informational — Kalshi enforces on submit).
- **Liquidity**: requested `C ≤ resting size at/through P` (warn on expected slippage / partial).
- **Market state**: `status active` and `/exchange/status` `trading_active` true; not inside the Thursday maintenance window.
- **Edge sanity**: warn if `edge_prob ≤ 0` or within fee noise.

### F.4 The honest deep-link / copy UX
**Kalshi exposes no public URL scheme to pre-fill side/size/limit.** "One-click ticket prep" therefore means: the console computes and presents the complete ticket; the human types it into Kalshi's own order form. Concretely the `TicketModal` provides:
- **Copy ticket** → clipboard payload (plain text + structured JSON): market title + `ticker`, action (Buy YES/NO), size `C`, limit `P`, est. taker fee, max-loss, payout-if-win, breakeven, edge.
- **Open in Kalshi** → best-effort deep link to the **market/event page** on the correct TLD (`kalshi.com` prod / `kalshi.co` demo), constructed from `series_ticker`/`event_ticker`. The web URL mapping is **not part of the API and not guaranteed** — verify it during M0 and fall back to the markets search page if unresolved.
- **Step checklist** mirroring Kalshi's order-form fields so the user fills it exactly.
- Every prepared ticket is written to the `ticket_audit` log (with the live book snapshot it was computed against).

**Future submit seam** (`ticket/submit_seam.py`):
```python
class TicketSubmitter(Protocol):
    async def submit(self, ticket: Ticket) -> OrderAck: ...   # v1: NotImplementedSubmitter raises
```
Wired through the UI behind a disabled control. The future implementation targets **V2** `/portfolio/events/orders` (`side=bid|ask`, TIF + STP required) — V1 is mid-deprecation with 10× cost — and would add `client_order_id` idempotency + an order state machine. None of that ships in v1.

---

## G. Frontend & Live-Push Design

**Stack (decision).** **Vite + Preact + TypeScript + `@preact/signals` + TradingView `lightweight-charts` + `decimal.js` + Tailwind.** Built to static assets, served by FastAPI (same origin). Reasoning: lighter than React/Svelte-kit, reactive enough for streaming panels, `lightweight-charts` is the standard for candlesticks, `decimal.js` formats the Decimal strings without reintroducing float math. (htmx was considered and rejected — server-push diffs into a live order book + candlestick chart are awkward with hypermedia swaps.)

**Panels:** Watchlist (add/remove markets → adjusts WS subs), **Live Order Book** (bids + **synthetic asks** with imbalance bar, best/mid/spread), **Price/Candlestick Chart** (`lightweight-charts`, periods 1/60/1440 min via `/candlesticks`, live last-trade overlay), **Positions/PnL/Balance**, **Alerts Feed** (severity-colored, click → opens `TicketModal`), plus an **env/status banner** (DEMO/PROD, `trading_active`, maintenance countdown).

**Backend WS → browser** (`web/ws_hub.py`):
- Single browser WS at `/ws`. Client sends `{"op":"subscribe","topics":["book:TICKER","alerts","portfolio","status"]}`.
- Server frames: `{"type":"book"|"ticker"|"trade"|"alert"|"position"|"balance"|"status","data":{…}}`; **all numbers are strings** (Decimal). Browser parses with `decimal.js` for display only.
- **Backpressure**: per-client bounded async queue; **coalesce order-book** updates to ~4–10 Hz/market (send compact top-N levels + derived asks + best/mid/spread/imbalance), drop intermediates; alerts/positions/balance pushed on change.
- **Reconnect**: client exponential backoff; on (re)connect the server replays current snapshots for subscribed topics so the UI is immediately consistent.

---

## H. Tech Stack & Key Libraries

- **Runtime:** Python 3.12, `asyncio`. **Core client = hand-rolled thin** (decision below).
- **HTTP:** `httpx` (async). **WS:** `websockets` (explicit Ping/Pong control). **Crypto:** `cryptography` (RSA-PSS). **Money:** stdlib `decimal`. **Web:** `fastapi` + `uvicorn`. **Config:** `pydantic-settings`. **DB:** `aiosqlite` (+ thin repo layer / SQLModel optional). **Logs:** `structlog`. **Tests:** `pytest` + `pytest-asyncio` + `respx` (httpx mock).
- **Frontend:** Vite, Preact, `@preact/signals`, `lightweight-charts`, `decimal.js`, Tailwind.

**SDK vs hand-rolled (decision).** **Recommend a thin hand-rolled core**; optionally **vendor the SDK's models only**. Reasoning: signing, the read token-bucket mirror, Decimal coercion at the cents/dollars boundary, and WS Ping/Pong + per-sid seq-gap recovery are exactly the load-bearing details, and we want one audited path we fully control with a canonical self-test — not a generated client we'd have to bend. The SDK is split (`kalshi_python_sync`/`kalshi_python_async`, **import `kalshi_python`**), lags the spec (3.20 SDK vs 3.21 spec), and its WS lives in a separate AsyncAPI doc anyway. v1 is read-only + WS, so the SDK's main value (typed request/response models) is captured by optionally vendoring its pydantic models behind our `kalshi/models.py`. Keep the SDK pinned as a cross-check reference, not the runtime dependency.

---

## I. Persistence Model (SQLite, Decimals as TEXT)

| Table | Key columns | Purpose |
|---|---|---|
| `watchlist` | `ticker` PK, `event_ticker`, `added_ts`, `subscribed` | drives WS subs + panels |
| `market_cache` | `ticker` PK, `event_ticker`, `series_ticker`, `fee_type`, `fee_multiplier`, `price_ranges`(json), `mutually_exclusive`, `status`, `updated_ts` | metadata snapshot (refreshed) |
| `alerts` | `id` PK, `family`, `key`, `tickers`(json), `severity`, `score`(text), `message`, `dedupe_key`, `created_ms`, `expires_ms` | **append-only** alert log |
| `signal_config` | `key` PK, `enabled`, `params`(json) | per-signal thresholds |
| `ticket_audit` | `id` PK, `ticker`, `action`, `size`(text), `price`(text), `fee`(text), `max_loss`(text), `payout`(text), `edge`(text), `book_snapshot`(json), `risk`(json), `created_ms` | every computed ticket (no submission) |
| `reconcile_state` | `scope` PK, `last_seq`(per sid), `last_cursor`, `updated_ms` | resume points |
| `ws_event_log` *(optional)* | `id`, `channel`, `sid`, `seq`, `payload`(json), `ts_ms` | replay/debug for seq-gap + PnL |
| `kv_settings` | `k` PK, `v` | env, misc |

**No orders table** (no write path). **PEM is never in the DB** — stored as a `0600` file under a secrets dir (or OS keychain / Railway secret), referenced by path in config. Decimals round-trip losslessly as TEXT.

---

## J. Resilience & Correctness

- **Units (one module, `app/money.py` + `app/timeutil.py`).** Parse `*_dollars`/`*_fp` → `Decimal`; hardcode the integer-cent stragglers (balance/portfolio_value, settlement revenue/value, total_resting_order_value) with explicit conversions; unit-test the boundaries. **Time:** auth header + WS data = **ms**; REST query filters + WS lifecycle channels = **seconds**; object datetimes = RFC3339. A small typed wrapper enforces the right unit per call site.
- **WS seq-gap + REST reconcile.** Track `seq` per `sid` on `orderbook_delta`; on gap → `update_subscription action=get_snapshot` (no resubscribe). Periodic REST orderbook snapshot cross-checks the WS book to catch silent drift. After **any** disconnect: re-sign handshake, re-subscribe, re-snapshot every book, re-pull positions/fills/balance, reconcile by `fill_id`/`order_id`, then resume.
- **Rate-limit mirror.** Local **read** token bucket seeded from `/account/limits` + `/account/endpoint_costs`; gate every send; exponential backoff + jitter on the headerless 429 (`{"error":"too many requests"}`); min-wait = cost/refill_rate. Read budget is a first-class metric. (Write bucket unused — no writes.)
- **Demo/prod parity.** Single `KALSHI_ENV` switch picks host/TLD/WS host/key; `.co`=demo, `.com`=prod (`demo.kalshi.com` is invalid). Credentials are environment-scoped (no cross-use → 401). Every log/metric/UI element tagged with env. Validate full read+signal+ticket flow on demo before pointing at prod.
- **Maintenance windows.** Scheduler models **Thursday 03:00–05:00 ET**: expect WS drop, stop expecting fresh data, show a UI countdown banner, suppress "stale book" false alerts, and run a full reconcile at 05:00 ET. Gate ticket "trading_active" badges on `/exchange/status` (`exchange_estimated_resume_time` is advisory).
- **Signing correctness.** Single signer; CI self-test reproduces the canonical vector; NTP-synced clock; ms timestamp asserted.

---

## K. Onboarding — Milestone 0 (no Kalshi access yet)

1. **Create accounts.** Demo at **`https://demo.kalshi.co/sign-up`** (`.co`), prod at `kalshi.com`. Fund demo with sandbox test cards as needed.
2. **Generate a server-side RSA keypair.** Kalshi generates the keypair on its side via **`POST /trade-api/v2/api_keys/generate`** (body `name`, optional `scopes`); the response includes `api_key_id` + the **`private_key` PEM shown exactly once**. **Chicken-and-egg note:** this call is authenticated by your **logged-in member session**, not by an RSA key you don't yet have — so in practice generate the key from the **Kalshi web UI "API Keys" page** (which performs the same call and shows the one-time PEM), or script it with your member session token. Do this **on demo first**, then repeat on prod.
3. **Store the PEM securely, immediately.** Write to `~/.kalshi-console/<env>/private_key.pem` with `chmod 600` (or OS keychain / Railway secret). Store `api_key_id` in config. **Never** commit the PEM or put it in the DB. It cannot be re-fetched — losing it means regenerating.
4. **Validate.** `scripts/onboard.py` runs the **signer self-test** (canonical vector) then a live signed `GET /exchange/status` + `GET /portfolio/balance` against demo to confirm auth end-to-end. Confirm the demo→prod env switch flips host/TLD/key cleanly.
5. **Output of M0:** working signed read access on demo (and prod keys stored, untouched), env switch verified, PEM secured.

---

## L. Build Milestones (ordered, demo-first, each shippable)

- **M0 — Onboarding & secure auth.** Accounts, server-side keygen, PEM secured, env switch, signer + self-test, `onboard.py` validates signed reads on demo. *Ship: CLI that authenticates to demo.*
- **M1 — Read core + dashboard shell.** REST gateway (Decimal, pagination, read token-bucket), market cache, watchlist, FastAPI + browser WS hub + Preact shell, Positions/PnL/Balance panel via REST poll, env/status banner. *Ship: dashboard showing real demo portfolio + markets.*
- **M2 — Live book + charts.** WS feed handler (Ping/Pong, subscribe, per-sid seq-gap → get_snapshot, reconnect), local order book (bids-only, synthetic asks, best=last), Order Book panel + imbalance, candlestick chart, trade tape, reconcile v1 (REST snapshot cross-check). *Ship: live streaming book + charts on demo.*
- **M3 — Signal engine + alerts.** Pluggable core (`Signal` Protocol, engine, dedupe/cooldown) + all 4 families + Alerts Feed panel + alert persistence + per-signal config UI. *Ship: live alerts across all 4 families.*
- **M4 — Ticket-prep.** Fee/collateral/payout/edge/breakeven math, advisory risk pre-check, `TicketModal`, copy payload + best-effort deep link, ticket audit log, disabled future submit seam. *Ship: end-to-end "alert → ticket → copy/open in Kalshi".*
- **M5 — Resilience & prod-readiness.** Full reconcile-on-reconnect, Thursday maintenance handling + UI banner, observability (read-token utilization, WS gap counts, reconcile deltas), demo→prod switch validation, WS-to-browser backpressure tuning, hardening. *Ship: a robust console ready to point at prod (still read-only).*

---

## M. Consolidated Risk Register

| Risk | Mitigation |
|---|---|
| **Silent 401 from signing** (ms vs s, separators, query in path, salt, base64, WS path) | One audited `Signer`; CI self-test vs canonical vector; ms asserted; NTP-synced; WS signs `/trade-api/ws/v2`. |
| **Headerless 429 / read-bucket exhaustion** | Local read token-bucket mirror seeded from `/account/limits` + `/account/endpoint_costs`; gate sends; exp backoff + jitter; budget as a first-class metric. |
| **Float corrupts money/fee math** | Decimal everywhere; one money module; integer-cent stragglers handled explicitly; fee/round-up unit tests. |
| **Orderbook off-by-one / wrong synthetic ask** | Encode "ascending → best = last", synthetic asks = `1 − opposite best bid`, signed `delta_fp`, per-market tick from `price_ranges`; periodic REST cross-check. |
| **WS seq gap / silent book drift** | Per-sid seq tracking → `get_snapshot`; periodic REST snapshot reconcile; event log for replay. |
| **WS disconnect / Thursday 03:00–05:00 ET maintenance** | Auto reconnect + re-sign + re-subscribe + re-snapshot; scheduler maintenance state machine; full REST reconcile at 05:00; suppress stale alerts; UI banner. |
| **Demo/prod credential cross-use → 401** | Single env switch; env-scoped keys; `.co`/`.com` enforced; env tag on every line. |
| **User expects auto-fill that Kalshi doesn't offer** | Honest UX: compute ticket + copy payload + best-effort market deep link + checklist; no fake order-prefill URL. |
| **Fair-value signal noise / false positives** | Pluggable estimator; fee-aware edge net of `p*`; size/liquidity gates; dedupe + hysteresis + cooldown. |
| **Arbitrage false positives** (stale book, fees, tick infeasibility, fractional) | Require fresh seq; sum **executable** synthetic asks net of fees; tick-feasibility check; combo product/$0-leg rule. |
| **Milestone over-polling vs read budget** | `min_updated_ts` cursor polling at a budgeted cadence through the rate-limiter. |
| **PEM leakage** | `0600` file outside repo/DB; keychain/secret option; never logged; one-time capture documented. |
| **SDK version lag / drift** | Hand-rolled core; SDK pinned only as reference; models optionally vendored behind our types. |
| **WS→browser backpressure** | Per-client bounded queue; coalesce book to 4–10 Hz; drop intermediates; snapshot-resync on reconnect. |
| **Decimal mangled across the browser boundary** | Serialize as strings; browser uses `decimal.js` for formatting only — no JS float math. |
| **Scope creep into writes** | No order table, no write bucket usage, submit seam raises `NotImplementedError`; review gate on any write code. |

---


---

## N. Resolved Decisions (locked with the user 2026-06-13)

The design panel surfaced ten open decisions; all are now resolved. Recommended defaults were
adopted except where noted.

1. **Core client:** ✅ **Hand-rolled thin async core.** Optionally vendor the SDK's pydantic models behind `kalshi/models.py`; keep `kalshi_python` pinned only as a cross-check reference, not a runtime dependency. We own the signing/WS path with a canonical self-test.
2. **Fair-value estimator (Family 1):** ✅ **Build the pluggable estimator interface now with a market-derived default** (microprice/last-trade blend, fee-aware edge). Source of a real external probability feed is deferred — the plug-in point is part of v1 so it can be added without rework.
3. **Frontend stack:** ✅ **Vite + Preact + TypeScript + lightweight-charts + decimal.js + Tailwind**, built to static assets served by FastAPI (same origin, no CORS).
4. **Persistence engine:** ✅ **SQLite** (`aiosqlite`), single process. Decimals as TEXT. Optional WS event log table available for replay/debug. Postgres only if/when hosted.
5. **Deep-link behavior:** ✅ **Best-effort market-page deep link + copy-ready payload + field checklist.** No invented order-prefill URL. Verify the web URL mapping during M0; fall back to the markets search page if unresolved.
6. **Secret storage:** ✅ **`0600` PEM file in a local secrets dir** (`~/.kalshi-console/<env>/private_key.pem`), referenced by path in config; never in the repo or DB. When hosted, use the platform secret store (Railway env + volume).
7. **Hosting target:** ✅ **Local dev first, cloud-ready.** Build with the env-switch + env-based secrets so a later Railway deploy is a config change, not a rewrite. 24/7 uptime + always-on auto-reconnect is **not** a v1 requirement (M5 still implements reconnect/maintenance handling for correctness while running).
8. **Watchlist size / WS scope:** ✅ Start **≤ ~25 simultaneously-watched markets** to stay well inside the Basic read budget and WS subscription caps; make it configurable.
9. **Alert delivery beyond dashboard:** ✅ **In-UI feed only for v1.** Desktop/OS, Telegram/Discord, and email/webhook notifiers are deferred (the alert manager is designed so a notifier sink can be added later without touching signals).
10. **Ticket fee headline:** ✅ **Taker** fee headline (the assisted default is a marketable limit); show the maker fee as a secondary line only when the series `fee_type = quadratic_with_maker_fees`.

## Definition of Done (v1)

The console is "done" for v1 when, pointed at **demo**:
- a user with no prior Kalshi access can complete M0 onboarding and get validated signed read access;
- the dashboard shows their live demo positions/PnL/balance and live streaming order books + candlestick charts for a watchlist of markets;
- all four signal families produce de-duplicated, severity-ranked alerts in the in-UI feed;
- clicking an alert (or a market) opens a ticket with correct fee/collateral/max-loss/payout/breakeven/edge math (`Decimal`), an advisory risk pre-check, a copy-ready payload, and a best-effort deep link;
- the system survives a WebSocket disconnect and the Thursday 03:00–05:00 ET maintenance window by reconnecting and reconciling against REST, with no wrong data shown;
- flipping the single `KALSHI_ENV` switch to **prod** works for read-only operation with prod credentials.
