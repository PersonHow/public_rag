""" Phase 5 - 預覽校正
add chunk_index to chunks

Revision ID: 005
Revises: 004
Create Date: 2026-05-10
"""

from alembic import op
import sqlalchemy as sa

revision = "005_phase5_add_chunk_index"
down_revision = "004_phase4_indexes"
branch_labels = None
depends_on = None



def upgrade():
    op.add_column('chunks',
        sa.Column('chunk_index', sa.Integer(), nullable=True)
    )
    op.create_index(
        'ix_chunks_doc_id_chunk_index',
        'chunks',
        ['doc_id', 'chunk_index']
    )

def downgrade():
    op.drop_index('ix_chunks_doc_id_chunk_index', table_name='chunks')
    op.drop_column('chunks', 'chunk_index')
