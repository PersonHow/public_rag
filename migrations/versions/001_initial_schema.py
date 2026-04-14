"""Initial Phase 1 schema

Revision ID: 001_initial
Revises:
Create Date: 2026-03-26
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── ingestion_sessions ───────────────────────────────────────────────
    op.create_table(
        "ingestion_sessions",
        sa.Column("session_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", sa.String(100), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending_preview", "confirmed", "processing", "done", "failed",
                name="session_status_enum",
            ),
            nullable=False,
            server_default="pending_preview",
        ),
        sa.Column("fail_reason", sa.String(500), nullable=True),
        sa.Column("preview_confirmed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("rule_version_used", sa.String(50), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_ingestion_sessions_company_id", "ingestion_sessions", ["company_id"])

    # ── documents ────────────────────────────────────────────────────────
    op.create_table(
        "documents",
        sa.Column("doc_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", sa.String(100), nullable=False),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ingestion_sessions.session_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("filename", sa.String(500), nullable=False),
        sa.Column("doc_type", sa.String(20), nullable=False),
        # 更新版決策 2：gcs_raw_path NOT NULL
        sa.Column("gcs_raw_path", sa.String(1000), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="uploaded"),
        # OCR confidence（掃描 PDF 才有值）
        sa.Column("min_confidence", sa.Float(), nullable=True),
        sa.Column("has_low_confidence", sa.Boolean(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_documents_company_id", "documents", ["company_id"])
    op.create_index("ix_documents_session_id", "documents", ["session_id"])

    # ── chunks（19 欄位）────────────────────────────────────────────────
    op.create_table(
        "chunks",
        # 系統欄位（NOT NULL）
        sa.Column("chunk_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "doc_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.doc_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("company_id", sa.String(100), nullable=False),
        sa.Column("doc_type", sa.String(20), nullable=False),
        sa.Column("rule_version", sa.String(50), nullable=False),
        sa.Column("embed_text", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        # 規格組（Nullable）
        sa.Column("product_name", sa.String(200), nullable=True),
        sa.Column("product_id", sa.String(100), nullable=True),
        sa.Column("material", sa.String(200), nullable=True),
        sa.Column("dimensions", sa.String(200), nullable=True),
        sa.Column("specs", sa.Text(), nullable=True),
        # 知識組（Nullable）
        sa.Column("situation", sa.Text(), nullable=True),
        sa.Column("action", sa.Text(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("applies_to", sa.Text(), nullable=True),
        # 通用（Nullable）
        sa.Column("case_id", sa.String(100), nullable=True),
        # 附件（後處理注入）
        sa.Column("code_gcs_path", sa.String(1000), nullable=True),
        sa.Column("drawing_gcs_path", sa.String(1000), nullable=True),
    )
    op.create_index("ix_chunks_company_id", "chunks", ["company_id"])
    op.create_index("ix_chunks_doc_id", "chunks", ["doc_id"])


def downgrade() -> None:
    op.drop_table("chunks")
    op.drop_table("documents")
    op.drop_table("ingestion_sessions")
    op.execute("DROP TYPE IF EXISTS session_status_enum")
