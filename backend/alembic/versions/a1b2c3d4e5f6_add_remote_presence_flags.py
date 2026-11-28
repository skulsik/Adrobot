"""add remote presence flags

Revision ID: a1b2c3d4e5f6
Revises: 04f0354571b9
"""

from alembic import op
import sqlalchemy as sa


revision = "a1b2c3d4e5f6"
down_revision = "04f0354571b9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "campaigns",
        sa.Column(
            "is_present_in_keitaro",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )

    op.add_column(
        "streams",
        sa.Column(
            "is_present_in_keitaro",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )

    op.alter_column(
        "campaigns",
        "is_present_in_keitaro",
        server_default=None,
    )

    op.alter_column(
        "streams",
        "is_present_in_keitaro",
        server_default=None,
    )


def downgrade() -> None:
    op.drop_column("streams", "is_present_in_keitaro")
    op.drop_column("campaigns", "is_present_in_keitaro")
