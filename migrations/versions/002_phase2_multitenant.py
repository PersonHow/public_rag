"""Phase 2 — 多租戶基礎 schema

Revision ID: 002_phase2_multitenant
Revises: 001_initial
Create Date: 2026-04-14

動工前置：
    DELETE FROM chunks;
    DELETE FROM documents;
    DELETE FROM ingestion_sessions;

變更內容：
    1. CREATE companies
    2. CREATE users（FK → companies）
    3. CREATE company_rules（FK → companies）
    4. CREATE products（FK → companies）
    5. ALTER ingestion_sessions.company_id  VARCHAR → UUID + FK → companies
    6. ALTER documents.company_id           VARCHAR → UUID + FK → companies
    7. ALTER chunks.company_id              VARCHAR → UUID（無 FK，denormalized）
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "002_phase2_multitenant"
down_revision = "001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:

    # ── 1. companies ─────────────────────────────────────────────────────
    op.create_table(
        "companies",
        sa.Column("company_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("industry", sa.String(100), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
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

    # ── 2. users ──────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(300), nullable=False),
        sa.Column("password_hash", sa.String(200), nullable=False),
        sa.Column(
            "role",
            sa.Enum("superadmin", "company_admin", "field_user", name="user_role_enum"),
            nullable=False,
        ),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.company_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
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
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_company_id", "users", ["company_id"])

    # ── 3. company_rules ──────────────────────────────────────────────────
    op.create_table(
        "company_rules",
        sa.Column("rule_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.company_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("field_mapping", postgresql.JSONB(), nullable=False),
        sa.Column("rule_version", sa.String(50), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_company_rules_company_id", "company_rules", ["company_id"])

    # ── 4. products ───────────────────────────────────────────────────────
    op.create_table(
        "products",
        sa.Column("product_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.company_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("canonical_name", sa.String(200), nullable=False),
        sa.Column("product_series", sa.String(100), nullable=True),
        sa.Column("aliases", postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_products_company_id", "products", ["company_id"])

    # ── 5. ingestion_sessions.company_id: VARCHAR → UUID + FK ─────────────
    op.drop_index("ix_ingestion_sessions_company_id", table_name="ingestion_sessions")
    op.drop_column("ingestion_sessions", "company_id")
    op.add_column(
        "ingestion_sessions",
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.company_id", ondelete="CASCADE"),
            nullable=False,
        ),
    )
    op.create_index("ix_ingestion_sessions_company_id", "ingestion_sessions", ["company_id"])

    # ── 6. documents.company_id: VARCHAR → UUID + FK ──────────────────────
    op.drop_index("ix_documents_company_id", table_name="documents")
    op.drop_column("documents", "company_id")
    op.add_column(
        "documents",
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.company_id", ondelete="CASCADE"),
            nullable=False,
        ),
    )
    op.create_index("ix_documents_company_id", "documents", ["company_id"])

    # ── 7. chunks.company_id: VARCHAR → UUID（無 FK，denormalized）─────────
    op.drop_index("ix_chunks_company_id", table_name="chunks")
    op.drop_column("chunks", "company_id")
    op.add_column(
        "chunks",
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
    )
    op.create_index("ix_chunks_company_id", "chunks", ["company_id"])


def downgrade() -> None:
    # chunks.company_id: UUID → VARCHAR
    op.drop_index("ix_chunks_company_id", table_name="chunks")
    op.drop_column("chunks", "company_id")
    op.add_column(
        "chunks",
        sa.Column("company_id", sa.String(100), nullable=False),
    )
    op.create_index("ix_chunks_company_id", "chunks", ["company_id"])

    # documents.company_id: UUID → VARCHAR
    op.drop_index("ix_documents_company_id", table_name="documents")
    op.drop_column("documents", "company_id")
    op.add_column(
        "documents",
        sa.Column("company_id", sa.String(100), nullable=False),
    )
    op.create_index("ix_documents_company_id", "documents", ["company_id"])

    # ingestion_sessions.company_id: UUID → VARCHAR
    op.drop_index("ix_ingestion_sessions_company_id", table_name="ingestion_sessions")
    op.drop_column("ingestion_sessions", "company_id")
    op.add_column(
        "ingestion_sessions",
        sa.Column("company_id", sa.String(100), nullable=False),
    )
    op.create_index("ix_ingestion_sessions_company_id", "ingestion_sessions", ["company_id"])

    op.drop_table("products")
    op.drop_table("company_rules")
    op.drop_table("users")
    op.drop_table("companies")
    op.execute("DROP TYPE IF EXISTS user_role_enum")
