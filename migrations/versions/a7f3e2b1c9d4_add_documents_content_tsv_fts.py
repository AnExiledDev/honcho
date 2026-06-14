"""add GIN expression index on to_tsvector(content) (R2 hybrid FTS arm)

Lets the conclusion full-text-search arm's ``@@`` match use a GIN index
instead of recomputing ``to_tsvector(content)`` over the whole
(observer,observed) collection on every query.
Measured on the live hot collection (~4.7k rows): ~308ms -> ~0.2ms.

Built CONCURRENTLY (outside the migration transaction) so it never takes an
exclusive lock on the live documents table — an earlier STORED generated-column
approach forced a full table rewrite under AccessExclusiveLock and was reverted.

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
    # CONCURRENTLY cannot run inside a transaction block; autocommit_block lets
    # alembic step out of its per-migration transaction for this statement.
    with op.get_context().autocommit_block():
        op.execute(
            text(
                f"""
                CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_documents_content_tsv_expr
                ON {schema}.documents USING gin (to_tsvector('english', content));
                """
            )
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(
            text(
                f"DROP INDEX CONCURRENTLY IF EXISTS {schema}.ix_documents_content_tsv_expr;"
            )
        )
