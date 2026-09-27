"""add internet_sources, internet_source_paragraphs, internet_matches tables

Revision ID: d14eb8117dc1
Revises: 5a7cb1b88041
Create Date: 2026-08-06 00:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'd14eb8117dc1'
down_revision = '5a7cb1b88041'
branch_labels = None
depends_on = None


def upgrade() -> None:
    source_category = postgresql.ENUM(
        'WIKIPEDIA', 'RESEARCH_PAPER', 'BOOK', 'EDUCATIONAL_WEBSITE', 'BLOG', 'GOVERNMENT',
        name='internetsourcecategory',
    )
    source_category.create(op.get_bind(), checkfirst=True)
    # create_type=False: already created above; see the comment in
    # 5a7cb1b88041's migration for why this second definition is needed.
    source_category = postgresql.ENUM(
        'WIKIPEDIA', 'RESEARCH_PAPER', 'BOOK', 'EDUCATIONAL_WEBSITE', 'BLOG', 'GOVERNMENT',
        name='internetsourcecategory', create_type=False,
    )

    op.create_table(
        'internet_sources',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('title', sa.String(length=300), nullable=False),
        sa.Column('url', sa.String(length=1000), nullable=True),
        sa.Column('category', source_category, nullable=False),
        sa.Column('full_text', sa.Text(), nullable=False),
        sa.Column('paragraph_count', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_internet_sources_category'), 'internet_sources', ['category'], unique=False)

    op.create_table(
        'internet_source_paragraphs',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('source_id', sa.UUID(), nullable=False),
        sa.Column('paragraph_index', sa.Integer(), nullable=False),
        sa.Column('paragraph_text', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['source_id'], ['internet_sources.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_internet_source_paragraphs_source_id'), 'internet_source_paragraphs', ['source_id'], unique=False
    )

    op.create_table(
        'internet_matches',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('report_id', sa.UUID(), nullable=False),
        sa.Column('source_paragraph_index', sa.Integer(), nullable=False),
        sa.Column('source_paragraph_text', sa.Text(), nullable=False),
        sa.Column('matched_source_id', sa.UUID(), nullable=False),
        sa.Column('matched_paragraph_index', sa.Integer(), nullable=False),
        sa.Column('matched_paragraph_text', sa.Text(), nullable=False),
        sa.Column('similarity', sa.Float(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['report_id'], ['reports.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['matched_source_id'], ['internet_sources.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_internet_matches_report_id'), 'internet_matches', ['report_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_internet_matches_report_id'), table_name='internet_matches')
    op.drop_table('internet_matches')
    op.drop_index(op.f('ix_internet_source_paragraphs_source_id'), table_name='internet_source_paragraphs')
    op.drop_table('internet_source_paragraphs')
    op.drop_index(op.f('ix_internet_sources_category'), table_name='internet_sources')
    op.drop_table('internet_sources')
    postgresql.ENUM(name='internetsourcecategory').drop(op.get_bind(), checkfirst=True)
