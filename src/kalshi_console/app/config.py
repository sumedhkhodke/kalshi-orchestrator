# src/kalshi_console/app/config.py
"""Application settings with a single demo/prod environment switch."""
from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from kalshi_console.kalshi.endpoints import HOSTS, Env, Hosts


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="KALSHI_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: Env = Env.demo
    api_key_id: str | None = None
    private_key_path: Path | None = None
    secrets_dir: Path = Field(default_factory=lambda: Path.home() / ".kalshi-console")
    http_port: int = 8000

    @property
    def hosts(self) -> Hosts:
        return HOSTS[self.env]

    def resolved_private_key_path(self) -> Path:
        """Explicit path if set, else <secrets_dir>/<env>/private_key.pem."""
        if self.private_key_path is not None:
            return self.private_key_path
        return self.secrets_dir / self.env.value / "private_key.pem"
