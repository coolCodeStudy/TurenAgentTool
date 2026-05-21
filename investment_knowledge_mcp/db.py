from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import psycopg
from psycopg import Connection
from psycopg.rows import dict_row

from investment_knowledge_mcp.config import PROJECT_ROOT, get_config


SCHEMA_PATH = PROJECT_ROOT / "db" / "schema.sql"


def connect() -> Connection:
    config = get_config()
    if config.database_url:
        return psycopg.connect(config.database_url, row_factory=dict_row)

    return psycopg.connect(
        host=config.postgres_host,
        port=config.postgres_port,
        dbname=config.postgres_db,
        user=config.postgres_user,
        password=config.postgres_password,
        row_factory=dict_row,
    )


@contextmanager
def transaction() -> Iterator[Connection]:
    with connect() as conn:
        with conn.transaction():
            yield conn


def run_schema(schema_path: Path = SCHEMA_PATH) -> None:
    schema_sql = schema_path.read_text(encoding="utf-8")
    with connect() as conn:
        conn.execute(schema_sql)
