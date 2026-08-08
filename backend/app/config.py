from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import AnyHttpUrl, Field, RedisDsn, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="VTT_",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "DnD VTT"
    environment: Literal["local", "test", "staging", "production"] = "local"
    api_prefix: str = "/api/v1"
    frontend_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    supabase_url: AnyHttpUrl | None = None
    supabase_publishable_key: str | None = None
    supabase_service_role_key: SecretStr | None = None
    supabase_jwt_audience: str = "authenticated"
    database_url: str | None = None
    redis_url: RedisDsn | None = None

    @property
    def supabase_issuer(self) -> str | None:
        if self.supabase_url is None:
            return None
        return f"{str(self.supabase_url).rstrip('/')}/auth/v1"

    @property
    def supabase_jwks_url(self) -> str | None:
        if self.supabase_issuer is None:
            return None
        return f"{self.supabase_issuer}/.well-known/jwks.json"

    @field_validator(
        "supabase_url",
        "supabase_publishable_key",
        "supabase_service_role_key",
        "database_url",
        "redis_url",
        mode="before",
    )
    @classmethod
    def empty_string_is_unset(cls, value: object) -> object:
        return None if value == "" else value

    def missing_runtime_configuration(self) -> list[str]:
        required = {
            "supabase_url": self.supabase_url,
            "supabase_publishable_key": self.supabase_publishable_key,
            "supabase_service_role_key": self.supabase_service_role_key,
            "database_url": self.database_url,
            "redis_url": self.redis_url,
        }
        return [name for name, value in required.items() if value is None]


@lru_cache
def get_settings() -> Settings:
    return Settings()
