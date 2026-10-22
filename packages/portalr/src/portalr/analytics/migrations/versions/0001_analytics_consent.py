"""People's answers to product analytics.

On PostgreSQL, row-level security keeps each transaction to the person it names in
``portalr.user_id``, which :class:`portalr.analytics.sql.SqlConsent` sets: a person's answer is
read and written only as theirs.

Revision ID: 0001
Revises:
Create Date: 2026-10-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "portalr_analytics_consent"
POLICY = "portalr_analytics_consent_person"
PERSON = "current_setting('portalr.user_id', true)"


def upgrade() -> None:
    """Upgrade the schema."""
    op.create_table(
        TABLE,
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("given", sa.Boolean(), nullable=False),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_portalr_analytics_consent")),
    )
    if op.get_bind().dialect.name == "postgresql":
        op.execute(f"ALTER TABLE {TABLE} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {POLICY} ON {TABLE}"
            f" USING (user_id = {PERSON}) WITH CHECK (user_id = {PERSON})"
        )


def downgrade() -> None:
    """Downgrade the schema."""
    if op.get_bind().dialect.name == "postgresql":
        op.execute(f"DROP POLICY {POLICY} ON {TABLE}")
    op.drop_table(TABLE)
