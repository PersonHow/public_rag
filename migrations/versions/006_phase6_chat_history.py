""" Phase 6 - 查詢歷史紀錄
create conversation_history

Revision ID: 006
Revises: 005
Create Date: 2026-06-22
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "006_phase6_chat_history"
down_revision = "005_phase5_add_chunk_index"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "conversation_history",
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.company_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.user_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("question", sa.String(500), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("sources", postgresql.JSONB(), nullable=True),
        sa.Column("top_k", sa.Integer(), nullable=False),
        sa.Column("elapsed_ms", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_conversation_history_company_id", "conversation_history", ["company_id"]
    )
    op.create_index(
        "ix_conversation_history_user_id", "conversation_history", ["user_id"]
    )
    op.create_index(
        "ix_conversation_history_company_created",
        "conversation_history",
        ["company_id", "created_at"],
    )
    op.create_index(
        "ix_conversation_history_user_created",
        "conversation_history",
        ["user_id", "created_at"],
    )


def downgrade():
    op.drop_index(
        "ix_conversation_history_user_created", table_name="conversation_history"
    )
    op.drop_index(
        "ix_conversation_history_company_created", table_name="conversation_history"
    )
    op.drop_index(
        "ix_conversation_history_user_id", table_name="conversation_history"
    )
    op.drop_index(
        "ix_conversation_history_company_id", table_name="conversation_history"
    )
    op.drop_table("conversation_history")
