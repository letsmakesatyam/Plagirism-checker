"""add ai_results table and report AI counter columns

Revision ID: 155f14e44913
Revises: d14eb8117dc1
Create Date: 2026-08-06 01:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '155f14e44913'
down_revision = 'd14eb8117dc1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    ai_label = postgresql.ENUM(
        'LIKELY_HUMAN', 'UNCERTAIN', 'LIKELY_AI', name='ailabel',
    )
    ai_label.create(op.get_bind(), checkfirst=True)
    # create_type=False: already created above; see the comment in
    # 5a7cb1b88041's migration for why this second definition is needed.
    ai_label = postgresql.ENUM(
        'LIKELY_HUMAN', 'UNCERTAIN', 'LIKELY_AI', name='ailabel', create_type=False,
    )

    op.add_column('reports', sa.Column('likely_ai_count', sa.Integer(), nullable=True))
    op.add_column('reports', sa.Column('likely_human_count', sa.Integer(), nullable=True))
    op.add_column('reports', sa.Column('uncertain_count', sa.Integer(), nullable=True))

    op.create_table(
        'ai_results',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('report_id', sa.UUID(), nullable=False),
        sa.Column('paragraph_index', sa.Integer(), nullable=False),
        sa.Column('paragraph_text', sa.Text(), nullable=False),
        sa.Column('ai_probability', sa.Float(), nullable=False),
        sa.Column('label', ai_label, nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['report_id'], ['reports.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_ai_results_report_id'), 'ai_results', ['report_id'], unique=False)
    op.create_index(op.f('ix_ai_results_label'), 'ai_results', ['label'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_ai_results_label'), table_name='ai_results')
    op.drop_index(op.f('ix_ai_results_report_id'), table_name='ai_results')
    op.drop_table('ai_results')
    op.drop_column('reports', 'uncertain_count')
    op.drop_column('reports', 'likely_human_count')
    op.drop_column('reports', 'likely_ai_count')
    postgresql.ENUM(name='ailabel').drop(op.get_bind(), checkfirst=True)
