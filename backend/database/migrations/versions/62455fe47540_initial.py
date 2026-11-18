"""initial

Revision ID: 62455fe47540
Revises: 
Create Date: 2026-08-22 14:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '62455fe47540'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create markets table
    op.create_table(
        'markets',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(length=10), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('country_code', sa.String(length=3), nullable=False),
        sa.Column('currency', sa.String(length=3), nullable=False),
        sa.Column('timezone', sa.String(length=50), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, default=True),
        sa.Column('market_open', sa.Time(timezone=False), nullable=False),
        sa.Column('market_close', sa.Time(timezone=False), nullable=False),
        sa.Column('pre_market_open', sa.Time(timezone=False), nullable=True),
        sa.Column('post_market_close', sa.Time(timezone=False), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code', name='uq_markets_code')
    )

    # Create exchanges table
    op.create_table(
        'exchanges',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(length=20), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('market_id', sa.Integer(), nullable=False),
        sa.Column('timezone', sa.String(length=50), nullable=False),
        sa.Column('currency', sa.String(length=3), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, default=True),
        sa.Column('market_open', sa.Time(timezone=False), nullable=False),
        sa.Column('market_close', sa.Time(timezone=False), nullable=False),
        sa.Column('pre_market_open', sa.Time(timezone=False), nullable=True),
        sa.Column('post_market_close', sa.Time(timezone=False), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.ForeignKeyConstraint(['market_id'], ['markets.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code', 'market_id', name='uq_exchange_code_market')
    )
    op.create_index('ix_exchanges_market_id', 'exchanges', ['market_id'])

    # Create instruments table
    op.create_table(
        'instruments',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('symbol', sa.String(length=50), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('exchange_id', sa.Integer(), nullable=False),
        sa.Column('type', sa.String(length=8), nullable=False, default='equity'),
        sa.Column('currency', sa.String(length=3), nullable=False),
        sa.Column('isin', sa.String(length=12), nullable=True),
        sa.Column('cusip', sa.String(length=9), nullable=True),
        sa.Column('figi', sa.String(length=12), nullable=True),
        sa.Column('sector', sa.String(length=100), nullable=True),
        sa.Column('industry', sa.String(length=100), nullable=True),
        sa.Column('market_cap', sa.Integer(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, default=True),
        sa.Column('is_tradable', sa.Boolean(), nullable=False, default=True),
        sa.Column('metadata_json', postgresql.JSONB(), nullable=False, default={}),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.ForeignKeyConstraint(['exchange_id'], ['exchanges.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('symbol', 'exchange_id', name='uq_instrument_symbol_exchange')
    )
    op.create_index('ix_instruments_symbol_active', 'instruments', ['symbol', 'is_active'])
    op.create_index('ix_instruments_sector', 'instruments', ['sector'])
    op.create_index('ix_instruments_exchange_id', 'instruments', ['exchange_id'])

    # Create users table
    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('hashed_password', sa.String(length=255), nullable=False),
        sa.Column('full_name', sa.String(length=255), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, default=True),
        sa.Column('is_superuser', sa.Boolean(), nullable=False, default=False),
        sa.Column('last_login', sa.DateTime(timezone=True), nullable=True),
        sa.Column('preferences', postgresql.JSONB(), nullable=False, default={}),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email', name='uq_users_email')
    )
    op.create_index('ix_users_email', 'users', ['email'])

    # Create sessions table
    op.create_table(
        'sessions',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('token_hash', sa.String(length=255), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
        sa.Column('user_agent', sa.String(length=500), nullable=True),
        sa.Column('is_revoked', sa.Boolean(), nullable=False, default=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('token_hash', name='uq_sessions_token_hash')
    )
    op.create_index('ix_sessions_user_expires', 'sessions', ['user_id', 'expires_at'])

    # Create refresh_tokens table
    op.create_table(
        'refresh_tokens',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('token_hash', sa.String(length=255), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('replaced_by_token_hash', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('token_hash', name='uq_refresh_tokens_token_hash')
    )
    op.create_index('ix_refresh_tokens_user_expires', 'refresh_tokens', ['user_id', 'expires_at'])

    # Create models table
    op.create_table(
        'models',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('description', sa.String(length=500), nullable=True),
        sa.Column('model_type', sa.String(length=50), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, default=True),
        sa.Column('metadata_json', postgresql.JSONB(), nullable=False, default={}),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name', name='uq_models_name')
    )

    # Create model_versions table
    op.create_table(
        'model_versions',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('model_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('version', sa.String(length=50), nullable=False),
        sa.Column('description', sa.String(length=500), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, default=True),
        sa.Column('training_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('metrics', postgresql.JSONB(), nullable=False, default={}),
        sa.Column('hyperparameters', postgresql.JSONB(), nullable=False, default={}),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.ForeignKeyConstraint(['model_id'], ['models.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('model_id', 'version', name='uq_model_version')
    )
    op.create_index('ix_model_versions_model_active', 'model_versions', ['model_id', 'is_active'])

    # Create price_bars table
    op.create_table(
        'price_bars',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('instrument_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('timeframe', sa.String(length=10), nullable=False),
        sa.Column('open', sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column('high', sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column('low', sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column('close', sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column('volume', sa.Integer(), nullable=False),
        sa.Column('vwap', sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column('trades_count', sa.Integer(), nullable=True),
        sa.Column('source', sa.String(length=50), nullable=False, default='unknown'),
        sa.Column('ingested_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.ForeignKeyConstraint(['instrument_id'], ['instruments.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('instrument_id', 'timestamp', 'timeframe', name='uq_price_bar_unique')
    )
    op.create_index('ix_price_bars_instrument_timeframe_ts', 'price_bars', ['instrument_id', 'timeframe', 'timestamp'])
    op.create_index('ix_price_bars_timestamp_desc', 'price_bars', [sa.text('timestamp DESC')])

    # Create market_snapshots table
    op.create_table(
        'market_snapshots',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('instrument_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('price', sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column('change', sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column('change_percent', sa.Numeric(precision=10, scale=4), nullable=False),
        sa.Column('volume', sa.Integer(), nullable=False),
        sa.Column('high', sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column('low', sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column('open', sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column('previous_close', sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column('market_status', sa.String(length=20), nullable=False),
        sa.Column('source', sa.String(length=50), nullable=False, default='unknown'),
        sa.Column('ingested_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.ForeignKeyConstraint(['instrument_id'], ['instruments.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('instrument_id', 'timestamp', name='uq_market_snapshot_unique')
    )
    op.create_index('ix_market_snapshots_instrument_ts', 'market_snapshots', ['instrument_id', 'timestamp'])

    # Create predictions table
    op.create_table(
        'predictions',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('instrument_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('model_version_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('horizon', sa.String(length=9), nullable=False),
        sa.Column('predicted_direction', sa.String(length=7), nullable=False),
        sa.Column('up_probability', sa.Numeric(precision=5, scale=4), nullable=False),
        sa.Column('neutral_probability', sa.Numeric(precision=5, scale=4), nullable=False),
        sa.Column('down_probability', sa.Numeric(precision=5, scale=4), nullable=False),
        sa.Column('expected_return', sa.Numeric(precision=10, scale=4), nullable=False),
        sa.Column('range_lower', sa.Numeric(precision=10, scale=4), nullable=False),
        sa.Column('range_upper', sa.Numeric(precision=10, scale=4), nullable=False),
        sa.Column('confidence', sa.Integer(), nullable=False),
        sa.Column('prediction_timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('data_timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('features_snapshot', postgresql.JSONB(), nullable=False, default={}),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.ForeignKeyConstraint(['instrument_id'], ['instruments.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['model_version_id'], ['model_versions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_predictions_instrument_horizon_ts', 'predictions', ['instrument_id', 'horizon', 'prediction_timestamp'])
    op.create_index('ix_predictions_model_ts', 'predictions', ['model_version_id', 'prediction_timestamp'])

    # Create prediction_outcomes table
    op.create_table(
        'prediction_outcomes',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('prediction_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('actual_return', sa.Numeric(precision=10, scale=4), nullable=False),
        sa.Column('actual_direction', sa.String(length=7), nullable=False),
        sa.Column('is_correct', sa.Boolean(), nullable=False),
        sa.Column('evaluated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('evaluation_price', sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column('evaluation_timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.ForeignKeyConstraint(['prediction_id'], ['predictions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('prediction_id', name='uq_prediction_outcome_prediction_id')
    )
    op.create_index('ix_prediction_outcomes_prediction_id', 'prediction_outcomes', ['prediction_id'])

    # Create watchlists table
    op.create_table(
        'watchlists',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('description', sa.String(length=500), nullable=True),
        sa.Column('is_default', sa.Boolean(), nullable=False, default=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'name', name='uq_watchlist_user_name')
    )
    op.create_index('ix_watchlists_user_default', 'watchlists', ['user_id', 'is_default'])

    # Create watchlist_items table
    op.create_table(
        'watchlist_items',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('watchlist_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('instrument_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('notes', sa.String(length=500), nullable=True),
        sa.Column('sort_order', sa.Integer(), nullable=False, default=0),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.ForeignKeyConstraint(['watchlist_id'], ['watchlists.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['instrument_id'], ['instruments.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('watchlist_id', 'instrument_id', name='uq_watchlist_item_unique')
    )
    op.create_index('ix_watchlist_items_watchlist_order', 'watchlist_items', ['watchlist_id', 'sort_order'])

    # Create alerts table
    op.create_table(
        'alerts',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('instrument_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('alert_type', sa.String(length=22), nullable=False),
        sa.Column('condition', sa.String(length=21), nullable=False),
        sa.Column('target_value', sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column('secondary_value', sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column('status', sa.String(length=12), nullable=False, default='active'),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('triggered_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('acknowledged_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('notify_email', sa.Boolean(), nullable=False, default=True),
        sa.Column('notify_push', sa.Boolean(), nullable=False, default=False),
        sa.Column('notify_in_app', sa.Boolean(), nullable=False, default=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['instrument_id'], ['instruments.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_alerts_user_status', 'alerts', ['user_id', 'status'])
    op.create_index('ix_alerts_instrument_type', 'alerts', ['instrument_id', 'alert_type'])
    op.create_index('ix_alerts_expires', 'alerts', ['expires_at'])

    # Create alert_triggers table
    op.create_table(
        'alert_triggers',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('alert_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('triggered_value', sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column('message', sa.String(length=500), nullable=False),
        sa.Column('email_sent', sa.Boolean(), nullable=False, default=False),
        sa.Column('push_sent', sa.Boolean(), nullable=False, default=False),
        sa.Column('in_app_sent', sa.Boolean(), nullable=False, default=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.ForeignKeyConstraint(['alert_id'], ['alerts.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_alert_triggers_alert_ts', 'alert_triggers', ['alert_id', 'created_at'])

    # Create backtests table
    op.create_table(
        'backtests',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('instrument_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('model_version_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('start_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('end_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('horizon', sa.String(length=10), nullable=False),
        sa.Column('initial_capital', sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column('status', sa.String(length=9), nullable=False, default='pending'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('total_return', sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column('annualized_return', sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column('sharpe_ratio', sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column('max_drawdown', sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column('win_rate', sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column('profit_factor', sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column('equity_curve', postgresql.JSONB(), nullable=True, default=[]),
        sa.Column('drawdown_curve', postgresql.JSONB(), nullable=True, default=[]),
        sa.Column('returns_distribution', postgresql.JSONB(), nullable=True, default=[]),
        sa.Column('trades', postgresql.JSONB(), nullable=True, default=[]),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['instrument_id'], ['instruments.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['model_version_id'], ['model_versions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_backtests_user_status', 'backtests', ['user_id', 'status'])
    op.create_index('ix_backtests_instrument_dates', 'backtests', ['instrument_id', 'start_date', 'end_date'])

    # Create backtest_trades table
    op.create_table(
        'backtest_trades',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('backtest_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('entry_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('exit_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('entry_price', sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column('exit_price', sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column('shares', sa.Integer(), nullable=False),
        sa.Column('side', sa.String(length=10), nullable=False),
        sa.Column('pnl', sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column('return_pct', sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column('is_winner', sa.Boolean(), nullable=True),
        sa.Column('prediction_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.ForeignKeyConstraint(['backtest_id'], ['backtests.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['prediction_id'], ['predictions.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_backtest_trades_backtest_entry', 'backtest_trades', ['backtest_id', 'entry_date'])

    # Create audit_logs table
    op.create_table(
        'audit_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('session_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('action', sa.String(length=50), nullable=False),
        sa.Column('resource_type', sa.String(length=50), nullable=True),
        sa.Column('resource_id', sa.String(length=100), nullable=True),
        sa.Column('ip_address', sa.String(length=45), nullable=True),
        sa.Column('user_agent', sa.String(length=500), nullable=True),
        sa.Column('request_id', sa.String(length=100), nullable=True),
        sa.Column('success', sa.Boolean(), nullable=False, default=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('metadata_json', postgresql.JSONB(), nullable=False, default={}),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['session_id'], ['sessions.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_audit_logs_user_action_ts', 'audit_logs', ['user_id', 'action', 'created_at'])
    op.create_index('ix_audit_logs_resource', 'audit_logs', ['resource_type', 'resource_id'])
    op.create_index('ix_audit_logs_ip_ts', 'audit_logs', ['ip_address', 'created_at'])
    op.create_index('ix_audit_logs_success_ts', 'audit_logs', ['success', 'created_at'])


def downgrade() -> None:
    op.drop_table('audit_logs')
    op.drop_table('backtest_trades')
    op.drop_table('backtests')
    op.drop_table('alert_triggers')
    op.drop_table('alerts')
    op.drop_table('watchlist_items')
    op.drop_table('watchlists')
    op.drop_table('prediction_outcomes')
    op.drop_table('predictions')
    op.drop_table('market_snapshots')
    op.drop_table('price_bars')
    op.drop_table('model_versions')
    op.drop_table('models')
    op.drop_table('sessions')
    op.drop_table('refresh_tokens')
    op.drop_table('users')
    op.drop_table('instruments')
    op.drop_table('exchanges')
    op.drop_table('markets')