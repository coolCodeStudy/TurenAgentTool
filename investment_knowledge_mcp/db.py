from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import psycopg
from psycopg import Connection
from psycopg.rows import dict_row

from investment_knowledge_mcp.config import PROJECT_ROOT, get_config


SCHEMA_PATH = PROJECT_ROOT / "db" / "schema.sql"


def connect(*, connect_timeout_seconds: int | None = None) -> Connection:
    config = get_config()
    connection_options = (
        {"connect_timeout": int(connect_timeout_seconds)}
        if connect_timeout_seconds is not None
        else {}
    )
    if config.database_url:
        return psycopg.connect(
            config.database_url,
            row_factory=dict_row,
            **connection_options,
        )

    return psycopg.connect(
        host=config.postgres_host,
        port=config.postgres_port,
        dbname=config.postgres_db,
        user=config.postgres_user,
        password=config.postgres_password,
        row_factory=dict_row,
        **connection_options,
    )


@contextmanager
def transaction(*, connect_timeout_seconds: int | None = None) -> Iterator[Connection]:
    connection = (
        connect()
        if connect_timeout_seconds is None
        else connect(connect_timeout_seconds=connect_timeout_seconds)
    )
    with connection as conn:
        with conn.transaction():
            yield conn


def run_schema(schema_path: Path = SCHEMA_PATH) -> None:
    schema_sql = schema_path.read_text(encoding="utf-8")
    with connect() as conn:
        conn.execute(schema_sql)
