"""add cluster summaries"""

from alembic import op
import sqlalchemy as sa


revision = "0003_add_cluster_summaries"
down_revision = "0002_add_source_item_clustering_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cluster_summaries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("cluster_id", sa.String(length=64), nullable=False),
        sa.Column("summary_text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_cluster_summaries_cluster_id"), "cluster_summaries", ["cluster_id"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_cluster_summaries_cluster_id"), table_name="cluster_summaries")
    op.drop_table("cluster_summaries")
