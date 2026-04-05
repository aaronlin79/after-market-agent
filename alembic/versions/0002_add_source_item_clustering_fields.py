"""add source item clustering fields"""

from alembic import op
import sqlalchemy as sa


revision = "0002_add_source_item_clustering_fields"
down_revision = "0001_init"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("source_items", sa.Column("cluster_id", sa.String(length=64), nullable=True))
    op.add_column(
        "source_items",
        sa.Column("is_representative", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index(op.f("ix_source_items_cluster_id"), "source_items", ["cluster_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_source_items_cluster_id"), table_name="source_items")
    op.drop_column("source_items", "is_representative")
    op.drop_column("source_items", "cluster_id")
