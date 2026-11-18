"""MLOps continuous-learning tables + outcome provenance columns.

- experiments / training_jobs / model_champions / model_promotions /
  drift_observations (see apps.api.models.mlops).
- prediction_outcomes gains source + note (resolution provenance; audit
  history for corrections lives in audit_logs).
- model_champions has a partial unique index guaranteeing a single current
  champion row (superseded_at IS NULL).
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "9f3c1a2b7d4e"
down_revision = "62455fe47540"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "experiments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("experiment_id", sa.String(50), unique=True, nullable=False),
        sa.Column("hypothesis", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="research"),
        sa.Column("dataset_fingerprint", sa.String(120), nullable=False, server_default=""),
        sa.Column("feature_set", sa.String(50), nullable=False, server_default="full"),
        sa.Column("target", sa.String(50), nullable=False, server_default="v1-h1d-0.5pct"),
        sa.Column("horizon", sa.String(10), nullable=False, server_default="1d"),
        sa.Column("model_family", sa.String(100), nullable=False, server_default=""),
        sa.Column("hyperparameters", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("seed", sa.Integer(), nullable=True),
        sa.Column("splits", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("backtest", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("artifact_path", sa.String(500), nullable=True),
        sa.Column("artifact_sha", sa.String(120), nullable=True),
        sa.Column("code_revision", sa.String(80), nullable=True),
        sa.Column("compute_seconds", sa.Float(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("decision", sa.String(20), nullable=True),
        sa.Column("decision_reason", sa.Text(), nullable=True),
    )
    op.create_index("ix_experiments_experiment_id", "experiments", ["experiment_id"])
    op.create_index("ix_experiments_status", "experiments", ["status"])

    op.create_table(
        "training_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("job_key", sa.String(120), unique=True, nullable=False),
        sa.Column("experiment_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("experiments.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("timeout_s", sa.Integer(), nullable=False, server_default="3600"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("compute_seconds", sa.Float(), nullable=False, server_default="0"),
    )
    op.create_index("ix_training_jobs_job_key", "training_jobs", ["job_key"])
    op.create_index("ix_training_jobs_status", "training_jobs", ["status"])

    op.create_table(
        "model_champions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("model_version_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("model_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("artifact_sha", sa.String(120), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_by", sa.String(255), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_model_champions_version", "model_champions", ["model_version_id"])
    op.execute(
        "CREATE UNIQUE INDEX uq_champion_current ON model_champions (superseded_at) "
        "WHERE superseded_at IS NULL"
    )

    op.create_table(
        "model_promotions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("from_version_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("model_versions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("to_version_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("model_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("experiment_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("experiments.id", ondelete="SET NULL"), nullable=True),
        sa.Column("decided_by", sa.String(255), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("metrics_delta", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
    )
    op.create_index("ix_model_promotions_to_version", "model_promotions", ["to_version_id"])

    op.create_table(
        "drift_observations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("scope", sa.String(100), nullable=False),
        sa.Column("metric", sa.String(100), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("threshold", sa.Float(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("acknowledged", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("note", sa.Text(), nullable=True),
    )
    op.create_index("ix_drift_scope_observed", "drift_observations", ["scope", "observed_at"])

    op.add_column("prediction_outcomes", sa.Column("source", sa.String(50), nullable=True))
    op.add_column("prediction_outcomes", sa.Column("note", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("prediction_outcomes", "note")
    op.drop_column("prediction_outcomes", "source")
    op.drop_table("drift_observations")
    op.drop_table("model_promotions")
    op.execute("DROP INDEX IF EXISTS uq_champion_current")
    op.drop_table("model_champions")
    op.drop_table("training_jobs")
    op.drop_table("experiments")
