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
