"""Phase 4 — 複合索引補充

Revision ID: 004_phase4_indexes
Revises: 003_phase4_vector
Create Date: 2026-04-24

變更內容：
    1. 新增複合索引 (company_id, code_gcs_path)
       加速 inject-gcs-paths 的 WHERE company_id=? AND code_gcs_path IS NULL 查詢
    2. 新增複合索引 (company_id, product_id)
       加速 product_id 比對查詢
"""
from alembic import op

revision = "004_phase4_indexes"
down_revision = "003_phase4_vector"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_chunks_company_code_path", "chunks", ["company_id", "code_gcs_path"])
    op.create_index("ix_chunks_company_product_id", "chunks", ["company_id", "product_id"])


def downgrade() -> None:
    op.drop_index("ix_chunks_company_product_id", table_name="chunks")
    op.drop_index("ix_chunks_company_code_path", table_name="chunks")
