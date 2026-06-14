# scripts/onboard.py
"""Convenience shim: `python scripts/onboard.py <command>`."""
from kalshi_console.onboarding.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
