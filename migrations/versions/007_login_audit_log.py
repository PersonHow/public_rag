""" 登入稽核紀錄
create login_logs + users.last_login_at

Revision ID: 007
Revises: 006
Create Date: 2026-07-29
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "007_login_audit_log"
down_revision = "006_phase6_chat_history"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "login_logs",
        sa.Column("log_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.user_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("email", sa.String(300), nullable=False),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.company_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("event", sa.String(30), nullable=False),
        sa.Column("ip", sa.String(64), nullable=True),
        sa.Column("user_agent", sa.String(500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_login_logs_user_id", "login_logs", ["user_id"])
    op.create_index("ix_login_logs_email_created", "login_logs", ["email", "created_at"])
    op.create_index(
        "ix_login_logs_company_created", "login_logs", ["company_id", "created_at"]
    )
    op.create_index("ix_login_logs_created_at", "login_logs", ["created_at"])

    op.add_column(
        "users",
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade():
    op.drop_column("users", "last_login_at")
    op.drop_index("ix_login_logs_created_at", table_name="login_logs")
    op.drop_index("ix_login_logs_company_created", table_name="login_logs")
    op.drop_index("ix_login_logs_email_created", table_name="login_logs")
    op.drop_index("ix_login_logs_user_id", table_name="login_logs")
    op.drop_table("login_logs")
