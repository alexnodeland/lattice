"""The initial schema.

Revision ID: 0001
Revises:
Create Date: 2026-10-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade the schema."""
    op.create_table(
        "grantr_tenants",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("live", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_grantr_tenants")),
    )
    op.create_table(
        "grantr_grants",
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("resource_kind", sa.String(), nullable=False),
        sa.Column("resource_workspace", sa.String(), nullable=False),
        sa.Column("resource_id", sa.String(), nullable=False),
        sa.Column("subject_kind", sa.String(), nullable=False),
        sa.Column("subject_workspace", sa.String(), nullable=False),
        sa.Column("subject_id", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint(
            "tenant_id",
            "resource_kind",
            "resource_workspace",
            "resource_id",
            "subject_kind",
            "subject_workspace",
            "subject_id",
            "role",
            name=op.f("pk_grantr_grants"),
        ),
    )
    op.create_index(
        "ix_grantr_grants_subject", "grantr_grants", ["subject_kind", "subject_id", "tenant_id"]
    )
    op.create_index(
        "ix_grantr_grants_workspace", "grantr_grants", ["tenant_id", "resource_workspace"]
    )
    op.create_table(
        "grantr_groups",
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("group_id", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("tenant_id", "group_id", name=op.f("pk_grantr_groups")),
    )
    op.create_table(
        "grantr_group_members",
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("group_id", sa.String(), nullable=False),
        sa.Column("member_kind", sa.String(), nullable=False),
        sa.Column("member_id", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint(
            "tenant_id",
            "group_id",
            "member_kind",
            "member_id",
            name=op.f("pk_grantr_group_members"),
        ),
    )
    op.create_index(
        "ix_grantr_group_members_member",
        "grantr_group_members",
        ["tenant_id", "member_kind", "member_id"],
    )
    op.create_table(
        "grantr_roles",
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("actions", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("tenant_id", "name", name=op.f("pk_grantr_roles")),
    )
    op.create_table(
        "grantr_keys",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("principal_id", sa.String(), nullable=False),
        sa.Column("digest", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_grantr_keys")),
    )
    op.create_index("ix_grantr_keys_tenant", "grantr_keys", ["tenant_id"])
    op.create_table(
        "grantr_audit",
        sa.Column(
            "seq",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("body", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("seq", name=op.f("pk_grantr_audit")),
    )
    op.create_index("ix_grantr_audit_tenant", "grantr_audit", ["tenant_id", "seq"])


def downgrade() -> None:
    """Downgrade the schema."""
    op.drop_index("ix_grantr_audit_tenant", table_name="grantr_audit")
    op.drop_table("grantr_audit")
    op.drop_index("ix_grantr_keys_tenant", table_name="grantr_keys")
    op.drop_table("grantr_keys")
    op.drop_table("grantr_roles")
    op.drop_index("ix_grantr_group_members_member", table_name="grantr_group_members")
    op.drop_table("grantr_group_members")
    op.drop_table("grantr_groups")
    op.drop_index("ix_grantr_grants_workspace", table_name="grantr_grants")
    op.drop_index("ix_grantr_grants_subject", table_name="grantr_grants")
    op.drop_table("grantr_grants")
    op.drop_table("grantr_tenants")
