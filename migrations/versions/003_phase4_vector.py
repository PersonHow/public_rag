"""Phase 4 — 向量寫入 schema

Revision ID: 003_phase4_vector
Revises: 002_phase2_multitenant
Create Date: 2026-04-23

變更內容：
    1. ALTER chunks: 新增 face VARCHAR(100) nullable
       加工面向原始術語（第一面 / 第二面），保留各公司術語多租戶彈性
"""
from alembic import op
import sqlalchemy as sa

revision = "003_phase4_vector"
down_revision = "002_phase2_multitenant"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "chunks",
        sa.Column("face", sa.String(100), nullable=True),
    )
    op.create_index("ix_chunks_face", "chunks", ["face"])


def downgrade() -> None:
    op.drop_index("ix_chunks_face", table_name="chunks")
    op.drop_column("chunks", "face")
