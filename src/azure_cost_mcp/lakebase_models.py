"""Lakebase（PostgreSQL）ORM 模型。

需要安裝 lakebase optional deps：
    uv sync --group lakebase
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Boolean, Date, DateTime, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

try:
    from pgvector.sqlalchemy import Vector
    _HAS_PGVECTOR = True
except ImportError:  # pragma: no cover
    Vector = None  # type: ignore[assignment,misc]
    _HAS_PGVECTOR = False


def _uuid() -> str:
    return str(uuid.uuid4())


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class TagSnapshot(Base):
    """每次 azure_cost_tag_inventory 執行後的資源 tag 快照。"""

    __tablename__ = "tag_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    snapshot_date: Mapped[datetime] = mapped_column(Date, nullable=False, index=True)
    subscription_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    resource_id: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    resource_group: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    location: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    tags: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now
    )

    __table_args__ = (
        Index("ix_tag_snapshots_sub_rg_date", "subscription_id", "resource_group", "snapshot_date"),
        Index("ix_tag_snapshots_resource_id_date", "resource_id", "snapshot_date"),
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "snapshot_date": str(self.snapshot_date),
            "subscription_id": self.subscription_id,
            "resource_id": self.resource_id,
            "name": self.name,
            "type": self.type,
            "resource_group": self.resource_group,
            "location": self.location,
            "tags": self.tags,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class TagChange(Base):
    """每次 azure_cost_tag_apply 執行後的變更紀錄。"""

    __tablename__ = "tag_changes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    applied_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now, index=True
    )
    resource_id: Mapped[str] = mapped_column(Text, nullable=False)
    before_tags: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    after_tags: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    applied_by: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    rationale: Mapped[str] = mapped_column(Text, nullable=False, default="")
    dry_run: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ok")

    __table_args__ = (Index("ix_tag_changes_resource_applied", "resource_id", "applied_at"),)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "applied_at": self.applied_at.isoformat() if self.applied_at else None,
            "resource_id": self.resource_id,
            "before_tags": self.before_tags,
            "after_tags": self.after_tags,
            "applied_by": self.applied_by,
            "rationale": self.rationale,
            "dry_run": self.dry_run,
            "status": self.status,
        }


EMBEDDING_DIM: int = 1024
"""向量維度：databricks-bge-large-en=1024；Ada-002=1536。
可在執行期透過 set_embedding_dim() 修改，需在 Base.metadata.create_all() 之前呼叫。"""


def set_embedding_dim(dim: int) -> None:
    """設定 embedding 維度（需在建立 schema 前呼叫）。"""
    global EMBEDDING_DIM
    EMBEDDING_DIM = dim


def _embedding_column() -> Any:
    """回傳 embedding 欄位類型：有 pgvector 時用 Vector(EMBEDDING_DIM)，否則 JSONB 作 fallback。"""
    if _HAS_PGVECTOR and Vector is not None:
        return mapped_column(Vector(EMBEDDING_DIM), nullable=True)
    return mapped_column(JSONB, nullable=True)  # pragma: no cover


class TagEmbedding(Base):
    """資源 tag 語意向量，供 pgvector 相似性搜尋使用。

    embedding 欄位由 azure_cost_embed_tags tool 填入。
    預設向量維度 1024（databricks-bge-large-en）；Ada-002 請改為 1536。
    pgvector 套件需已安裝（uv sync --group lakebase），且 DB 已啟用 vector extension。
    """

    __tablename__ = "tag_embeddings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    resource_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    tag_summary: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[Any] = _embedding_column()
    snapshot_date: Mapped[datetime] = mapped_column(Date, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "resource_id": self.resource_id,
            "tag_summary": self.tag_summary,
            "snapshot_date": str(self.snapshot_date),
        }
