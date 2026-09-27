"""add reports and internal_matches tables

Revision ID: 5a7cb1b88041
Revises: 6eea27ec63d2
Create Date: 2026-08-06 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '5a7cb1b88041'
down_revision = '6eea27ec63d2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    report_status = postgresql.ENUM(
        'PENDING', 'GENERATING', 'COMPLETE', 'FAILED', name='reportstatus'
    )
    report_status.create(op.get_bind(), checkfirst=True)
    # create_type=False: the line above already created the type. Without this,
    # create_table()'s own DDL emission tries to CREATE TYPE a second time for
    # the same Column, which fails with "type already exists" even though
    # checkfirst=True was passed to the manual .create() call above — that
    # checkfirst only guards the explicit call, not the table-creation one.
    report_status = postgresql.ENUM(
        'PENDING', 'GENERATING', 'COMPLETE', 'FAILED', name='reportstatus', create_type=False
    )

    op.create_table(
        'reports',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('submission_id', sa.UUID(), nullable=False),
        sa.Column('status', report_status, nullable=False),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('internal_score', sa.Float(), nullable=True),
        sa.Column('internet_score', sa.Float(), nullable=True),
        sa.Column('ai_score', sa.Float(), nullable=True),
        sa.Column('overall_originality_score', sa.Float(), nullable=True),
        sa.Column('paragraphs_checked', sa.Integer(), nullable=True),
        sa.Column('paragraphs_flagged_internal', sa.Integer(), nullable=True),
        sa.Column('generated_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['submission_id'], ['submissions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('submission_id'),
    )
    op.create_index(op.f('ix_reports_status'), 'reports', ['status'], unique=False)

    op.create_table(
        'internal_matches',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('report_id', sa.UUID(), nullable=False),
        sa.Column('source_paragraph_index', sa.Integer(), nullable=False),
        sa.Column('source_paragraph_text', sa.Text(), nullable=False),
        sa.Column('matched_submission_id', sa.UUID(), nullable=False),
        sa.Column('matched_paragraph_index', sa.Integer(), nullable=False),
        sa.Column('matched_paragraph_text', sa.Text(), nullable=False),
        sa.Column('similarity', sa.Float(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['report_id'], ['reports.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['matched_submission_id'], ['submissions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_internal_matches_report_id'), 'internal_matches', ['report_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_internal_matches_report_id'), table_name='internal_matches')
    op.drop_table('internal_matches')
    op.drop_index(op.f('ix_reports_status'), table_name='reports')
    op.drop_table('reports')
    postgresql.ENUM(name='reportstatus').drop(op.get_bind(), checkfirst=True)
