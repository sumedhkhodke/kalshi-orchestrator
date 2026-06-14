# Kalshi Trade Orchestrator — Building Blocks & Key Decisions

Architecture design grounded in the verified Kalshi API research. The orchestrator's job: ingest market data, run strategy/signal logic, route orders and manage their lifecycle, track positions/risk, and continuously reconcile local state against Kalshi's authoritative state.

A few facts from the research dominate every design choice and are referenced throughout:

- **Auth is per-request RSA-PSS/SHA256** over `timestamp(ms) + METHOD + path` (no separators, query stripped). There is no session token; every REST call and the WS handshake must be signed. WS signs `/trade-api/ws/v2`, REST signs `/trade-api/v2/...`.
- **Money/quantity are fixed-point strings now**, not integer cents: `*_dollars` (USD, up to 6 dp) and `*_fp` (contract counts, 2 dp). Legacy integer-cent fields were removed 2026-03-12. A few fields are still integer cents (`balance`, `portfolio_value`, settlement `revenue`/`value`, `total_resting_order_value`).
- **Orderbook returns bids only, sorted ascending**, both sides (`yes_dollars`, `no_dollars`); best bid is the *last* element; a YES bid at X = NO ask at (1.00 − X). Both orderbook REST endpoints require auth.
- **Rate limits are token buckets** (read/write lanes, default 10 tokens/req); 429s carry no `Retry-After`. Legacy `/portfolio/orders*` write endpoints now cost ~10x the V2 `/portfolio/events/orders*` equivalents.
- **Two coexisting order APIs**: V1 (`/portfolio/orders`, yes/no + buy/sell, type inferred) and V2 (`/portfolio/events/orders`, bid/ask single-book, TIF + STP required). V1 is mid-deprecation.
- **WS data uses per-subscription `seq`** for gap detection on `orderbook_delta` and `order_group_updates`; recovery via `update_subscription action=get_snapshot`. Lifecycle channel timestamps are **seconds**; data channels are **ms**.

---

## 1. Core Components

For each: **Responsibility** · **Key API touchpoints** · **What's tricky on Kalshi**.

### 1.1 Auth / Signing Client
**Responsibility.** Load the RSA private key (PEM) + API Key ID, produce the three `KALSHI-ACCESS-*` headers for every REST call and the WS handshake, keep a millisecond clock, and inject headers transparently into the HTTP/WS layers.

**Touchpoints.** All private REST endpoints; `GET /trade-api/ws/v2` handshake; `POST /api_keys/generate` (one-time key bootstrap).

**Tricky on Kalshi.**
- Signed string is `timestamp + METHOD + path` with **no separators**, path **includes** `/trade-api/v2` prefix and **excludes** the query string. A single stray `?limit=5` in the signed path silently breaks auth (401).
- **Timestamp must be ms** (`int(time.time()*1000)`); a seconds value is a common, hard-to-debug 401. Clock skew window is undocumented — keep NTP-synced; a slow clock fails auth.
- WS signs `/trade-api/ws/v2` (with `ws`), **not** `/trade-api/v2` — the host changes but the signed path is fixed.
- `salt_length = PSS.DIGEST_LENGTH` (32 for SHA256), **not** `MAX_LENGTH`; signature is **base64**, not hex. Wrong padding/encoding = silent 401.
- The server-generated private key is shown **once** — bootstrap must persist it immediately and securely.
- Credentials are environment-scoped: demo keys only work on `*.kalshi.co`, prod keys only on `*.kalshi.com`. Mixing them = 401.

### 1.2 REST Gateway / Client
**Responsibility.** Typed wrapper over REST endpoints with: rate-limit-aware throttling (token-bucket accounting per read/write lane), retry with exponential backoff + jitter, fixed-point parsing/serialization, pagination cursor handling, and idempotency-key threading.

**Touchpoints.** Market data (`/markets`, `/markets/{ticker}`, `/markets/{ticker}/orderbook`, `/markets/trades`, candlesticks); portfolio (`/portfolio/balance`, `/positions`, `/fills`, `/settlements`, `/orders`); orders (V1 `/portfolio/orders*`, V2 `/portfolio/events/orders*`); ops (`/exchange/status`, `/exchange/schedule`, `/account/limits`, `/account/endpoint_costs`).

**Tricky on Kalshi.**
- **Local token-bucket mirror is mandatory** because 429 has no `Retry-After` and no headers. Read `GET /account/limits` at startup (`refill_rate`, `bucket_capacity` per lane) and `GET /account/endpoint_costs` to learn non-default per-route costs, then gate sends locally. Batch admission is **atomic** — a 25-order batch needs all 25×10 tokens present on arrival or the whole batch is rejected.
- **Two unit systems in one payload.** Parse `*_dollars`/`*_fp` as `Decimal` (never float — float makes 0.0700 fee math wrong). Keep the handful of integer-cent fields straight.
- **Mixed timestamp units in params vs bodies.** Query filters (`min_ts`, `*_close_ts`, `start_ts`, `expiration_ts`) are **Unix seconds**; the auth header and V2 `ts_ms` are **ms**.
- **Cursor pagination stops on empty cursor, not short page.** Per-endpoint limits differ (markets/trades/orders default 100 max 1000; events default/max 200).
- **V1 vs V2 cost asymmetry:** route writes through V2 (`/portfolio/events/orders`) — V1 single Create now bills ~100 tokens/request vs the default 10, and legacy mutations are 10x.

### 1.3 WebSocket Market-Data Feed Handler (with seq-gap recovery)
**Responsibility.** Maintain one authenticated WS connection, multiplex subscriptions by `sid`, normalize messages, detect sequence gaps, and trigger snapshot recovery. Answer server Pings to stay alive.

**Touchpoints.** Handshake `wss://external-api-ws.kalshi.com/trade-api/ws/v2`; `subscribe`/`unsubscribe`/`update_subscription` commands; channels `orderbook_delta`, `ticker`, `trade` (public) and `fill`, `market_positions`, `user_orders`, `order_group_updates`, `communications` (private).

**Tricky on Kalshi.**
- **Snapshot-then-delta with per-`sid` `seq`.** On a gap, recover via `update_subscription {action: get_snapshot}` (no resubscribe needed) or `send_initial_snapshot`. **`seq` is present on `orderbook_delta` and `order_group_updates` but absent on `communications` and `subscribed` confirmations** — gap logic must be per-channel, not global.
- **Keep-alive is WS-protocol Ping (0x9, body `heartbeat`) every 10s**, answered with Pong (0xA) — there is **no JSON heartbeat**. Most JSON WS libraries auto-Pong, but verify; a missed Pong drops the connection.
- **`delta_fp` is a signed string**; apply against the matching `side` ('yes'|'no') and `price_dollars` level. Quantities are 2-dp strings, not ints.
- **Type names ≠ channel names**: `market_positions` → type `market_position`; `user_orders` → type `user_order` and uses field `ticker` (not `market_ticker`); deprecated `multivariate` → type `multivariate_lookup`.
- **Lifecycle channels are seconds, data channels are ms** — easy to misparse settlement/close timestamps.
- Reconnect after the **Thursday 03:00–05:00 ET maintenance**; the socket will drop and must re-handshake (re-sign) and re-subscribe + re-snapshot every book.

### 1.4 Local Order Book
**Responsibility.** Maintain a per-market replica of resting bid liquidity (both YES and NO sides), expose best bid/ask, mid, depth, and microprice to strategy.

**Touchpoints.** WS `orderbook_delta` (snapshot + deltas); REST `/markets/{ticker}/orderbook` and batch `/markets/orderbooks` for cold-start/reconcile.

**Tricky on Kalshi.**
- **Bids-only model.** There are no ask arrays. Best **YES ask = 1.00 − highest NO bid**; best **NO ask = 1.00 − highest YES bid**. Derive the synthetic ask side yourself.
- **Ascending sort → best bid is the LAST element.** Off-by-one here corrupts every quote.
- **Both orderbook REST endpoints require auth** (their OpenAPI security overrides the otherwise-public market-data root) — your "public data" client still needs signing for books.
- **Per-market tick sizes are not universally 1¢.** Read `price_level_structure` / `price_ranges[].step`; markets can be `linear_cent`, `deci_cent`, or `tapered_deci_cent`, and fractional contracts (0.01) exist. Quoting/rounding logic must be per-market.
- Cross-check the WS-built book against a periodic REST snapshot to catch silent drift.

### 1.5 Order Manager / State Machine
**Responsibility.** Translate strategy intents into API orders, own each order's lifecycle (`resting → executed`/`canceled`), enforce idempotency, and reconcile order state from both REST and WS.

**Touchpoints.** V2 `POST /portfolio/events/orders`, `.../amend`, `.../decrease`, `DELETE .../{order_id}`, batched variants; `GET /portfolio/orders` and `/orders/{order_id}`; WS `user_orders` + `fill`.

**Tricky on Kalshi.**
- **Status enum is just `resting | canceled | executed`** — there is no `pending`/`open`/`partial`. Partial fills stay `resting` with `remaining_count_fp` shrinking; cancel is a *decrease-to-zero* that returns `reduced_by_fp` and flips status to `canceled` (the record is not deleted).
- **Idempotency via `client_order_id`** (generate a UUID per intent) lets you safely retry after a network timeout — but the Create Order reference does **not** formally guarantee server-side dedup over a window. Treat retries as *probably* idempotent and always reconcile by `client_order_id` against `GET /portfolio/orders`.
- **Amend queue mechanics:** only a **size-decrease** preserves queue position; price change or size increase goes to the back. Model this so the strategy knows it's re-queuing.
- **V1↔V2 side semantics differ:** V1 `side=yes|no` + `action=buy|sell`; V2 `side=bid|ask` (bid = buy YES, ask = sell YES). Pick one API (recommend V2) and don't mix.
- **V1 has no `type` field** — limit vs market is inferred (price ⇒ limit; `buy_max_cost` in cents ⇒ FoK market). V2 requires `time_in_force` and `self_trade_prevention_type` explicitly.
- 200,000 open-order ceiling per user; `subaccount` (0–63) and `exchange_index` (only 0) thread through every call.
- A trading **pause** (Thu maintenance) blocks placements/amends but allows cancels; a full exchange pause blocks cancels too — the state machine must know which mode it's in.

### 1.6 Position & PnL Tracker
**Responsibility.** Maintain authoritative positions (market- and event-level), cost basis, realized/unrealized PnL, and fees paid; mark-to-market against the local book.

**Touchpoints.** `GET /portfolio/positions` (`market_positions[]`, `event_positions[]`), `GET /portfolio/fills`, `GET /portfolio/settlements`, `GET /portfolio/balance`; WS `fill` + `market_positions` for incremental updates.

**Tricky on Kalshi.**
- **`position_fp` sign convention:** positive = YES contracts, negative = NO contracts. Event-level aggregates YES+NO.
- **`portfolio_value` = market value of positions only**, not balance+positions — don't double-count for equity.
- **Settlement payout = $1.00/contract** to the winning side; `revenue`/`value` are **integer cents** while cost basis is `*_total_cost_dollars` strings — mixed units in one settlement record.
- **Determination ≠ settlement.** A market is `determined` (outcome known) then settles `settlement_timer_seconds` later; funds move only at settlement. PnL realization timing must follow this, and only **net** positions settle.
- **Quadratic fees** must be modeled to compute true PnL: taker = `ceil_to_cent(0.07·C·P·(1−P))`, maker = `ceil_to_cent(0.0175·C·P·(1−P))`, P in **dollars**, **rounded up on the order total**. Maker fees only apply to `fee_type = quadratic_with_maker_fees` series; confirm live rates via `GET /margin/fee_tiers`.
- **`balance_dollars` carries finer precision** (centi-cent) than integer `balance` for direct members — prefer the string for exactness.

### 1.7 Risk / Limits Engine
**Responsibility.** Pre-trade gate (per-order, per-market, per-event, account-wide exposure caps, max loss, fat-finger price/size bounds, rate-budget headroom) and continuous post-trade monitoring with kill-switch.

**Touchpoints.** Reads from Position Tracker + Balance; can hard-stop the Order Manager; uses `/account/limits` for budget headroom; can deploy `order_group` contract limits and `cancel_order_on_pause` as exchange-side backstops.

**Tricky on Kalshi.**
- **Collateral = price × contracts = max loss** on a long binary (you can't lose more than premium). Netting/`netting_enabled` reduces collateral on hedged/mutually-exclusive positions to worst-case loss — but it's **OFF by default and locked at your first order in an event**, before any fill. The risk engine must decide netting posture *before* the first order and cannot change it retroactively for that event.
- **Exposure must aggregate at event level**, not just market level — mutually-exclusive events mean YES/NO across markets net out, and combos resolve to the **product** of legs (any leg at $0 ⇒ whole combo $0).
- **Rate budget is itself a risk dimension.** A cancel-storm during a fast market can exhaust the write bucket and leave you unable to cancel. Reserve headroom; note cancels (2 tokens) are far cheaper than creates (10).
- **Exchange-side safety nets** exist and should be used: `order_group` auto-cancel on a contract limit (1–1,000,000), `cancel_order_on_pause`, and (FIX) `CancelOrdersOnDisconnect`. Belt-and-suspenders vs your local kill-switch.

### 1.8 Strategy / Signal Interface
**Responsibility.** A clean contract that feeds strategies normalized market data + position/PnL state and receives order intents; isolates strategy logic from transport and lifecycle.

**Touchpoints.** Consumes from Order Book, Trade tape, `ticker`, candlesticks, milestones, `cfbenchmarks_value`; emits intents to the Order Manager.

**Tricky on Kalshi.**
- **Probability semantics are native:** price = implied probability, YES + NO = $1.00. Strategies should reason in probability space and account for the quadratic fee notch at P=0.50 (max 1.75¢/contract taker).
- **Event/market structure matters:** strategies often span multiple markets in a mutually-exclusive event or a multivariate collection; the interface should expose the Series→Event→Market hierarchy (and **never parse tickers** to infer relationships — docs explicitly warn against it).
- **Settlement-driven, not perpetual.** Markets close, determine, and settle on schedules; strategies need lifecycle awareness (`status`, `close_time`, `settlement_timer_seconds`) rather than assuming continuous trading.
- **Milestones channel** (`/milestones`, `min_updated_ts` polling) links real-world events (games, elections) to `related_event_tickers` — a natural signal source the interface should surface.

### 1.9 Reconciliation Loop
**Responsibility.** Periodically (and on reconnect) compare local state — orders, positions, balance — against Kalshi authoritative REST snapshots; resolve divergence (missed fills, ghost orders, partial-fill drift), and re-anchor WS-built state.

**Touchpoints.** `GET /portfolio/orders` (status filter), `/positions`, `/fills` (since last cursor/`min_ts`), `/balance`; orderbook REST snapshots; `/exchange/status`.

**Tricky on Kalshi.**
- **WS is best-effort; REST is truth.** After any disconnect/maintenance, re-pull orders + positions + fills and reconcile by `client_order_id`/`order_id`/`fill_id` before resuming trading. WS `seq` gaps on the book trigger `get_snapshot`; order/position drift triggers REST re-fetch.
- **Fills can arrive on WS, be implied by an order status change, and appear in `/fills`** — dedupe by `fill_id` (with `trade_id` as legacy alias) to avoid triple-counting.
- **Idempotency reconciliation:** after a timed-out create, the order may or may not have landed — reconcile by `client_order_id` rather than blindly resubmitting.
- **Settlement reconciliation:** positions disappear at settlement; pull `/settlements` to attribute realized PnL and confirm `revenue` matches expectation. Archived markets need `/historical/.../candlesticks`.

### 1.10 Persistence / State Store
**Responsibility.** Durable record of orders (with `client_order_id`), fills, positions, balances, signals, config, and an append-only audit/event log for replay and post-mortem.

**Touchpoints.** Internal; sources all of the above. No Kalshi endpoint, but must survive restarts to support idempotent recovery.

**Tricky on Kalshi.**
- **`client_order_id` is your idempotency anchor** — it must be generated *before* the network call and persisted *before* sending, so a crash mid-send is recoverable.
- **Store fixed-point as exact decimals/strings**, never floats; round-trip `*_dollars`/`*_fp` losslessly.
- **Event-sourced WS log** lets you replay book/fill streams to debug seq-gap handling and PnL.
- Keep last-seen `seq` per `sid` and last cursor per portfolio endpoint to resume cleanly.

### 1.11 Scheduler
**Responsibility.** Drive periodic jobs: reconciliation cadence, candlestick polling, token-bucket refill accounting, maintenance-window handling, key/credential checks, and strategy timers.

**Touchpoints.** `/exchange/status`, `/exchange/schedule` (weekly hours + maintenance windows, all ET), `/exchange/announcements`.

**Tricky on Kalshi.**
- **Thursday 03:00–05:00 ET maintenance** is a recurring, known disruption — schedule a graceful "pause trading, hold cancels, expect WS drop, reconcile at 05:00" routine. `exchange_estimated_resume_time` is advisory and can be extended.
- **Trading hours are per-weekday in ET** with possible multiple sessions/day and per-series schedules; the scheduler must gate order submission on `trading_active`/`exchange_active`, not assume 24/7.

### 1.12 Observability
**Responsibility.** Structured logs, metrics (fill rates, latency, slippage, token-budget utilization, WS gap counts, reconciliation deltas), alerting, and a kill-switch surface.

**Touchpoints.** Wraps every component; consumes `/account/limits`, 429 counts, WS error codes.

**Tricky on Kalshi.**
- **Watch the write-token budget as a first-class metric** — 429s have no headers, so you only know you're throttled by your own accounting; alert before exhaustion.
- **WS error codes 1–28** (e.g. 9 auth required, 25 buffer overflow, 26 market limit, 27 too many requests) and **REST `{code,message,details?,service?}`** envelopes should be parsed and dashboarded; the 429 body is the distinct `{"error":"too many requests"}`.
- **Demo vs prod parity gaps** (different TLDs, possibly different liquidity/behavior) should be tagged in every log line so you never confuse environments.

---

## 2. Architecture Styles

### Style A — Single-process async event loop (monolithic bot)
One process (e.g. Python `asyncio` + `kalshi_python_async`, or Node/TS): one WS task, an async REST client, in-memory book/position/risk state, strategies as coroutines, SQLite for persistence.

- **Pros:** Lowest latency (no IPC), simplest to build/deploy/reason about, trivial state sharing, fast iteration. Matches Kalshi's single-WS-connection model naturally. Cheapest to run.
- **Cons:** One crash takes everything down; a slow strategy blocks the event loop (book updates stall); vertical-scaling only; harder to isolate a misbehaving strategy; in-memory state lost on crash unless carefully persisted.
- **Best when:** single/few strategies, one account, retail-to-prosumer scale, you value shipping speed and low latency over horizontal scale.

### Style B — Modular services + message bus
Separate processes/containers — Market-Data service, Order/Execution service, Risk service, Strategy services, Reconciliation service — communicating over a bus (Redis Streams / NATS / Kafka). Persistence in Postgres.

- **Pros:** Fault isolation (a strategy crash doesn't kill the feed); independent scaling/deploy; clean audit via the bus as an event log; multiple strategies/accounts cleanly separated; natural fit for the WS→normalize→fan-out pattern.
- **Cons:** Much more operational complexity; added IPC latency (bad for latency-sensitive quoting); distributed-state and ordering headaches; **the single-WS-per-key and one-connection-per-FIX-key constraints force a single gateway owner anyway** — you don't get to parallelize the feed across keys without multiple API keys; over-engineered for one account.
- **Best when:** multiple uncorrelated strategies, multi-account/subaccount, team ownership, or you need strong isolation and auditability and can tolerate ~ms of bus latency.

### Style C — Library-first SDK + pluggable strategies (framework)
A thin, well-typed core library (signing client, REST gateway, WS handler, book, order manager, risk primitives) exposed as a stable API; strategies are plugins loaded into a host runner. Effectively Style A's internals packaged as reusable modules, deployable as a monolith or wired into Style B later.

- **Pros:** Maximum reuse and testability; strategies are isolated, unit-testable units against a mocked gateway; lets you start monolith (Style A deployment) and graduate to services (Style B) without rewriting core; easiest to demo-first since the core is environment-parametrized.
- **Cons:** Up-front design cost to get the interfaces right; risk of over-abstracting before you know the strategies; plugin isolation is logical, not process-level (a bad plugin can still stall the host unless sandboxed).
- **Best when:** you expect the strategy set to evolve, want clean testing, and want to defer the monolith-vs-services decision.

### Recommendation
**Start with Style C's library-first core, deployed as a Style A single async process, demo-first.** This gives low latency and fast iteration now, clean testability, and a clear seam to peel components into Style B services later **if and only if** multi-strategy isolation or multi-account scale actually materializes. The single-WS-per-key constraint means the market-data feed will be a single owner regardless, so the monolith loses little. Persist aggressively (orders keyed by `client_order_id`, event-sourced WS log) so the in-memory risk of Style A is bounded.

---

## 3. Key Decisions to Settle With the User

Each framed as a question with default options and a recommended default (★).

1. **Language / runtime?**
   Official SDKs exist for **Python** (`kalshi_python_sync` / `kalshi_python_async`, import as `kalshi_python`) and **TypeScript** (`kalshi-typescript`, axios-based). FIX (FIX50SP2) exists for institutional/HFT.
   → ★ **Python async** for fastest build with first-party SDK and rich quant tooling; TypeScript if the team is JS-native; FIX only if sub-ms HFT and Premier+ tier. *(Note: install `kalshi_python_sync` but import `kalshi_python`.)*

2. **REST-only vs REST + WebSocket?**
   → ★ **REST + WS.** WS is needed for real-time book/fills/positions and low latency. **REST-only** is viable only for slow, poll-based strategies (and still must auth-sign everything, and still needs auth for orderbook). Confirm whether the strategy is latency-sensitive.

3. **Fully automated vs assisted (human-in-the-loop)?**
   → ★ **Assisted first, automate after demo validation.** Options: (a) signals-only/alerting, (b) human-approve each order, (c) full auto with kill-switch. Full automation against real money should only follow a clean demo run.

4. **Single-strategy vs multi-strategy / multi-account?**
   → ★ **Single strategy, single account (primary subaccount 0) to start.** Multi-strategy/multi-subaccount (0–63) raises exposure-netting and rate-budget-sharing complexity (and `netting_enabled` is locked per-event at first order). Defer unless required.

5. **Risk controls — what hard limits and kill-switches?**
   Define: max contracts per market/event, max account exposure (collateral $), max daily loss, fat-finger price/size bounds, and whether to use exchange-side `order_group` contract limits + `cancel_order_on_pause`.
   → ★ **Conservative caps + local kill-switch + exchange-side `cancel_order_on_pause`.** Decide netting posture (default OFF) **before** first order per event.

6. **Persistence / state store?**
   → ★ **SQLite (monolith) or Postgres (services) + append-only event log.** Decide durability needs: at minimum, persist `client_order_id` before send for crash-safe idempotency. In-memory-only is acceptable only for throwaway demo bots.

7. **Deployment target?**
   → ★ **Single small always-on VM/container** (the codebase already includes Railway tooling) near US-East to minimize latency to Kalshi and align with ET maintenance. Decide: local dev box vs cloud (Railway/AWS), and whether 24/7 uptime with auto-reconnect across Thursday maintenance is required.

8. **Demo-first vs straight to production?**
   → ★ **Demo-first, mandatory.** Build and validate entirely on `external-api.demo.kalshi.co` (.co TLD), then flip a single config flag to prod. Credentials are environment-scoped and non-transferable. Confirm the user has demo + prod API keys generated.

9. **(If applicable) V1 vs V2 order API and FIX?**
   → ★ **V2 events order API** (`/portfolio/events/orders`) — V1 is mid-deprecation with 10x rate cost. Skip FIX unless institutional HFT + Premier tier.

10. **API usage tier / throughput expectations?**
    Default is **Basic** (read 200 / write 100 tokens/s ≈ 20 reads, 10 writes per second). Self-upgrade to **Advanced** (300/300) is one API call; Premier+ is volume-earned.
    → ★ Confirm expected order/quote rate so the token-bucket throttle and tier are sized correctly.

---

## 4. Kalshi-Specific Risks & Constraints Shaping the Design

- **Signing is unforgiving and easy to get subtly wrong.** Ms (not s) timestamp, no-separator concatenation, signed path includes `/trade-api/v2` and excludes the query, PSS `DIGEST_LENGTH` salt, base64 (not hex), WS signs `/trade-api/ws/v2`. Every one of these is a silent 401. → Centralize signing in one audited module with a self-test that reproduces the docs' canonical example (`1703123456789GET/trade-api/v2/portfolio/balance`). Keep clocks NTP-synced; the skew window is undocumented.

- **Rate-limit tiers with headerless 429s.** No `Retry-After`, no `X-RateLimit-*`, no cooldown — the bucket just refills. → You **must** mirror the token bucket locally (seed from `/account/limits` + `/account/endpoint_costs`), gate sends, and use exponential backoff + jitter on 429. Budget is per-lane (read vs write) and batches are atomic. Cancels (2 tokens) are 5x cheaper than creates (10) — design cancel-heavy strategies accordingly, and **always reserve write headroom so you can cancel in a fast market.** Prefer V2 endpoints (V1 writes cost ~10x).

- **Fixed-point money/quantity migration.** Prices are `*_dollars` strings (≤6 dp), counts are `*_fp` strings (2 dp); legacy integer-cent fields are gone (removed 2026-03-12) — except a few stragglers still in integer cents (`balance`, `portfolio_value`, settlement `revenue`/`value`, `total_resting_order_value`). → Parse everything as `Decimal`, never float; centralize unit handling; unit-test the cents-vs-dollars boundaries. Don't blindly divide by 100.

- **Orderbook quirks.** Bids-only, ascending (best bid = last element), asks are synthetic (1.00 − opposite bid), per-market tick sizes (`linear_cent`/`deci_cent`/`tapered_deci_cent`), fractional contracts, and **auth required even for the book**. → Book-building code must encode all four; a naive "first element = best" or "ask = book.asks" assumption is wrong.

- **Settlement & fees change PnL semantics.** Determination precedes settlement by `settlement_timer_seconds`; only net positions settle; payout is $1/contract. Quadratic taker (0.07) / maker (0.0175) fees, P in dollars, rounded **up on the order total**, maker fees only on `quadratic_with_maker_fees` series, scaled by per-series `fee_multiplier` (verify live via `/margin/fee_tiers`). → PnL/risk must model fees and settlement timing explicitly; don't treat markets as perpetual or fee-free.

- **Collateral & netting lock-in.** `netting_enabled` is OFF by default and **locked at the first order in an event, before any fill, irreversibly for that event.** → The risk engine must set netting posture as a deliberate, up-front per-event decision; you cannot fix it after the first order.

- **WS reliability model.** Best-effort stream, per-`sid` `seq` gaps (only on some channels), server Ping/Pong keep-alive, single connection per key, lifecycle timestamps in seconds vs data in ms, and forced disconnects during Thursday 03:00–05:00 ET maintenance. → Treat REST as truth, WS as fast-but-fallible; build seq-gap `get_snapshot` recovery, auto-reconnect+re-subscribe+re-snapshot, and a full reconciliation pass after every disconnect/maintenance window.

- **Demo vs prod parity.** Demo is `.kalshi.co`, prod is `.kalshi.com` (`demo.kalshi.com` is **not** a valid domain); credentials are environment-scoped and non-transferable; demo liquidity/behavior may differ; demo deposits use sandbox test cards. → Parameterize host + keys by a single environment switch, tag every log/metric with the environment, and never hardcode hosts. Validate the full order lifecycle on demo before any prod capital.

- **Order API in transition + idempotency caveat.** Two coexisting APIs (V1 deprecating, V2 preferred) with **inverted side semantics**, no `pending` status, and `client_order_id` idempotency that is **not contractually guaranteed** to dedup. → Pick V2, never mix side models, and make reconciliation-by-`client_order_id` (not blind resubmit) the recovery primitive after any timed-out write.

- **Maintenance & trading-hours gating.** Markets are not 24/7; trading pauses allow cancels but block placements/amends, full pauses block cancels too. → Gate every send on `/exchange/status` (`trading_active`/`exchange_active`) and schedule around `/exchange/schedule` (ET); use `cancel_order_on_pause` / `order_group` as exchange-side backstops.