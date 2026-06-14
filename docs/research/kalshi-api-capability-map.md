# Kalshi API Capability Map — Authoritative Internal Reference

> Build target: a trade orchestrator against Kalshi's Trade API v2 (Predictions). Verified against `docs.kalshi.com` primary sources. Confidence: **high** across all domains. "As of" date for migration-state claims: **2026-06-13**. Uncertain items are explicitly flagged with ⚠️.

---

## 0. Canonical Base URLs, Hosts & Ports (memorize this)

| Purpose | Production | Demo / Sandbox |
|---|---|---|
| **REST (recommended)** | `https://external-api.kalshi.com/trade-api/v2` | `https://external-api.demo.kalshi.co/trade-api/v2` |
| **REST (legacy/alt, still supported)** | `https://api.elections.kalshi.com/trade-api/v2` | `https://demo-api.kalshi.co/trade-api/v2` |
| **WebSocket (recommended)** | `wss://external-api-ws.kalshi.com/trade-api/ws/v2` | `wss://external-api-ws.demo.kalshi.co/trade-api/ws/v2` |
| **WebSocket (legacy/alt)** | `wss://api.elections.kalshi.com/trade-api/ws/v2` ⚠️ WS-support on legacy host unconfirmed in current docs | `wss://demo-api.kalshi.co/trade-api/ws/v2` ⚠️ |
| **Demo sign-up** | — | `https://demo.kalshi.co/sign-up` (`.co`, **not** `.com`) |

**TLD trap:** demo = `kalshi.co`, prod = `kalshi.com`. `demo.kalshi.com` is **not** a valid Kalshi domain.

**Path prefix is constant across all hosts:** `/trade-api/v2` (REST), `/trade-api/ws/v2` (WebSocket).

**Naming trap:** `api.elections.kalshi.com` serves **ALL** markets, not just elections — historical name.

**Credentials are environment-scoped:** demo keys work only on demo; prod keys only on prod. No cross-use.

**FIX hosts** (institutional, Premier+): order entry `mm.fix.elections.kalshi.com` (demo `fix.demo.kalshi.co`); market data `marketdata.fix.elections.kalshi.com` (demo `marketdata.fix.demo.kalshi.co`). Ports: NR 8228, DC 8229, RT 8230, PT 8231, RFQ 8232, MD 8233 (demo mirrors prod ports).

---

## 1. Authentication (RSA-PSS signing) — applies to ALL private REST + WebSocket

### 1.1 The three headers (REST + WS handshake)
```
KALSHI-ACCESS-KEY:       <API Key ID (UUID, public)>
KALSHI-ACCESS-TIMESTAMP: <current Unix time in MILLISECONDS>   # NOT seconds
KALSHI-ACCESS-SIGNATURE: <base64 RSA-PSS/SHA256 signature>     # NOT hex
```

### 1.2 The signed message (exact)
```
message = timestamp_ms + HTTP_METHOD + path
```
- **No separators** between the three parts.
- `path` includes the `/trade-api/v2` prefix and **excludes the query string**.
- REST example: `1703123456789` + `GET` + `/trade-api/v2/portfolio/balance` → `1703123456789GET/trade-api/v2/portfolio/balance`
- WebSocket signs `GET` + `/trade-api/ws/v2` (note **`ws`** in the path), even though the wss host differs from the REST host.
- For `.../portfolio/orders?limit=5` you sign `/trade-api/v2/portfolio/orders` (strip `?limit=5`).

### 1.3 Copy-pasteable signing recipe (Python, cryptography lib)
```python
import base64, time
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

def load_private_key(pem_path: str):
    with open(pem_path, "rb") as f:
        return serialization.load_pem_private_key(f.read(), password=None)

def sign_request(private_key, method: str, path: str):
    """path MUST start with /trade-api/v2 (REST) or be /trade-api/ws/v2 (WS),
       and MUST NOT include a query string."""
    timestamp_ms = str(int(time.time() * 1000))         # MILLISECONDS
    message = (timestamp_ms + method.upper() + path).encode("utf-8")
    signature = private_key.sign(
        message,
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.DIGEST_LENGTH,       # = 32 bytes for SHA256, NOT MAX_LENGTH
        ),
        hashes.SHA256(),
    )
    return {
        "KALSHI-ACCESS-KEY": "<your-api-key-id-uuid>",
        "KALSHI-ACCESS-TIMESTAMP": timestamp_ms,
        "KALSHI-ACCESS-SIGNATURE": base64.b64encode(signature).decode("utf-8"),
    }

# REST:  headers = sign_request(pk, "GET", "/trade-api/v2/portfolio/balance")
# WS:    headers = sign_request(pk, "GET", "/trade-api/ws/v2")   # send at handshake
```

### 1.4 Critical signing parameters (do not deviate)
- Algorithm: **RSA-PSS**, hash **SHA-256**, MGF1 with **SHA-256**, `salt_length = PSS.DIGEST_LENGTH` (**32 bytes**).
- Signature output: **base64**, not hex.
- Timestamp: **milliseconds**. A seconds-timestamp produces an auth error.

### 1.5 Getting API keys
| Endpoint | Method | Path | Notes |
|---|---|---|---|
| Generate API Key (self-serve) | POST | `/trade-api/v2/api_keys/generate` | Kalshi generates the keypair server-side. Body: `name` (req), `scopes` (opt). Returns `api_key_id` + **`private_key` PEM shown ONCE** (cannot be re-fetched). No tier gate. |
| Create API Key (upload own pubkey) | POST | `/trade-api/v2/api_keys` | Body: `name`, `public_key` (PEM), `scopes` (opt). Returns only `api_key_id`. **Restricted to Premier/Market Maker** usage levels → **403** "insufficient API usage level" otherwise. |

Also (standard REST, inferred): `GET /api_keys` (list), `DELETE /api_keys/{id}` (revoke). ⚠️ Not separately re-verified.

**Auth model:** Public market-data endpoints need NO headers. Everything portfolio/order/private — **plus both orderbook endpoints** (see §3) — requires the three headers. There is no session token; signing is per-request.

⚠️ **Uncertain:** allowed clock-skew window (keep NTP-synced); PEM variant (PKCS1 vs PKCS8 unstated — "RSA private key in PEM format" suggests PKCS1); required RSA key size unstated.

---

## 2. Domain Model & Market Mechanics

### 2.1 Hierarchy
**Series → Event → Market.**
- **Series** = recurring template (settlement sources, rules, fee type), e.g. `KXHIGHNY`. Not directly traded.
- **Event** = one real-world occurrence; the basic unit users interact with, e.g. `KXHIGHNY-24JAN01`.
- **Market** = one binary YES/NO contract, e.g. `KXHIGHNY-24JAN01-T60`.
- **Do NOT parse ticker strings to infer relationships** (explicit docs instruction). Use the API fields (`series_ticker`, `event_ticker`).

### 2.2 Binary contract economics
- Each contract pays **$1.00** (`notional_value_dollars`) to the winning side, **$0** to the loser.
- **YES price + NO price = $1.00**, so price ≈ market-implied probability.
- YES and NO are two sides of the **same** orderbook; NO price = $1.00 − YES price.
- Collateral on a long binary = `price × contracts` (= max loss; you cannot lose more than premium).
- **Tick sizes are now market-specific** — read `price_level_structure` and `price_ranges[].step`. The universal 1¢ tick is no longer guaranteed.
- **Fractional trading** (down to 1/100 contract) is live since Jan 2026 (Rulebook 13.1); `fractional_trading_enabled` is deprecated and always `true`.

### 2.3 Lifecycle
`Market.status`: `initialized → inactive → active → closed → determined → disputed → amended → finalized`.
- **determined** = outcome known, not yet paid; **settlement** happens `settlement_timer_seconds` after determination; **finalized** = terminal.
- Only **net** positions are settled.

### 2.4 Mutually-exclusive events & multivariate combos
- `Event.mutually_exclusive = true` → only one market in the event resolves YES (enables collateral return).
- **Multivariate / combo collections**: dynamically build a market from multiple events; resolve to the **PRODUCT** of underlying position values, **capped at $1.00/contract**; **any leg at $0 ⇒ whole combo $0**. Settles ~1–12h after the last underlying resolves. Priced via RFQ; fills not guaranteed.

### 2.5 Collateral return / netting
- `netting_enabled` is **OFF by default**, and is **locked at your FIRST order in an event** (even before any fill) — cannot be changed retroactively for that event.
- When on, reduces required collateral on hedged/mutually-exclusive positions to worst-case loss.

### 2.6 Fees (quadratic)
- **Taker fee** = `ceil_to_cent(0.07 × C × P × (1−P))`
- **Maker fee** = `ceil_to_cent(0.0175 × C × P × (1−P))` (≈¼ of taker)
- `C` = contracts; **`P` = price in DOLLARS (0–1), not cents**. Curve peaks at P=0.50 (taker max **1.75¢/contract**, maker max ≈0.44¢/contract).
- **Rounding is UP on the whole-order total**, not per-contract.
- Maker fees apply **only** to series with `fee_type = quadratic_with_maker_fees` (mainly major sports + some macro). The quadratic maker curve replaced the old flat $0.0025/share maker fee (~July 2025).
- `Series.fee_type` enum: `quadratic | quadratic_with_maker_fees | flat`. `fee_multiplier` (double) scales the coefficient per series; events can override via `fee_type_override` / `fee_multiplier_override`.
- **Live authoritative rates:** `GET /trade-api/v2/margin/fee_tiers` → `maker_fee_rates` / `taker_fee_rates` keyed per market ticker as decimal fractions.

⚠️ **Uncertain:** exact premium-series `fee_multiplier` values (primary fee-schedule PDF was behind a security checkpoint — coefficients corroborated by multiple secondary sources only). Use `/margin/fee_tiers` programmatically.

### 2.7 Combo / multivariate endpoints
| Endpoint | Method | Path | Purpose |
|---|---|---|---|
| Get Multivariate Events | GET | `/trade-api/v2/events/multivariate` | Synthetic combo events (note: plain `/events` excludes multivariate since 2025-12-04). |
| Get Collection | GET | `/trade-api/v2/multivariate_event_collections/{collection_ticker}` | Combo definition; `associated_events[]`, `size_min`/`size_max`, `is_ordered`. |
| Create Market In Collection | POST | `/trade-api/v2/multivariate_event_collections/{collection_ticker}` | Body `selected_markets[]` = `{event_ticker, market_ticker, side}`. |
| Lookup Tickers For Market | GET | `/trade-api/v2/multivariate_event_collections/{collection_ticker}/lookup` | Read-only resolve without creating. |

Deprecated collection fields to avoid: `associated_event_tickers`, `is_single_market_per_event`, `is_all_yes` → use `associated_events[]`.

---

## 3. Market Data (REST)

### 3.1 The fixed-point migration (LOAD-BEARING — applies API-wide)
Kalshi removed legacy integer-cents and integer-count fields on **2026-03-12**. As of today the canonical representations are:
- **Prices** = USD dollar **STRINGS** in `*_dollars` fields, e.g. `"0.4200"` = $0.42, up to **6 decimals**.
- **Contract counts** = fixed-point **STRINGS** in `*_fp` fields, e.g. `"10.00"`, **2 decimals**.
- Renames: `yes_bid → yes_bid_dollars`, `last_price → last_price_dollars`, `volume → volume_fp`, `open_interest → open_interest_fp`, `liquidity → liquidity_dollars` (deprecated, always `"0.0000"`).
- **The "1–99 cents" model is dead** for market-data objects. Parse `*_dollars` as decimals.

### 3.2 Auth model for market data
Most read endpoints are **public (no auth)**: markets, market, trades, events, series, candlesticks, exchange status/schedule/announcements.
**EXCEPTION — both orderbook endpoints REQUIRE auth** (their OpenAPI `security` block overrides the global `security:[]`): `GET /markets/{ticker}/orderbook` and `GET /markets/orderbooks`. The single orderbook is **not** public.

### 3.3 Endpoints
| Endpoint | Method | Path | Purpose / key params & units |
|---|---|---|---|
| Exchange Status | GET | `/exchange/status` | Public. `exchange_active` (bool), `trading_active` (bool), `exchange_estimated_resume_time` (ISO8601, nullable, not guaranteed). |
| Exchange Schedule | GET | `/exchange/schedule` | Public. `standard_hours[]` (per-weekday `open_time`/`close_time` "HH:MM" **ET**), `maintenance_windows[]` (`start_datetime`/`end_datetime`). |
| Exchange Announcements | GET | `/exchange/announcements` | Public. `type` (info\|warning\|error), `message`, `delivery_time`, `status` (active\|inactive). |
| Series List | GET | `/series` | Public. All params optional: `category`, `tags`, `include_product_metadata`, `include_volume`, `min_updated_ts` (unix **seconds**). |
| Series | GET | `/series/{series_ticker}` | Public. `include_volume`. Returns `fee_type`, `fee_multiplier`, `settlement_sources[]`. |
| Events | GET | `/events` | Public. `limit` (1–200, **default 200**), `cursor`, `status` (unopened\|open\|closed\|settled — **no `paused`**), `series_ticker`, `tickers`, `with_nested_markets`, `with_milestones`, `min_close_ts`/`min_updated_ts` (unix sec). |
| Event | GET | `/events/{event_ticker}` | Public. `with_nested_markets`. |
| Markets | GET | `/markets` | Public. `limit` (0–1000, **default 100**), `cursor`, `event_ticker`, `series_ticker`, `tickers`, `status` (unopened\|open\|paused\|closed\|settled), `min/max_close_ts`, `min/max_created_ts`, `min_updated_ts`, `min/max_settled_ts` (all int64 unix **seconds**), `mve_filter` (only\|exclude). |
| Market | GET | `/markets/{ticker}` | Public. Full detail (see §3.4). |
| Market Orderbook | GET | `/markets/{ticker}/orderbook` | **AUTH REQUIRED.** `depth` (0/neg = all, 1–100 = N levels). |
| Multiple Orderbooks | GET | `/markets/orderbooks` | **AUTH REQUIRED.** `tickers` (1–100, repeated query param). Returns an **array** of `{ticker, orderbook_fp}`, not a map. |
| Trades | GET | `/markets/trades` | Public. `ticker` is a **QUERY** param (not path). `limit` (0–1000, default 100), `min_ts`/`max_ts` (unix sec), `is_block_trade`. |
| Market Candlesticks | GET | `/series/{series_ticker}/markets/{ticker}/candlesticks` | Public. Needs **BOTH** path params. `start_ts`,`end_ts` (req, unix sec), `period_interval` (req, **1\|60\|1440** min), `include_latest_before_start`. |
| Batch Candlesticks | GET | `/markets/candlesticks` | Public. `market_tickers` (comma, max 100), `start_ts`,`end_ts`,`period_interval`. **No** series_ticker in path. |
| Event Candlesticks | GET | `/series/{series_ticker}/events/{ticker}/candlesticks` | Public. Aggregated across event markets. Returns `adjusted_end_ts` if window exceeds `maxAggregateCandidates`. |
| Historical Candlesticks | GET | `/historical/markets/{ticker}/candlesticks` | Public. For settled/archived markets removed from live set. **No** series_ticker in path. |

### 3.4 `Get Market` fields (current fixed-point schema)
`ticker, event_ticker, market_type (binary|scalar), yes_sub_title, no_sub_title, created_time, updated_time, open_time, close_time, expected_expiration_time (nullable), latest_expiration_time, settlement_timer_seconds, status, notional_value_dollars, yes_bid_dollars, yes_ask_dollars, yes_bid_size_fp, yes_ask_size_fp, no_bid_dollars, no_ask_dollars, last_price_dollars, previous_yes_bid_dollars, previous_yes_ask_dollars, previous_price_dollars, volume_fp, volume_24h_fp, liquidity_dollars (deprecated '0.0000'), open_interest_fp, result (yes|no|scalar|''), can_close_early, fractional_trading_enabled (deprecated, always true), expiration_value, occurrence_datetime (nullable), settlement_value_dollars (nullable, populated post-determination), settlement_ts (nullable), fee_waiver_expiration_time (nullable), early_close_condition (nullable), strike_type (greater|greater_or_equal|less|less_or_equal|between|functional|custom|structured), floor_strike (nullable), cap_strike (nullable), functional_strike (nullable), custom_strike (nullable), rules_primary, rules_secondary, price_level_structure, price_ranges[{start,end,step} USD strings], mve_collection_ticker (nullable), mve_selected_legs (nullable), is_provisional, exchange_index (default 0)`.
There is **no plain `expiration_time`** field — use `close_time` / `latest_expiration_time`.

### 3.5 Orderbook semantics (critical)
- Response: `{ orderbook_fp: { yes_dollars: [PriceLevel], no_dollars: [PriceLevel] } }`.
- Each `PriceLevel` = 2-element **string** array `[price_dollars, count_fp]`, e.g. `["0.1500","100.00"]`.
- **Only BIDS** are returned for both sides — **no asks**. Compute: best YES ask = `1.00 − highest NO bid`; best NO ask = `1.00 − highest YES bid`. (A YES bid at X = NO ask at 1.00−X.)
- Arrays are sorted **ASCENDING** by price → **the best (highest) bid is the LAST element**.

### 3.6 Candlestick object
`{ end_period_ts (int64 unix sec, inclusive), yes_bid {open/low/high/close _dollars}, yes_ask {OHLC _dollars}, price {open/low/high/close/mean/previous/min/max _dollars — NULLABLE when no trades}, volume_fp, open_interest_fp }`. `yes_bid`/`yes_ask` are always present; `price.*` is nullable for empty periods.

### 3.7 Trade object
`trade_id, ticker, count_fp, yes_price_dollars, no_price_dollars, taker_outcome_side (yes|no), taker_book_side (bid|ask), created_time (RFC3339), is_block_trade`. Legacy `taker_side` deprecated.

### 3.8 Status vocabularies don't match — common bug
- **Markets list filter:** `unopened | open | paused | closed | settled`
- **Events list filter:** `unopened | open | closed | settled` (NO `paused`)
- **`Market.status` field:** `initialized | inactive | active | closed | determined | disputed | amended | finalized`
- Mapping hints: filter `open`→active, `paused`→inactive, `unopened`→initialized, `settled`→finalized.

### 3.9 Timestamp unit trap
**Query filter params** (`min_ts`/`max_ts`, `*_close_ts`, `start_ts`/`end_ts`, `*_created_ts`, candlestick `end_period_ts`) are integer **UNIX SECONDS**. But object time fields (`open_time`, `close_time`, `created_time`, `settlement_ts`) are **RFC3339 strings**.

⚠️ **Uncertain:** numeric value of `maxAggregateCandidates`; exact ticker grammar; default tick size per market; public-endpoint rate limits.

---

## 4. Orders (placement, amend, cancel, lifecycle)

### 4.1 Two coexisting order APIs (same `/trade-api/v2` base)
- **Legacy "V1":** `/portfolio/orders*` — `side=yes|no` + `action=buy|sell`, prices as int cents OR `*_dollars` strings.
- **New "V2" (migration target):** `/portfolio/events/orders*` — single-book `side=bid|ask` (**bid=buy YES, ask=sell YES**), all fixed-point strings, `time_in_force` + `self_trade_prevention_type` **required**.
- **V1 is deprecating** (no earlier than 2026-05-21) with escalating rate-limit costs (10×→15×→50×→100× across May 25 / Jun 1 / Jun 4 2026). Prefer V2.

### 4.2 Endpoints
| Endpoint | Method | Path |
|---|---|---|
| Create Order (V1) | POST | `/portfolio/orders` |
| Create Order (V2) | POST | `/portfolio/events/orders` |
| Batch Create (V1) | POST | `/portfolio/orders/batched` |
| Batch Create (V2) | POST | `/portfolio/events/orders/batched` |
| Batch Cancel (V1) | DELETE | `/portfolio/orders/batched` |
| Batch Cancel (V2) | DELETE | `/portfolio/events/orders/batched` |
| Amend Order | POST | `/portfolio/orders/{order_id}/amend` (V2: `/portfolio/events/orders/{order_id}/amend`) |
| Decrease Order | POST | `/portfolio/orders/{order_id}/decrease` (V2: `/portfolio/events/orders/{order_id}/decrease`) |
| Cancel Order | DELETE | `/portfolio/orders/{order_id}` (V2: `/portfolio/events/orders/{order_id}`) |
| Get Order | GET | `/portfolio/orders/{order_id}` |
| Get Orders | GET | `/portfolio/orders` |

**Note:** Batch Create and Batch Cancel share the **same path** `/portfolio/orders/batched` — distinguished by **POST vs DELETE**.

### 4.3 Create Order V1 — key params
Required: `ticker`, `action` (buy|sell), `side` (yes|no). Optional: `client_order_id`, `count` (int ≥1) OR `count_fp` (string, 0.01 granularity), `yes_price`/`no_price` (**int CENTS 1–99**) OR `yes_price_dollars`/`no_price_dollars` (string dollars, up to 6 dp), `time_in_force` (fill_or_kill|good_till_canceled|immediate_or_cancel), `expiration_ts` (int64 unix **SECONDS**), `buy_max_cost` (int **CENTS** — triggers Fill-or-Kill market buy), `post_only`, `reduce_only`, `self_trade_prevention_type` (taker_at_cross|maker), `order_group_id`, `cancel_order_on_pause`, `subaccount` (0–63, default 0), `exchange_index` (0 only).
**No `type` field in the request** — limit vs market is inferred: price present ⇒ limit; price absent + `buy_max_cost` ⇒ market/FoK buy. `type` (limit|market) appears only in the response.

### 4.4 Create Order V2 — key params
Required: `ticker`, `side` (**bid|ask**), `count` (FixedPointCount string), `price` (FixedPointDollars string — **`"0.0100"` = 1¢ = $0.01**, up to 6 dp), `time_in_force`, `self_trade_prevention_type`. Optional: `client_order_id`, `expiration_time` (unix **SECONDS**), `post_only`, `cancel_order_on_pause`, `reduce_only`, `subaccount`, `order_group_id`, `exchange_index`.
Returns **201**: `order_id`, `client_order_id?`, `fill_count`, `remaining_count`, `average_fill_price` & `average_fee_paid` (when fill>0), **`ts_ms` (epoch MILLISECONDS)**. Errors: 400/401/409/429/500.

### 4.5 Amend / Decrease / Cancel rules
- **Amend** requires `ticker` + `side` + `action` even though you pass `order_id`; **exactly one** of `yes_price`/`no_price`/`yes_price_dollars`/`no_price_dollars`. Queue rule (verbatim): *amend preserves queue position only when it DECREASES size; increasing size or changing price forfeits queue position (back of queue).* Returns `{old_order, order}`.
- **Decrease** is the only edit that lowers quantity. **Exactly one** of `reduce_by(_fp)` (subtract) OR `reduce_to(_fp)` (set remaining). "Cancelling = decreasing to zero."
- **Cancel** does not delete; it zeroes the resting remainder and returns `{order, reduced_by_fp}`. Partial fills retain fill history; order shows `status=canceled`. Cost: 2 tokens.

### 4.6 Get Orders — params
`ticker`, `event_ticker` (comma list, **max 10**), `min_ts`/`max_ts` (unix sec), `status` (**resting|canceled|executed** only — no open/pending/all), `limit` (1–1000, default 100), `cursor`, `subaccount` (0–63; omit = ALL subaccounts).

### 4.7 Order status & idempotency
- **Status enum: `resting | canceled | executed`.** `pending` was removed (announced 2025-11-20, released ~2025-11-27).
- **Idempotency** via `client_order_id` — duplicate submissions are rejected/deduplicated, enabling safe retries. ⚠️ The Create Order reference page does **not** document a hard dedup guarantee/window; treat as best-practice.
- Max **200,000 open orders** per user.

### 4.8 Order response object (V1/Get Order)
`order_id, user_id, client_order_id, ticker, outcome_side (yes|no), book_side (bid|ask), type (limit|market), status, yes_price_dollars, no_price_dollars, fill_count_fp, remaining_count_fp, initial_count_fp, taker_fees_dollars, maker_fees_dollars, taker_fill_cost_dollars, maker_fill_cost_dollars, created_time, last_update_time, expiration_time?, order_group_id?, self_trade_prevention_type?, cancel_order_on_pause, subaccount_number?, exchange_index`. **Deprecated:** `side` (yes|no), `action` (buy|sell) — use `outcome_side`/`book_side`. ⚠️ Removal date conflict: endpoint pages say "May 14, 2026", changelog says "not before May 28, 2026".

### 4.9 Batch behavior
- Body field `orders` = array. Responses: per-item `{client_order_id?, order?, error?}`.
- Costs: batch **create = 10 tokens/order**, batch **cancel = 2 tokens/order**. Whole batch billed `N×cost` and must fit the write bucket atomically (all-or-nothing admission).
- Batch cancel body: current = `orders[]` of `{order_id, subaccount?, exchange_index?}`; deprecated = `ids[]` of strings. Returns per-item `{order_id, reduced_by_fp, order?, error?}`.
- ⚠️ No fixed max batch size — "scales with your tier's write budget." (Old 20-order cap no longer in docs.)

⚠️ **Uncertain:** default `time_in_force` when omitted in V1; whether `immediate_or_cancel` + `expiration_ts` together is rejected (announced, release TBD); whether V1 endpoints are still live today given deprecation timeline. The single Create Order V1 page literally reads "Rate limit: **100 tokens per request**" (legacy cost escalation), vs generic default 10.

---

## 5. Portfolio & Account

### 5.1 Unit trap (CRITICAL — mixed within one payload)
Most positions/fills/orders values are now fixed-point **strings** (`*_dollars` / `*_fp`). But a few fields remain **INTEGER CENTS**:
- `Get Balance`: `balance`, `portfolio_value` (int64 cents)
- `Get Settlements`: `revenue`, `value` (int cents)
- `Get Total Resting Order Value`: `total_resting_order_value` (int cents)

Don't assume one unit across a response.

### 5.2 Endpoints
| Endpoint | Method | Path | Notes |
|---|---|---|---|
| Get Balance | GET | `/portfolio/balance` | `subaccount` (0–63). Returns `balance` (int64 **cents**), `balance_dollars` (string, finer precision — centi-cent $0.0001 for direct members; prefer for exactness), `portfolio_value` (int64 **cents** = positions market value only, NOT balance+positions), `updated_ts` (int64), `balance_breakdown[]` `{exchange_index, balance}`. Scope `read::portfolio_balance`. |
| Get Positions | GET | `/portfolio/positions` | `cursor`, `limit` (1–1000, default 100), `count_filter` (comma; **only** `position`,`total_traded`), `ticker`, `event_ticker` (single), `subaccount`. **No `settlement_status` param.** Returns `market_positions[]` + `event_positions[]` + cursor. |
| Get Fills | GET | `/portfolio/fills` | `ticker`, `order_id`, `min_ts`/`max_ts` (unix ts), `limit` (1–1000), `cursor`, `subaccount`. |
| Get Settlements | GET | `/portfolio/settlements` | `limit`, `cursor`, `ticker`, `event_ticker` (single), `min_ts`/`max_ts`, `subaccount`. |
| Get Orders / Get Order | GET | `/portfolio/orders` , `/portfolio/orders/{order_id}` | Doc pages live under `/api-reference/orders/` (the `/portfolio/get-orders` doc URL 404s) but runtime path is `/portfolio/...`. |
| Get Total Resting Order Value | GET | `/portfolio/summary/total_resting_order_value` | No params. **FCM-members only (rare)** — retail should sum `Get Orders?status=resting` instead. Returns int **cents**. |

### 5.3 Object fields
- **`market_positions[]`:** `ticker, position_fp` (signed: **+ = YES, − = NO**), `market_exposure_dollars, realized_pnl_dollars, total_traded_dollars, fees_paid_dollars, resting_orders_count` (int32, deprecated, **plural spelling**), `last_updated_ts`.
- **`event_positions[]`:** `event_ticker, event_exposure_dollars, realized_pnl_dollars, total_cost_dollars, total_cost_shares_fp, fees_paid_dollars`.
- **Fill:** `fill_id, trade_id (alias), order_id, ticker, market_ticker (alias), outcome_side, book_side, count_fp, yes_price_dollars, no_price_dollars, fee_cost, is_taker, created_time, ts?, subaccount_number?` + deprecated `side`/`action`.
- **Settlement:** `ticker, event_ticker, market_result (yes|no|scalar), yes_count_fp, no_count_fp, yes_total_cost_dollars, no_total_cost_dollars, revenue (int CENTS — winners pay 100¢/contract), fee_cost, value (int CENTS, nullable — payout of one YES contract), settled_time`.

### 5.4 Pagination
Cursor-based: pass returned `cursor` as `?cursor=`; **stop when cursor is null/empty**, NOT when the data array is short. Per-endpoint `limit`: default 100, max 1000. ⚠️ The general pagination guide says "typically 1–100" (conflict); per-endpoint specs are more authoritative.

⚠️ **Uncertain:** `min_ts`/`max_ts` unit (docs say "Unix timestamp", seconds vs ms not stated — historically seconds); `side`/`action` removal date (May 14 vs May 28 2026 conflict).

---

## 6. WebSocket Streaming (Trade API v2)

### 6.1 Connect & auth
- URL: `wss://external-api-ws.kalshi.com/trade-api/ws/v2` (demo `…demo.kalshi.co…`).
- Auth at HTTP handshake with the same three headers; **sign `timestamp_ms + "GET" + "/trade-api/ws/v2"`**.
- One socket multiplexes many subscriptions, each with a server-assigned integer `sid`.
- **Keep-alive:** server sends WebSocket **Ping (0x9)** every **10s** with body `heartbeat`; client must reply **Pong (0xA)**. No JSON heartbeat message.

### 6.2 Command/response protocol
- Client → server: `{id, cmd, params}` where `cmd ∈ {subscribe, unsubscribe, update_subscription}`. `id` is a unique integer ≥0.
- Server → client: `{id?, type, sid, seq?, msg}`.
- **subscribe** `params`: `channels: string[]` (req); market scoping per-channel via `market_ticker` / `market_tickers` (most), `index_ids` (cfbenchmarks_value only), or none (lifecycle channels = all markets). Optional `shard_key`/`shard_factor`.
- **unsubscribe** `params.sids: int[]`.
- **update_subscription** `params`: `sid` or `sids` (exactly one), `action ∈ {add_markets, delete_markets, get_snapshot}`, `market_tickers[]`; optional `send_initial_snapshot` (bool), `use_yes_price` (bool, orderbook only). `get_snapshot` is the gap-recovery path.

### 6.3 Channels
| Channel | type value | Public/Private | Notes |
|---|---|---|---|
| `orderbook_delta` | `orderbook_snapshot`, `orderbook_delta` | **Public** | Snapshot then signed deltas; carries top-level `seq` per sid. |
| `ticker` | `ticker` | Public | `ticker_v2` REMOVED 2026-02-12 — use `ticker`. |
| `trade` | `trade` | Public | Public executed trades. |
| `fill` | `fill` | **Private** | Your fills; `yes_price_dollars` only (no no_price). |
| `market_positions` | `market_position` (singular!) | **Private** | No ts/ts_ms fields. |
| `market_lifecycle_v2` | `market_lifecycle_v2`, `event_lifecycle`, `event_fee_update` | Public | Keeps `_v2`. Timestamps in **SECONDS**. |
| `multivariate_market_lifecycle` | same | Public | Combo lifecycle (added 2026-03-19). |
| `multivariate` | `multivariate_lookup` | Public | **DEPRECATED** (predates RFQs). |
| `communications` | `rfq_*`/`quote_*` | **Private** | Envelope has **NO `seq`**. |
| `order_group_updates` | `order_group_updates` | **Private** | Has `seq`. `event_type ∈ {created,triggered,reset,deleted,limit_updated}`. |
| `user_orders` | `user_order` (singular!) | **Private** | Uses field **`ticker`** (not `market_ticker`); `yes_price_dollars` 4 dp; `created_ts_ms`. |
| `cfbenchmarks_value` | `cfbenchmarks_value` | Public | Subscribe with `index_ids` (e.g. `["BRTI"]` or `["all"]`); market params → error 24. |

### 6.4 Data formats on WS
- Prices = `*_dollars` strings; counts = `*_fp` strings (2 dp; `user_orders` price 4 dp). Legacy integer cent fields removed ~2026-03-12.
- `orderbook_delta.msg`: `market_ticker, market_id, price_dollars, delta_fp (SIGNED), side (yes|no), ts_ms`; optional `client_order_id`/`subaccount` when YOUR order caused it.
- **Timestamp split:** data channels use `*_ts_ms` (**MILLISECONDS**); **lifecycle channels** (`open_ts/close_ts/determination_ts/settled_ts`) use **SECONDS**. Legacy `ts` (sec)/`time` (RFC3339) deprecated.
- `seq` presence varies: present on `orderbook_delta` and `order_group_updates`; **absent** on `communications` and on `subscribed` confirmations. ⚠️ Presence on ticker/trade/fill/market_positions unconfirmed.

### 6.5 Error codes (1–28, confirmed table)
`1 unable to process, 2 params required, 3 channels required, 4 sids required, 5 unknown command, 6 already subscribed, 7 unknown subscription id, 8 unknown channel, 9 authentication required, 10 channel error, 11 invalid parameter, 12 exactly one sid required, 13 unsupported action, 14 market ticker required, 15 action required, 16 market not found, 17 internal error, 18 command timeout, 19–22 shard validation, 23 match ids required, 24 index ids required, 25 buffer overflow, 26 market limit exceeded, 27 too many requests, 28 markets not found.`

⚠️ **Uncertain:** orderbook session caps (announced ~500k subs / 10k cmds/sec effective 2026-06-18); idle/Pong timeout; legacy WS host support; `shard_key`/`shard_factor` semantics.

---

## 7. Rate Limits & Access Tiers

### 7.1 Token-bucket model
- Separate **Read** and **Write** buckets, in **tokens/sec**. Most requests cost **10 tokens** (default). Some cost less (Get Order = 2; Batch Cancel = 2/order). Authoritative deviations: `GET /trade-api/v2/account/endpoint_costs` (includes `default_cost = 10`).
- **Budget = `refill_rate`** (tokens/sec added); **capacity = `bucket_capacity`** (max stored). Sustained rate = budget / cost.

| Tier | Read (tok/s) | Write (tok/s) |
|---|---|---|
| Basic (default on signup) | 200 | 100 |
| Advanced (self-serve) | 300 | 300 |
| Premier | 1,000 | 1,000 |
| Paragon | 2,000 | 2,000 |
| Prime | 4,000 | 4,000 |

- **Burst:** Read buckets and Basic Write hold **1s** of budget (no burst). Write buckets **above Basic** hold up to **2s** → one-time burst up to 2× per-second budget.
- **Tokens ≠ requests.** Basic read 200 tok/s ÷ 10 = ~20 req/s; Basic write 100 ÷ 10 = ~10 order ops/s.

### 7.2 429 behavior
- Body: `{"error": "too many requests"}`. **No `Retry-After`, no `X-RateLimit-*` headers, no penalty/cooldown** — bucket just keeps refilling. Docs: *"Apply exponential backoff on 429."* Min wait = cost / refill_rate.
- ⚠️ Per-endpoint OpenAPI lists 429 under the generic `{code,message,...}` envelope, conflicting with the literal rate_limits body — verify which actually ships.

### 7.3 Tier management endpoints
| Endpoint | Method | Path | Notes |
|---|---|---|---|
| Get Account Limits | GET | `/account/limits` | `usage_tier`, `read`/`write` `{refill_rate, bucket_capacity}`, `grants[]` `{exchange_instance (event_contract\|margined), level, source (volume\|manual), expires_ts (unix SEC, nullable)}`. |
| Get Limits (Perps) | GET | `/account/limits/perps` | Margined lane. ⚠️ No dedicated reference page; schema/numbers unconfirmed. |
| Upgrade Usage Level | POST | `/account/api_usage_level/upgrade` | Basic→**Advanced** only. Requires ≥1 of last 100 Predictions orders created via API. Costs **30 tokens** (Predictions write bucket). 201 success / 403 if criterion unmet. Cannot reach Premier+. |
| Endpoint Costs | GET | `/account/endpoint_costs` | Public. `{default_cost, endpoint_costs:[{method,path,cost}]}`. |
| Volume Progress | GET | `/account/api_usage_level/volume_progress` | ⚠️ Path referenced but no reference page; fields unconfirmed. |

- Volume share = trailing-30-day volume / (prev month exchange volume × 2). Premier/Paragon/Prime earned by volume share (or manual), granted 30 days, renewed daily while qualifying.
- Two exchange lanes: **event_contract (Predictions)** and **margined (perps)** — independent buckets/grants.
- Batch admission is **atomic**: 25 creates need all 250 tokens present on arrival or the whole batch is rejected.

---

## 8. Errors, Ops & Exchange Status

### 8.1 REST error envelope
Generic (per-endpoint OpenAPI): `{code (string), message (string), details? (string, "if available"), service? (string)}`. **HTTP codes:** 400 bad request, 401 unauthorized, 409 conflict (already exists / cannot be modified), 429 rate limited, 500/503/504 server/maintenance.
**Exception:** 429 documented separately as `{"error":"too many requests"}`.
⚠️ `docs.kalshi.com/fix/error-handling` is **FIX-protocol-only** (Reject 35=3, etc.) — NOT the REST reference.

Confirmed order-validation `code` strings (added 2026-01-26): `invalid_order_size, available_balance_too_low, order_id_and_client_order_id_mismatch, order_side_mismatch, order_ticker_mismatch`.

### 8.2 Exchange status / schedule / maintenance
- `GET /exchange/status` → `exchange_active`, `trading_active`, `exchange_estimated_resume_time` (nullable, not guaranteed). Poll this before submitting in degraded conditions.
- **Scheduled maintenance: every Thursday 3:00–5:00 AM ET** = a **trading pause** (cancels allowed, placements/amends blocked). Rare **exchange pause** blocks cancels too. Resting orders remain on book in both. Expect WS disconnects; reconnect after 5:00 AM ET. Kalshi does NOT reset sequence numbers during maintenance — clients should reset on reconnect.

### 8.3 Milestones (communications/event data)
| Endpoint | Method | Path | Notes |
|---|---|---|---|
| Get Milestones | GET | `/milestones` | Public. `limit` (1–500, **required**), `minimum_start_date`, `category`, `competition`, `type`, `related_event_ticker`, `cursor`, `min_updated_ts` (unix **SECONDS**). |
| Get Milestone | GET | `/milestones/{milestone_id}` | Public. |

Object: `id, category, type, start_date, end_date?, title, notification_message, related_event_tickers[], primary_event_tickers[], last_updated_ts (date-time string), source_id?, source_ids{}, details{}`.

### 8.4 Resilience recommendations
- Self-compute backoff (exponential + jitter) on 429; min wait = cost/refill_rate.
- Idempotency: `client_order_id` (orders), `client_transfer_id` (subaccount transfers).
- `expiration_ts` in the **past** is rejected ("must be in the future", since 2025-11-21); can't set `immediate_or_cancel` + `expiration_ts` together.

⚠️ **Uncertain:** the complete REST `code` enum (only fragments published); production 429 body shape (two docs disagree); whether placing during a trading pause returns 409 vs 400 and which code; whether 503/504 are returned during maintenance vs polling `/exchange/status`.

---

## 9. FIX API (institutional; Premier+ or `institutional@kalshi.com`)

- **Protocol: FIXT.1.1 transport + FIX50SP2 application** (`DefaultApplVerID` tag 1137 = `FIX50SP2<9>`). **NOT FIX 4.4** (third-party claims are wrong).
- TLS 1.2+ mandatory (plain TCP prohibited). **One connection per API key.**
- Sessions (TargetCompID → host:port): `KalshiNR` 8228 (no-retransmit, needs `ResetSeqNumFlag=Y`), `KalshiRT` 8230 (retransmit), `KalshiDC` 8229 (drop copy, request-response, 3h lookback, ExecutionReports only), `KalshiPT` 8231 (post-trade/settlement, retransmit), `KalshiRFQ` 8232, `KalshiMD` 8233 (on the `marketdata.fix.*` host). SenderCompID = your API Key UUID.

### 9.1 Logon (35=A)
- `98 EncryptMethod=None<0>`, `108 HeartBtInt` (int >3s), `1137 DefaultApplVerID=FIX50SP2<9>`, `141 ResetSeqNumFlag=Y` (non-retransmit sessions), `96 RawData` = base64 RSA-PSS/SHA256 signature.
- **Pre-hash string** (SOH-joined): `SendingTime ^ MsgType ^ MsgSeqNum ^ SenderCompID ^ TargetCompID`. `SendingTime` must exactly match tag 52 and be within **30s** of server time (else SessionRejectReason 373=10), format `YYYYMMDD-HH:MM:SS.mmm` UTC.
- Optional: `21005 UseDollars=Y`, `20126 ListenerSession=Y` (+`21011 SkipPendingExecReports=Y`), `20200 MessageRetentionPeriod` (≤72h, default 24h, RT/PT only), `8013 CancelOrdersOnDisconnect` (default N).

### 9.2 Order entry
- `NewOrderSingle (35=D)`: `11 ClOrdID, 38 OrderQty, 40 OrdType=2 (Limit ONLY — no market orders), 44 Price (INT CENTS 1–99 by default, or dollars ≤4 dp when UseDollars=Y), 54 Side (1=Buy,2=Sell), 55 Symbol`. Optional `18 ExecInst=6 PostOnly, 59 TimeInForce (0=Day,1=GTC,3=IOC,4=FOK,6=GTD), 126 ExpireTime (req for GTD), 2964 SelfTradePreventionType (1=Taker At Cross default,2=Maker), 21006 CancelOrderOnPause, 21009 MaxExecutionCost (dollars), 79 AllocAccount (0–63), 526 SecondaryClOrdID (order group)`.
- `OrderCancelRequest (35=F)`, `OrderCancelReplaceRequest (35=G)` (increasing qty forfeits queue), `OrderMassCancelRequest (35=q, 530=6)` throttled to **1/sec**.
- `OrderGroupRequest (35=UOG)/Response (35=UOH)`: `20131 OrderGroupAction (1=Create,2=Reset,3=Delete,4=Trigger,5=Update), 20130 OrderGroupID, 20132 ContractsLimit (1–1,000,000)`; scoped per `AllocAccount`; 15s rolling window.
- `UseDollars` affects tags 6/31/44/132/133; subpenny ≤4 dp (e.g. 72.5¢ = `0.725`).

⚠️ **Uncertain:** subpenny min-tick rules; whether MassCancel is restricted to specific sessions; exact maintenance schedule page; FIX Margin API (`/fix-margin/*`) host/port mapping; no published latency SLAs (AWS PrivateLink on request).

---

## 10. SDKs

- **Python:** `kalshi_python_sync` and `kalshi_python_async` — **install `kalshi_python_sync` but `import kalshi_python`**. Use `Configuration` + `KalshiClient`; set `Configuration.api_key_id` and `Configuration.private_key_pem`.
- **TypeScript:** `kalshi-typescript` (axios-based). Classes: **`MarketApi`** (singular, not `MarketsApi`), `OrdersApi`, `PortfolioApi`.
- Published SDKs **v3.20.0** (OpenAPI Generator 7.17.0); **spec is already 3.21.0** — version lag. WebSockets use a **separate `asyncapi.yaml`** (source of truth for WS).
- Legacy `kalshi-python` 2.1.4 is **deprecated**.
- Default host `external-api.kalshi.com`; `api.elections.kalshi.com` still valid; demo `external-api.demo.kalshi.co`.
- **Money trap in SDKs:** responses carry BOTH legacy int-cents (where still present) AND `*_dollars` FixedPointDollars strings — **do not blindly divide by 100**; prefer `*_dollars`.
- Spec download: `GET https://docs.kalshi.com/openapi.yaml` (info.version 3.21.0); also `asyncapi.yaml`, `perps_openapi.yaml`, `perps_asyncapi.yaml`.

⚠️ **Uncertain:** when 3.21.0 SDKs ship; source repo (`Kalshi/exchange-infra`) unconfirmed by primary docs.

---

## 11. Cross-Cutting Cheat Sheet (units, traps, must-knows)

- **Timestamps:** auth header + V2 order `ts_ms` + WS data channels = **MILLISECONDS**. REST query filters (`min_ts`, `start_ts`, `expiration_ts`, etc.) + WS **lifecycle** channels = **SECONDS**. Object datetime fields = **RFC3339 strings**.
- **Money:** market-data/positions/fills/orders → `*_dollars` **dollar strings** (≤6 dp). Still-integer-**cents**: Balance `balance`/`portfolio_value`, Settlement `revenue`/`value`, `total_resting_order_value`, and FIX `Price` (1–99) by default. V1 order `yes_price`/`no_price` + `buy_max_cost` = **cents**; V2 `price` = **dollars** (`"0.0100"`=1¢).
- **Counts:** `*_fp` **strings**, 2 dp (fractional contracts, 0.01 granularity); WS `user_orders` price uses 4 dp.
- **Orderbook:** bids-only both sides; **ascending sort → best bid = LAST**; asks = `1.00 − opposite-side best bid`.
- **Both orderbook REST endpoints REQUIRE auth** despite the rest of market data being public.
- **Sign:** `timestamp_ms + METHOD + path` (no separators, no query string, includes `/trade-api/v2`); RSA-PSS/SHA256, salt=32, base64.
- **Status enums differ** between markets-filter / events-filter / `Market.status` field / order status (`resting|canceled|executed`).
- **Pagination:** stop on null/empty `cursor`, not short arrays. `limit` default 100, max 1000 per-endpoint.
- **Migration was already executed (2026-03-12):** legacy integer fields are GONE. Code on bare `yes_bid`/`volume`/`count` will break.
- **Prefer V2 order API** (`/portfolio/events/orders*`); V1 deprecating with rising token costs.

### Date-anchored migration log (for "is it live yet" decisions; today = 2026-06-13)
- 2025-11-20/27: `pending` status removed. • 2025-11-21: past `expiration_ts` rejected. • 2025-12-04: `/events` excludes multivariate. • 2026-01-22: WS `*_fp` added. • 2026-01-26: granular order-validation error codes. • 2026-02-12: WS `ticker_v2` removed. • 2026-03-12: **legacy integer cent/count fields removed (REST+WS)**. • 2026-03-19: multivariate lifecycle WS channel. • 2026-04-22: `/account/endpoint_costs` public. • 2026-05-05: `metadata_updated` lifecycle event. • 2026-05-07: external-api-ws hosts in docs. • 2026-05-21+: V1 order deprecation begins. • 2026-05-25/06-01/06-04: V1 cost escalation 10×→15×→50×→100×. • 2026-06-04: legacy `/portfolio/orders` = 10× V2 cost. • 2026-06-11: `grants[]` in `/account/limits`. • 2026-06-18 (upcoming): orderbook WS caps ~500k subs / 10k cmds/sec.