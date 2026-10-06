"""add ai metadata, layout metadata, and normalized email unique index

Revision ID: c4e2f9a1b8d7
Revises: 8b2e4f7a1c33
Create Date: 2026-10-06 07:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'c4e2f9a1b8d7'
down_revision = '8b2e4f7a1c33'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Normalize existing user emails and add case-insensitive unique index
    op.execute("UPDATE users SET email = LOWER(TRIM(email))")
    op.create_index(
        'ix_users_lower_email',
        'users',
        [sa.text('LOWER(email)')],
        unique=True,
    )

    # 2. Add AI metadata columns to reports table
    op.add_column('reports', sa.Column('ai_status', sa.String(length=50), nullable=True))
    op.add_column('reports', sa.Column('ai_model_name', sa.String(length=150), nullable=True))
    op.add_column('reports', sa.Column('ai_method_version', sa.String(length=50), nullable=True))
    op.add_column('reports', sa.Column('ai_word_coverage_pct', sa.Float(), nullable=True))
    op.add_column('reports', sa.Column('ai_evaluated_words', sa.Integer(), nullable=True))
    op.add_column('reports', sa.Column('ai_skipped_words', sa.Integer(), nullable=True))
    op.add_column('reports', sa.Column('ai_signal_strength', sa.String(length=50), nullable=True))

    # 3. Mark existing reports as legacy so they are not silently reinterpreted
    op.execute("UPDATE reports SET ai_status = 'legacy' WHERE ai_score IS NOT NULL")

    # 4. Add layout metadata column to submissions table
    op.add_column('submissions', sa.Column('layout_metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    op.drop_column('submissions', 'layout_metadata')
    op.drop_column('reports', 'ai_signal_strength')
    op.drop_column('reports', 'ai_skipped_words')
    op.drop_column('reports', 'ai_evaluated_words')
    op.drop_column('reports', 'ai_word_coverage_pct')
    op.drop_column('reports', 'ai_method_version')
    op.drop_column('reports', 'ai_model_name')
    op.drop_column('reports', 'ai_status')
    op.drop_index('ix_users_lower_email', table_name='users')
