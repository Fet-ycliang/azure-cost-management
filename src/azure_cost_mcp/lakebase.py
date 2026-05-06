"""Lakebase（PostgreSQL）非同步連線管理。

適配自 AuroraOps database.py 的 async engine + OAuth token refresh 模式。
需要安裝 lakebase optional deps：
    uv sync --group lakebase

支援兩種連線模式：
1. 靜態 URL 模式（LAKEBASE_PG_URL）：本地開發用，密碼嵌入 URL
2. 動態 OAuth 模式（LAKEBASE_INSTANCE_NAME）：正式環境，每 50 分鐘更新 token
"""
from __future__ import annotations

import asyncio
import logging
import socket
import subprocess
import uuid
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any, AsyncGenerator

if TYPE_CHECKING:
    from .config import Settings

logger = logging.getLogger(__name__)

TOKEN_REFRESH_INTERVAL_SECONDS = 50 * 60


def _check_imports() -> None:
    """確認 lakebase optional deps 已安裝。"""
    try:
        import sqlalchemy  # noqa: F401
        import asyncpg  # noqa: F401
    except ImportError as exc:
        raise ImportError(
            "Lakebase 功能需要額外套件，請執行：uv sync --group lakebase"
        ) from exc


def _resolve_hostname(hostname: str) -> str | None:
    """將 hostname 解析為 IP；Python getaddrinfo 失敗時回退 dig。"""
    try:
        result = socket.getaddrinfo(hostname, 5432)
        if result:
            return result[0][4][0]
    except socket.gaierror:
        pass

    try:
        result = subprocess.run(
            ["dig", "+short", hostname, "A"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        ips = [line for line in result.stdout.strip().split("\n") if line and line[0].isdigit()]
        if ips:
            logger.info(f"Resolved {hostname} -> {ips[0]} via dig")
            return ips[0]
    except Exception as exc:
        logger.debug(f"dig resolution failed for {hostname}: {exc}")

    return None


def _get_workspace_client(settings: Settings) -> Any:
    """取得 Databricks WorkspaceClient（用於動態 OAuth token）。

    優先使用 Settings 中的 DATABRICKS_HOST / DATABRICKS_TOKEN；
    若未設定則退回 SDK 預設（env vars 或 ~/.databrickscfg）。
    """
    try:
        from databricks.sdk import WorkspaceClient
        if settings.databricks_host and settings.databricks_token:
            return WorkspaceClient(
                host=settings.databricks_host,
                token=settings.databricks_token,
            )
        return WorkspaceClient()
    except Exception as exc:
        logger.debug(f"Could not create WorkspaceClient: {exc}")
        return None


def _generate_token(settings: Settings) -> str | None:
    """透過 Databricks SDK 產生 Lakebase OAuth token。

    - Autoscaling 模式：w.postgres.generate_database_credential(endpoint=...)
    - Provisioned 模式（舊版）：w.database.generate_database_credential(instance_names=[...])
    """
    client = _get_workspace_client(settings)
    if not client:
        return None
    try:
        if settings.lakebase_endpoint:
            # Autoscaling 模式
            cred = client.postgres.generate_database_credential(
                endpoint=settings.lakebase_endpoint,
            )
        else:
            # Provisioned 模式（舊版）
            cred = client.database.generate_database_credential(
                request_id=str(uuid.uuid4()),
                instance_names=[settings.lakebase_instance_name or ""],
            )
        return cred.token
    except Exception as exc:
        logger.error(f"Failed to generate Lakebase token: {exc}")
        return None


class LakebaseClient:
    """Lakebase 非同步連線管理器（Settings-driven）。"""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._engine: Any = None
        self._session_maker: Any = None
        self._current_token: str | None = None
        self._token_refresh_task: asyncio.Task | None = None  # type: ignore[type-arg]

    def is_configured(self) -> bool:
        s = self._settings
        return s.lakebase_enabled and bool(
            s.lakebase_pg_url
            or (s.lakebase_endpoint and s.lakebase_host)        # Autoscaling 模式
            or (s.lakebase_instance_name and s.lakebase_database)  # Provisioned 模式（舊版）
        )

    def is_ready(self) -> bool:
        """回傳 engine 是否已完成初始化。"""
        return self._session_maker is not None

    async def init(self) -> None:
        """初始化 async engine 與 session factory。"""
        if not self.is_configured():
            return

        _check_imports()
        from sqlalchemy import event, text
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

        s = self._settings
        import ssl as _ssl
        _ssl_ctx = _ssl.create_default_context()

        connect_args: dict[str, Any] = {
            "ssl": _ssl_ctx,
            "server_settings": {"search_path": s.lakebase_schema},
        }

        if s.lakebase_pg_url:
            url = s.lakebase_pg_url
            if url.startswith("postgresql://"):
                url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        else:
            # 動態 OAuth 模式（Autoscaling 或 Provisioned）
            self._current_token = await asyncio.to_thread(_generate_token, s)
            if not self._current_token:
                raise RuntimeError(
                    f"無法產生 Lakebase OAuth token（endpoint: {s.lakebase_endpoint or s.lakebase_instance_name}）"
                )
            from urllib.parse import quote
            if s.lakebase_endpoint:
                # Autoscaling：host 必填；username 為 Databricks 帳號 email
                host = s.lakebase_host or ""
                username = quote(s.lakebase_user or "", safe="")
                db = s.lakebase_database or "databricks_postgres"
            else:
                # Provisioned（舊版）
                host = s.lakebase_host or f"{s.lakebase_instance_name}.database.us-east-1.cloud.databricks.com"
                username = quote(s.lakebase_instance_name or "", safe="")
                db = s.lakebase_database or "databricks_postgres"
            url = f"postgresql+asyncpg://{username}:{self._current_token}@{host}:5432/{db}"
            # SNI 必須與 URL 中的 hostname 一致，不可用 IP 覆蓋

        self._engine = create_async_engine(
            url,
            pool_size=5,
            max_overflow=5,
            pool_pre_ping=True,
            pool_recycle=3600,
            pool_timeout=10,
            echo=False,
            connect_args=connect_args,
        )

        # 動態 token 注入
        if not s.lakebase_pg_url:
            @event.listens_for(self._engine.sync_engine, "do_connect")
            def _inject_token(dialect, conn_rec, cargs, cparams):
                if self._current_token:
                    cparams["password"] = self._current_token

            self._token_refresh_task = asyncio.create_task(self._token_refresh_loop())

        self._session_maker = async_sessionmaker(
            self._engine,
            expire_on_commit=False,
            autoflush=False,
        )
        logger.info("Lakebase engine initialised")

    async def close(self) -> None:
        if self._token_refresh_task:
            self._token_refresh_task.cancel()
            try:
                await self._token_refresh_task
            except asyncio.CancelledError:
                pass
            self._token_refresh_task = None
        if self._engine:
            await self._engine.dispose()
            self._engine = None
        logger.info("Lakebase engine closed")

    async def _token_refresh_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(TOKEN_REFRESH_INTERVAL_SECONDS)
                new_token = await asyncio.to_thread(_generate_token, self._settings)
                if new_token:
                    self._current_token = new_token
                    logger.info("Lakebase token refreshed")
                else:
                    logger.warning("Lakebase token refresh failed")
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error(f"Token refresh loop error: {exc}")

    @asynccontextmanager
    async def session_scope(self) -> AsyncGenerator[Any, None]:
        """提供帶 commit / rollback 的 async session context manager。"""
        if not self._session_maker:
            raise RuntimeError("LakebaseClient 尚未初始化，請先呼叫 init()")
        session = self._session_maker()
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

    async def run_migrations(self) -> None:
        """程式化執行 Alembic migrations（idempotent）。"""
        if not self.is_configured() or not self._engine:
            return
        try:
            import os
            from pathlib import Path
            from alembic import command
            from alembic.config import Config

            repo_root = Path(__file__).parent.parent.parent
            alembic_ini = repo_root / "alembic.ini"
            if not alembic_ini.exists():
                logger.warning(f"alembic.ini not found at {alembic_ini}, skipping migrations")
                return

            cfg = Config(str(alembic_ini))
            alembic_dir = repo_root / "alembic"
            if alembic_dir.exists():
                cfg.set_main_option("script_location", str(alembic_dir))
            cfg.set_main_option("lakebase_schema_name", self._settings.lakebase_schema)
            await asyncio.to_thread(command.upgrade, cfg, "head")
            logger.info("Lakebase migrations completed")
        except Exception as exc:
            logger.error(f"Lakebase migration failed: {exc}")
            raise

    async def upsert_tag_snapshots(
        self,
        resources: list[dict[str, Any]],
        snapshot_date: str,
    ) -> int:
        """批次 upsert tag_snapshots，回傳寫入筆數。"""
        if not self.is_configured() or not self._session_maker:
            return 0

        from datetime import date as _date
        from sqlalchemy import delete, text
        from .lakebase_models import TagSnapshot

        parsed_date = _date.fromisoformat(snapshot_date) if isinstance(snapshot_date, str) else snapshot_date

        inserted = 0
        async with self.session_scope() as session:
            for r in resources:
                row = TagSnapshot(
                    snapshot_date=parsed_date,
                    subscription_id=r.get("subscriptionId") or "",
                    resource_id=r.get("id") or "",
                    name=r.get("name") or "",
                    type=r.get("type") or "",
                    resource_group=r.get("resourceGroup") or "",
                    location=r.get("location") or "",
                    tags=r.get("tags") or {},
                )
                await session.merge(row)
                inserted += 1
        return inserted

    async def record_tag_changes(
        self,
        diff_entries: list[dict[str, Any]],
        *,
        dry_run: bool,
        rationale: str,
        applied_by: str = "",
    ) -> int:
        """批次寫入 tag_changes audit trail，回傳筆數。"""
        if not self.is_configured() or not self._session_maker:
            return 0

        from .lakebase_models import TagChange

        written = 0
        async with self.session_scope() as session:
            for entry in diff_entries:
                current = entry.get("unchanged", {}).copy()
                current.update({k: v["from"] for k, v in entry.get("modified", {}).items()})
                after = current.copy()
                after.update(entry.get("added", {}))
                after.update({k: v["to"] for k, v in entry.get("modified", {}).items()})
                row = TagChange(
                    resource_id=entry.get("resource_id") or "",
                    before_tags=current,
                    after_tags=after,
                    applied_by=applied_by,
                    rationale=rationale,
                    dry_run=dry_run,
                    status="dry-run" if dry_run else "ok",
                )
                session.add(row)
                written += 1
        return written

    async def find_similar_tagged_resources(
        self,
        resource_type: str,
        resource_group: str,
        *,
        required_keys: list[str],
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """查詢同類型且已完整標記的資源（SQL 相似性，不需 pgvector）。"""
        if not self.is_configured() or not self._session_maker:
            return []

        from sqlalchemy import select, func, text
        from .lakebase_models import TagSnapshot

        async with self.session_scope() as session:
            # 找同類型、同 RG、已完整標記的最新快照
            conditions = [TagSnapshot.type == resource_type]
            for key in required_keys:
                conditions.append(
                    text(f"tags->>'{key}' IS NOT NULL AND tags->>'{key}' != ''")
                )

            stmt = (
                select(TagSnapshot)
                .where(*conditions)
                .order_by(TagSnapshot.snapshot_date.desc(), TagSnapshot.resource_group)
                .limit(limit)
            )
            result = await session.execute(stmt)
            rows = result.scalars().all()
            return [r.to_dict() for r in rows]
