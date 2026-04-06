"""add pipeline run metadata"""

from alembic import op
import sqlalchemy as sa


revision = "0005_add_pipeline_run_metadata"
down_revision = "0004_add_openai_summary_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("pipeline_runs", sa.Column("watchlist_id", sa.Integer(), nullable=True))
    op.add_column("pipeline_runs", sa.Column("trigger_type", sa.String(length=50), nullable=True))
    op.add_column("pipeline_runs", sa.Column("provider_used", sa.String(length=100), nullable=True))


def downgrade() -> None:
    op.drop_column("pipeline_runs", "provider_used")
    op.drop_column("pipeline_runs", "trigger_type")
    op.drop_column("pipeline_runs", "watchlist_id")
