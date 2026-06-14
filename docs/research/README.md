# Kalshi API Research

Verified exploration of the Kalshi Trade API v2, produced 2026-06-13 by a multi-agent
sweep (11 domain explorers + adversarial verifiers, cross-checked against
`docs.kalshi.com`). All domains returned **high** confidence.

| File | What's in it |
|------|--------------|
| [`kalshi-api-capability-map.md`](./kalshi-api-capability-map.md) | The authoritative reference: base URLs, RSA-PSS signing recipe, every endpoint group (market data, orders, portfolio), WebSocket channels, fees, rate limits, units cheat-sheet, migration log. |
| [`kalshi-orchestrator-architecture.md`](./kalshi-orchestrator-architecture.md) | Orchestrator building blocks (12 components), 3 architecture styles + recommendation, key decisions, Kalshi-specific risks. |
| [`kalshi-api-open-questions.json`](./kalshi-api-open-questions.json) | Missing areas, unverified claims, and recommended demo experiments to resolve them. |
| [`kalshi-api-domain-findings.json`](./kalshi-api-domain-findings.json) | Raw structured findings per domain (endpoints, concepts, gotchas, sources). |

## The load-bearing facts (read before writing any code)

- **Auth:** per-request RSA-PSS/SHA-256 over `timestamp_ms + METHOD + path` (no separators,
  query stripped, salt=32, base64). Timestamp is **milliseconds**. WS handshake signs
  `/trade-api/ws/v2`. Every detail is a silent 401 if wrong.
- **Money/quantity are fixed-point strings now** (`*_dollars` ≤6dp, `*_fp` 2dp); legacy
  integer-cent fields were removed 2026-03-12. A few stragglers stay integer cents
  (`balance`, `portfolio_value`, settlement `revenue`/`value`). Parse as `Decimal`, never float.
- **Orderbook is bids-only, sorted ascending** (best bid = last element); asks are synthetic
  (`1.00 − opposite-side best bid`); both orderbook REST endpoints require auth.
- **Rate limits are token buckets** with headerless 429s — mirror the bucket locally.
- **Use the V2 order API** (`/portfolio/events/orders`); V1 is mid-deprecation with rising cost.
- **WS is best-effort, REST is truth** — per-`sid` `seq` gaps recover via `get_snapshot`;
  reconcile against REST after every disconnect / Thursday 03:00–05:00 ET maintenance.
- **Demo = `kalshi.co`, prod = `kalshi.com`**; credentials are environment-scoped.
