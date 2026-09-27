"""one submission per student per assignment

Revision ID: 8b2e4f7a1c33
Revises: 155f14e44913
Create Date: 2026-09-10 06:00:00.000000

Adds a DB-level UNIQUE constraint on (assignment_id, student_id) so a student
can never have more than one submission for the same assignment, even under
concurrent requests (the API-level check in the upload route can't fully
prevent a race by itself — this constraint is the actual guarantee).

Before adding the constraint, any *existing* duplicate submissions (from
before this constraint existed) are cleaned up automatically, keeping only
each student's most recent submission per assignment and deleting the
older ones. Deletions cascade to paragraph_embeddings/reports/etc. via the
existing ON DELETE CASCADE foreign keys.

Note: this does not clean up the FAISS index file on disk — any vectors
belonging to a deleted duplicate submission become orphaned (unreferenced)
entries in that file. They're harmless (they'll never be returned as a match
for a real submission's own paragraphs since that submission no longer
exists), but if you want a fully clean slate, delete the FAISS index file
under backend's storage directory and restart the backend — it will be
recreated empty, and existing *valid* submissions' vectors would then need
re-embedding (not handled by this migration).
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '8b2e4f7a1c33'
down_revision = '155f14e44913'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Keep only the newest submission per (assignment_id, student_id); delete
    # the rest so the unique constraint below can be added successfully even
    # on a database that already has duplicates from before this fix.
    op.execute(
        """
        DELETE FROM submissions
        WHERE id IN (
            SELECT id FROM (
                SELECT id,
                       ROW_NUMBER() OVER (
                           PARTITION BY assignment_id, student_id
                           ORDER BY submitted_at DESC
                       ) AS rn
                FROM submissions
            ) ranked
            WHERE rn > 1
        )
        """
    )
    op.create_unique_constraint(
        "uq_submissions_assignment_student", "submissions", ["assignment_id", "student_id"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_submissions_assignment_student", "submissions", type_="unique")
