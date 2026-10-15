""" 租戶負責人聯絡資訊
companies 加 contact_name / contact_phone / contact_email（皆選填）

Revision ID: 008
Revises: 007
Create Date: 2026-10-01
"""

from alembic import op
import sqlalchemy as sa

revision = "008_company_contact"
down_revision = "007_login_audit_log"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("companies", sa.Column("contact_name", sa.String(100), nullable=True))
    op.add_column("companies", sa.Column("contact_phone", sa.String(50), nullable=True))
    op.add_column("companies", sa.Column("contact_email", sa.String(300), nullable=True))


def downgrade():
    op.drop_column("companies", "contact_email")
    op.drop_column("companies", "contact_phone")
    op.drop_column("companies", "contact_name")
