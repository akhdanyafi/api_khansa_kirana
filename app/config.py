from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


def _env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value


def _env_int(name: str, default: int) -> int:
    value = _env(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    db_host: str = _env("DB_HOST", "127.0.0.1") or "127.0.0.1"
    db_port: int = _env_int("DB_PORT", 3306)
    db_user: str = _env("DB_USER", "root") or "root"
    db_password: str = _env("DB_PASSWORD", "") or ""
    db_name: str = _env("DB_NAME", "khansa_collection") or "khansa_collection"

    jwt_secret: str = _env("JWT_SECRET", "change-me") or "change-me"
    jwt_algorithm: str = _env("JWT_ALGORITHM", "HS256") or "HS256"
    jwt_expires_days: int = _env_int("JWT_EXPIRES_DAYS", 7)

    cors_origins: str = _env("CORS_ORIGINS", "*") or "*"


settings = Settings()
