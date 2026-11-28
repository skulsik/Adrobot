from alembic import op
import sqlalchemy as sa


revision = "b7c8d9e0f1a2"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "stream_offers",
        sa.Column("synced_share", sa.Numeric(6, 2), nullable=True),
    )
    op.add_column(
        "stream_offers",
        sa.Column("synced_is_fixed", sa.Boolean(), nullable=True),
    )
    op.add_column(
        "stream_offers",
        sa.Column("synced_is_deleted", sa.Boolean(), nullable=True),
    )

    op.execute("""
        UPDATE stream_offers
        SET
            synced_share = share,
            synced_is_fixed = is_fixed,
            synced_is_deleted = is_deleted
    """)


def downgrade():
    op.drop_column("stream_offers", "synced_is_deleted")
    op.drop_column("stream_offers", "synced_is_fixed")
    op.drop_column("stream_offers", "synced_share")
