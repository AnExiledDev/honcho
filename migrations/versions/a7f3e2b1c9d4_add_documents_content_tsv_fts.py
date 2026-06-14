"""add stored content_tsv + GIN index to documents (R2 hybrid FTS arm)

Replaces per-query to_tsvector(content) recomputation on the conclusion
full-text-search arm with a STORED generated tsvector column + GIN index.
Measured: ~286ms FTS over a ~4.7k-row collection -> single-digit ms.

Revision ID: a7f3e2b1c9d4
Revises: e4eba9cfaa6f
Create Date: 2026-06-14

"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy import text

from src.config import settings

# revision identifiers, used by Alembic.
revision: str = "a7f3e2b1c9d4"
down_revision: str | None = "e4eba9cfaa6f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
schema = settings.DB.SCHEMA


def upgrade() -> None:
    # STORED generated column. The 2-arg to_tsvector(regconfig, text) form is
    # IMMUTABLE, which a generated column requires.
    op.execute(
        text(
            f"""
            ALTER TABLE {schema}.documents
            ADD COLUMN IF NOT EXISTS content_tsv tsvector
            GENERATED ALWAYS AS (to_tsvector('english', content)) STORED;
            """
        )
    )
    op.execute(
        text(
            f"""
            CREATE INDEX IF NOT EXISTS ix_documents_content_tsv
            ON {schema}.documents USING gin (content_tsv);
            """
        )
    )


def downgrade() -> None:
    op.execute(text(f"DROP INDEX IF EXISTS {schema}.ix_documents_content_tsv;"))
    op.execute(
        text(f"ALTER TABLE {schema}.documents DROP COLUMN IF EXISTS content_tsv;")
    )
