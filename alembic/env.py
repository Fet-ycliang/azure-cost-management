"""Alembic 環境配置（同步執行模式，適用於 offline / online migration）。"""
from __future__ import annotations

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# Alembic Config 物件
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 從 lakebase_models 取得 metadata（供 autogenerate 使用）
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from azure_cost_mcp.lakebase_models import Base

target_metadata = Base.metadata

# 從環境變數或 alembic.ini 讀取 DB URL
def get_url() -> str:
    url = os.environ.get("LAKEBASE_PG_URL") or config.get_main_option("sqlalchemy.url", "")
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


# Schema 設定
SCHEMA = os.environ.get(
    "LAKEBASE_SCHEMA_NAME",
    config.get_main_option("lakebase_schema_name", "azure_cost_mcp"),
)


def include_object(obj, name, type_, reflected, compare_to):
    if type_ == "table" and getattr(obj, "schema", None) != SCHEMA:
        return obj.schema is None
    return True


def run_migrations_offline() -> None:
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table_schema=SCHEMA,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        version_table_schema=SCHEMA,
        include_schemas=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_url()
    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
