# src/kalshi_console/app/config.py
"""Application settings with a single demo/prod environment switch."""
from __future__ import annotations

from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from kalshi_console.kalshi.endpoints import HOSTS, Env, Hosts


def _default_secrets_dir() -> Path:
    return Path.home() / ".kalshi-console"


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
    secrets_dir: Path = Field(default_factory=_default_secrets_dir)
    http_port: int = 8000

    @field_validator("api_key_id", "private_key_path", mode="before")
    @classmethod
    def _blank_to_none(cls, v: object) -> object:
        """A copied .env ships these keys present-but-empty; treat "" as unset."""
        if isinstance(v, str) and v.strip() == "":
            return None
        return v

    @field_validator("secrets_dir", mode="before")
    @classmethod
    def _blank_secrets_dir_to_default(cls, v: object) -> object:
        if v is None or (isinstance(v, str) and v.strip() == ""):
            return _default_secrets_dir()
        return v

    @property
    def hosts(self) -> Hosts:
        return HOSTS[self.env]

    def resolved_private_key_path(self) -> Path:
        """Explicit path if set, else <secrets_dir>/<env>/private_key.pem."""
        if self.private_key_path is not None:
            return self.private_key_path
        return self.secrets_dir / self.env.value / "private_key.pem"
