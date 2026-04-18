from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

import pymysql
from pymysql.cursors import DictCursor

from .config import settings


@contextmanager
def get_conn() -> Iterator[pymysql.Connection]:
    conn = pymysql.connect(
        host=settings.db_host,
        port=settings.db_port,
        user=settings.db_user,
        password=settings.db_password,
        database=settings.db_name,
        autocommit=True,
        cursorclass=DictCursor,
        charset="utf8mb4",
    )
    try:
        yield conn
    finally:
        conn.close()


def fetch_one(sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchone()


def fetch_all(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return list(cur.fetchall())


def execute(sql: str, params: tuple[Any, ...] = ()) -> int:
    with get_conn() as conn:
        with conn.cursor() as cur:
            affected = cur.execute(sql, params)
            return int(affected)
