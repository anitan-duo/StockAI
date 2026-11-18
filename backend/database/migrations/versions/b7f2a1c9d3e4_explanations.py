"""Immutable per-prediction explanation artifacts."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "b7f2a1c9d3e4"
down_revision = "a7e4c9d12f5b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "prediction_explanations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "prediction_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("predictions.id", ondelete="CASCADE"),
            unique=True,
            nullable=False,
        ),
        sa.Column("explainer_version", sa.String(20), nullable=False),
        sa.Column("method", sa.String(50), nullable=False),
        sa.Column("model_version", sa.String(100), nullable=True),
        sa.Column("artifact_sha", sa.String(120), nullable=True),
        sa.Column("feature_vector_hash", sa.String(120), nullable=False),
        sa.Column("predicted_direction", sa.String(10), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    )
    op.create_index(
        "ix_prediction_explanations_prediction_id",
        "prediction_explanations",
        ["prediction_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_prediction_explanations_prediction_id", table_name="prediction_explanations")
    op.drop_table("prediction_explanations")
