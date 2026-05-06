"""初始 tag 管理表格：tag_snapshots、tag_changes、tag_embeddings

Revision ID: 0001
Revises:
Create Date: 2026-05-06
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "azure_cost_mcp"


def upgrade() -> None:
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")

    op.create_table(
        "tag_snapshots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("snapshot_date", sa.Date, nullable=False),
        sa.Column("subscription_id", sa.String(255), nullable=False),
        sa.Column("resource_id", sa.Text, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("type", sa.String(255), nullable=False),
        sa.Column("resource_group", sa.String(255), nullable=False),
        sa.Column("location", sa.String(100), nullable=False, server_default=""),
        sa.Column("tags", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        schema=SCHEMA,
    )
    op.create_index("ix_tag_snapshots_snapshot_date", "tag_snapshots", ["snapshot_date"], schema=SCHEMA)
    op.create_index("ix_tag_snapshots_subscription_id", "tag_snapshots", ["subscription_id"], schema=SCHEMA)
    op.create_index("ix_tag_snapshots_type", "tag_snapshots", ["type"], schema=SCHEMA)
    op.create_index("ix_tag_snapshots_resource_group", "tag_snapshots", ["resource_group"], schema=SCHEMA)
    op.create_index(
        "ix_tag_snapshots_sub_rg_date",
        "tag_snapshots",
        ["subscription_id", "resource_group", "snapshot_date"],
        schema=SCHEMA,
    )
    op.create_index(
        "ix_tag_snapshots_resource_id_date",
        "tag_snapshots",
        ["resource_id", "snapshot_date"],
        schema=SCHEMA,
    )

    op.create_table(
        "tag_changes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "applied_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("resource_id", sa.Text, nullable=False),
        sa.Column("before_tags", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("after_tags", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("applied_by", sa.String(255), nullable=False, server_default=""),
        sa.Column("rationale", sa.Text, nullable=False, server_default=""),
        sa.Column("dry_run", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("status", sa.String(20), nullable=False, server_default="ok"),
        schema=SCHEMA,
    )
    op.create_index("ix_tag_changes_applied_at", "tag_changes", ["applied_at"], schema=SCHEMA)
    op.create_index(
        "ix_tag_changes_resource_applied",
        "tag_changes",
        ["resource_id", "applied_at"],
        schema=SCHEMA,
    )

    op.create_table(
        "tag_embeddings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("resource_id", sa.Text, nullable=False),
        sa.Column("tag_summary", sa.Text, nullable=False),
        sa.Column("embedding_json", postgresql.JSONB, nullable=True),
        sa.Column("snapshot_date", sa.Date, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        schema=SCHEMA,
    )
    op.create_index("ix_tag_embeddings_resource_id", "tag_embeddings", ["resource_id"], schema=SCHEMA)
    op.create_index("ix_tag_embeddings_snapshot_date", "tag_embeddings", ["snapshot_date"], schema=SCHEMA)


def downgrade() -> None:
    op.drop_table("tag_embeddings", schema=SCHEMA)
    op.drop_table("tag_changes", schema=SCHEMA)
    op.drop_table("tag_snapshots", schema=SCHEMA)
