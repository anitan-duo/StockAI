"""Historical scenario lab: scenarios, attempts, streaks, diagnoses."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "a7e4c9d12f5b"
down_revision = "9f3c1a2b7d4e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scenarios",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("scenario_key", sa.String(200), unique=True, nullable=False),
        sa.Column("instrument_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("instruments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("decision_ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("horizon", sa.String(10), nullable=False, server_default="1d"),
        sa.Column("target_version", sa.String(50), nullable=False, server_default="v1-h1d-0.5pct"),
        sa.Column("data_cutoff", sa.DateTime(timezone=True), nullable=False),
        sa.Column("feature_schema_version", sa.String(20), nullable=False, server_default="v1"),
        sa.Column("split", sa.String(20), nullable=False, server_default="train"),
        sa.Column("seen_by_model", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("used_for_training", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("outcome_status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("unavailable_reason", sa.Text(), nullable=True),
        sa.Column("snapshot_hash", sa.String(120), nullable=True),
    )
    op.create_index("ix_scenarios_key", "scenarios", ["scenario_key"])
    op.create_index("ix_scenarios_instrument", "scenarios", ["instrument_id"])
    op.create_index("ix_scenarios_split", "scenarios", ["split"])

    op.create_table(
        "challenge_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("scenario_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False),
        sa.Column("experiment_id", sa.String(50), nullable=False),
        sa.Column("model_version", sa.String(100), nullable=False, server_default="ensemble-v1.0"),
        sa.Column("artifact_sha", sa.String(120), nullable=True),
        sa.Column("horizon", sa.String(10), nullable=False, server_default="1d"),
        sa.Column("pred_up", sa.Float(), nullable=False),
        sa.Column("pred_neutral", sa.Float(), nullable=False),
        sa.Column("pred_down", sa.Float(), nullable=False),
        sa.Column("action", sa.String(10), nullable=False, server_default="HOLD"),
        sa.Column("committed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revealed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actual_return_pct", sa.Float(), nullable=True),
        sa.Column("actual_direction", sa.String(10), nullable=True),
        sa.Column("correct", sa.Boolean(), nullable=True),
        sa.Column("is_repeat", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.create_index("ix_attempts_scenario", "challenge_attempts", ["scenario_id"])
    op.create_index("ix_attempts_experiment", "challenge_attempts", ["experiment_id"])

    op.create_table(
        "streaks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("streak_key", sa.String(200), unique=True, nullable=False),
        sa.Column("experiment_id", sa.String(50), nullable=False),
        sa.Column("horizon", sa.String(10), nullable=False, server_default="1d"),
        sa.Column("correctness_rule", sa.String(200), nullable=False, server_default="action-vs-cost-band"),
        sa.Column("current", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("longest", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unique_scenarios", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("correct_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("incorrect_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completed_10_of_10", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.create_index("ix_streaks_key", "streaks", ["streak_key"])
    op.create_index("ix_streaks_experiment", "streaks", ["experiment_id"])

    op.create_table(
        "error_diagnoses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("attempt_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("challenge_attempts.id", ondelete="CASCADE"),
                  unique=True, nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("alternatives", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("confidence", sa.String(20), nullable=False, server_default="low"),
        sa.Column("intervention", sa.Text(), nullable=True),
        sa.Column("success_metric", sa.String(200), nullable=True),
        sa.Column("result", sa.Text(), nullable=True),
    )
    op.create_index("ix_diagnoses_category", "error_diagnoses", ["category"])


def downgrade() -> None:
    op.drop_table("error_diagnoses")
    op.drop_table("streaks")
    op.drop_table("challenge_attempts")
    op.drop_table("scenarios")
