"""Cross-sectional ranking snapshots, entries and resolved outcomes (ACC-001)."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "d8f3a1c7e9b2"
down_revision = "c4e1b90d5a7f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ranking_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("market", sa.String(10), nullable=False),
        sa.Column("horizon", sa.String(10), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("objective", sa.String(80), nullable=False),
        sa.Column("model_version", sa.String(80), nullable=False),
        sa.Column("artifact_sha", sa.String(80), nullable=False),
        sa.Column("feature_version", sa.String(40), nullable=False),
        sa.Column("universe_size", sa.Integer(), nullable=False),
        sa.Column("market_universe_size", sa.Integer(), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.UniqueConstraint(
            "market", "horizon", "as_of_date", "model_version",
            name="uq_ranking_snapshot_scope",
        ),
    )
    op.create_index("ix_ranking_snapshots_market", "ranking_snapshots", ["market"])
    op.create_index("ix_ranking_snapshots_horizon", "ranking_snapshots", ["horizon"])
    op.create_index("ix_ranking_snapshots_as_of_date", "ranking_snapshots", ["as_of_date"])
    op.create_index(
        "ix_ranking_snapshots_market_horizon_date",
        "ranking_snapshots",
        ["market", "horizon", "as_of_date"],
    )

    op.create_table(
        "ranking_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "snapshot_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ranking_snapshots.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "instrument_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("instruments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("symbol", sa.String(50), nullable=False),
        sa.Column("exchange", sa.String(20), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("score", sa.Numeric(8, 6), nullable=False),
        sa.Column("percentile", sa.Numeric(6, 3), nullable=False),
        sa.Column("quintile", sa.Integer(), nullable=False),
        sa.Column("relative_label", sa.String(32), nullable=False),
        sa.Column("feature_hash", sa.String(64), nullable=True),
        sa.UniqueConstraint("snapshot_id", "instrument_id", name="uq_ranking_entry_scope"),
    )
    op.create_index("ix_ranking_entries_snapshot_id", "ranking_entries", ["snapshot_id"])
    op.create_index("ix_ranking_entries_instrument_id", "ranking_entries", ["instrument_id"])
    op.create_index("ix_ranking_entries_snapshot_rank", "ranking_entries", ["snapshot_id", "rank"])

    op.create_table(
        "ranking_outcomes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "entry_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ranking_entries.id", ondelete="CASCADE"),
            unique=True,
            nullable=False,
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("horizon_end_date", sa.Date(), nullable=False),
        sa.Column("forward_return", sa.Numeric(12, 6), nullable=False),
        sa.Column("cross_sectional_median_return", sa.Numeric(12, 6), nullable=False),
        sa.Column("relative_return", sa.Numeric(12, 6), nullable=False),
        sa.Column("outperformed", sa.Boolean(), nullable=False),
        sa.Column("source", sa.String(50), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
    )
    op.create_index("ix_ranking_outcomes_entry_id", "ranking_outcomes", ["entry_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_ranking_outcomes_entry_id", table_name="ranking_outcomes")
    op.drop_table("ranking_outcomes")
    op.drop_index("ix_ranking_entries_snapshot_rank", table_name="ranking_entries")
    op.drop_index("ix_ranking_entries_instrument_id", table_name="ranking_entries")
    op.drop_index("ix_ranking_entries_snapshot_id", table_name="ranking_entries")
    op.drop_table("ranking_entries")
    op.drop_index("ix_ranking_snapshots_market_horizon_date", table_name="ranking_snapshots")
    op.drop_index("ix_ranking_snapshots_as_of_date", table_name="ranking_snapshots")
    op.drop_index("ix_ranking_snapshots_horizon", table_name="ranking_snapshots")
    op.drop_index("ix_ranking_snapshots_market", table_name="ranking_snapshots")
    op.drop_table("ranking_snapshots")
