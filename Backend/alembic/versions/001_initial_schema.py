"""initial schema - cases, citations, query_records

Revision ID: 001_initial
Revises: None
Create Date: 2026-04-23
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, ARRAY

revision: str = '001_initial'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Cases table
    op.create_table(
        'cases',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('case_id', sa.String(100), unique=True, nullable=False),
        sa.Column('year', sa.Integer(), nullable=False),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('bench', sa.Text(), nullable=True),
        sa.Column('petitioner', sa.Text(), nullable=True),
        sa.Column('respondent', sa.Text(), nullable=True),
        sa.Column('decision_date', sa.Date(), nullable=True),
        sa.Column('disposal_nature', sa.String(100), nullable=True),
        sa.Column('acts_sections', ARRAY(sa.Text()), nullable=True),
        sa.Column('citation', sa.String(200), nullable=True),
        sa.Column('full_text_path', sa.Text(), nullable=True),
        sa.Column('embedding_id', sa.Integer(), nullable=True),
        sa.Column('facts_text', sa.Text(), nullable=True),
        sa.Column('issues_text', sa.Text(), nullable=True),
        sa.Column('reasoning_text', sa.Text(), nullable=True),
        sa.Column('outcome_text', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('idx_cases_case_id', 'cases', ['case_id'])
    op.create_index('idx_cases_year', 'cases', ['year'])

    # Full-text search vector (generated column + GIN index)
    op.execute("""
        ALTER TABLE cases ADD COLUMN text_search_vector tsvector
        GENERATED ALWAYS AS (
            to_tsvector('english', coalesce(title,'') || ' ' || coalesce(facts_text,'') || ' ' || coalesce(issues_text,''))
        ) STORED;
    """)
    op.execute("CREATE INDEX idx_cases_fts ON cases USING GIN(text_search_vector);")

    # Citations table
    op.create_table(
        'citations',
        sa.Column('citing_case_id', sa.String(100), sa.ForeignKey('cases.case_id'), primary_key=True),
        sa.Column('cited_case_id', sa.String(100), sa.ForeignKey('cases.case_id'), primary_key=True),
        sa.Column('citation_count', sa.Integer(), default=1),
    )

    # Query records table
    op.create_table(
        'query_records',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('query_text', sa.Text(), nullable=False),
        sa.Column('status', sa.String(50), nullable=False, server_default='pending'),
        sa.Column('filters', sa.Text(), nullable=True),
        sa.Column('options', sa.Text(), nullable=True),
        sa.Column('result', sa.Text(), nullable=True),
        sa.Column('agent_trace', sa.Text(), nullable=True),
        sa.Column('processing_time_ms', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_cases_fts;")
    op.drop_table('query_records')
    op.drop_table('citations')
    op.drop_table('cases')
