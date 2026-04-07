"""add openai summary fields"""

from alembic import op
import sqlalchemy as sa


revision = "0004_add_openai_summary_fields"
down_revision = "0003_add_cluster_summaries"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("cluster_summaries", sa.Column("model_name", sa.String(length=255), nullable=True))
    op.add_column("cluster_summaries", sa.Column("prompt_version", sa.String(length=100), nullable=True))
    op.add_column("cluster_summaries", sa.Column("structured_payload_json", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("cluster_summaries", "structured_payload_json")
    op.drop_column("cluster_summaries", "prompt_version")
    op.drop_column("cluster_summaries", "model_name")
