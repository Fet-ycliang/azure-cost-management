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


class TagEmbedding(Base):
    """資源 tag 語意向量，供 pgvector 相似性搜尋使用。

    embedding 欄位在首次使用前由 azure_cost_tag_suggest tool 填入。
    向量維度 1536（Azure OpenAI text-embedding-ada-002）。
    """

    __tablename__ = "tag_embeddings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    resource_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    tag_summary: Mapped[str] = mapped_column(Text, nullable=False)
    # embedding 以 JSONB 暫存（安裝 pgvector 擴充後可改為 Vector(1536)）
    embedding_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
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
