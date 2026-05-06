"""升級 tag_embeddings.embedding_json（JSONB）→ embedding（vector(1536)）

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-06
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "azure_cost_mcp"


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.execute(
        f"ALTER TABLE {SCHEMA}.tag_embeddings DROP COLUMN IF EXISTS embedding_json"
    )
    op.execute(
        f"ALTER TABLE {SCHEMA}.tag_embeddings ADD COLUMN IF NOT EXISTS embedding vector(1536)"
    )
    # ivfflat 索引需要足夠筆數的資料才能建立（建議 > 1000 筆）
    # 等資料量足夠後再手動執行：
    #   CREATE INDEX ix_tag_embeddings_embedding
    #   ON azure_cost_mcp.tag_embeddings USING ivfflat (embedding vector_cosine_ops)
    #   WITH (lists = 100);


def downgrade() -> None:
    op.execute(
        f"ALTER TABLE {SCHEMA}.tag_embeddings DROP COLUMN IF EXISTS embedding"
    )
    from sqlalchemy.dialects import postgresql
    op.execute(
        f"ALTER TABLE {SCHEMA}.tag_embeddings ADD COLUMN IF NOT EXISTS embedding_json jsonb"
    )
