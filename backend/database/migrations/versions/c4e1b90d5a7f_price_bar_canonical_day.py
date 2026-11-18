"""BAR-002: canonical session-day identity for daily price bars.

Adds a nullable DATE column ``price_bars.session_day`` populated only
for 1d bars, plus a partial unique index
``uq_price_bar_instrument_timeframe_session_day`` on
(instrument_id, timeframe, session_day) WHERE session_day IS NOT NULL.

The column is populated by the application (canonical trading-day
stamping at ingestion time, services/ingestion/canonical_days.py) and by
a one-off backfill after auditing legacy double-stamped rows with
scripts/audit_price_bar_duplicates.py. The migration is intentionally
data-preserving: it does NOT delete or rewrite existing bar rows; it
only adds the identity column and the index that forbids new
double-stamps.

Apply after an owner-approved dedupe, and BEFORE the session_day
backfill: scripts/bar002_reconcile.py --phase dedupe --apply, then
alembic upgrade, then scripts/bar002_reconcile.py --phase backfill
--apply. Building the partial index with every session_day NULL succeeds;
the guard fires when the backfill tries to assign a second row the same
(instrument, timeframe, session_day). Quarantined legacy conflicts keep
session_day NULL so the partial index accepts them without discarding
data.
"""

import sqlalchemy as sa
from alembic import op

revision = "c4e1b90d5a7f"
down_revision = "b7f2a1c9d3e4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "price_bars",
        sa.Column("session_day", sa.Date(), nullable=True),
    )
    op.create_index(
        "ix_price_bars_session_day",
        "price_bars",
        ["instrument_id", "timeframe", "session_day"],
        unique=False,
    )
    op.create_index(
        "uq_price_bar_instrument_timeframe_session_day",
        "price_bars",
        ["instrument_id", "timeframe", "session_day"],
        unique=True,
        postgresql_where=sa.text("session_day IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_price_bar_instrument_timeframe_session_day", table_name="price_bars")
    op.drop_index("ix_price_bars_session_day", table_name="price_bars")
    op.drop_column("price_bars", "session_day")
