from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from apps.api.models.backtest import Backtest, BacktestStatus, BacktestTrade
from apps.api.models.market import Exchange, Instrument
from apps.api.models.prediction import Model, ModelVersion
from apps.api.repositories.base import BaseRepository


class BacktestRepository(BaseRepository[Backtest]):
    """Backtest repository."""

    def __init__(self, session: AsyncSession):
        super().__init__(Backtest, session)

    async def get_user_backtests(
        self,
        user_id: UUID,
        status: str | None = None,
        include_details: bool = False,
        skip: int = 0,
        limit: int = 20,
    ) -> list[Backtest]:
        """Get backtests for a user."""
        query = select(Backtest).where(Backtest.user_id == user_id)
        if status:
            query = query.where(Backtest.status == status)
        if include_details:
            query = query.options(
                selectinload(Backtest.instrument).selectinload(Instrument.exchange).selectinload(Exchange.market),
                selectinload(Backtest.model_version).selectinload(ModelVersion.model),
            )
        query = query.order_by(desc(Backtest.created_at)).offset(skip).limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_by_id_with_details(self, backtest_id: UUID) -> Backtest | None:
        """Get backtest with all details."""
        query = (
            select(Backtest)
            .options(
                selectinload(Backtest.instrument).selectinload(Instrument.exchange).selectinload(Exchange.market),
                selectinload(Backtest.model_version).selectinload(ModelVersion.model),
            )
            .where(Backtest.id == backtest_id)
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def create_backtest(
        self,
        user_id: UUID,
        instrument_id: UUID,
        model_version_id: UUID,
        start_date: datetime,
        end_date: datetime,
        horizon: str,
        initial_capital: Decimal,
    ) -> Backtest:
        """Create a new backtest."""
        return await self.create(
            user_id=user_id,
            instrument_id=instrument_id,
            model_version_id=model_version_id,
            start_date=start_date,
            end_date=end_date,
            horizon=horizon,
            initial_capital=initial_capital,
            status=BacktestStatus.PENDING,
        )

    async def update_status(
        self,
        backtest_id: UUID,
        status: str,
        error_message: str | None = None,
    ) -> bool:
        """Update backtest status."""
        backtest = await self.get(backtest_id)
        if not backtest:
            return False
        backtest.status = status
        if error_message:
            backtest.error_message = error_message
        if status == BacktestStatus.COMPLETED:
            backtest.completed_at = datetime.now(UTC)
        await self.session.flush()
        return True

    async def update_results(
        self,
        backtest_id: UUID,
        total_return: Decimal,
        annualized_return: Decimal,
        sharpe_ratio: Decimal,
        max_drawdown: Decimal,
        win_rate: Decimal,
        profit_factor: Decimal,
        equity_curve: list,
        drawdown_curve: list,
        returns_distribution: list,
        trades: list,
    ) -> bool:
        """Update backtest results."""
        backtest = await self.get(backtest_id)
        if not backtest:
            return False
        backtest.total_return = total_return
        backtest.annualized_return = annualized_return
        backtest.sharpe_ratio = sharpe_ratio
        backtest.max_drawdown = max_drawdown
        backtest.win_rate = win_rate
        backtest.profit_factor = profit_factor
        backtest.equity_curve = equity_curve
        backtest.drawdown_curve = drawdown_curve
        backtest.returns_distribution = returns_distribution
        backtest.trades = trades
        backtest.status = BacktestStatus.COMPLETED
        backtest.completed_at = datetime.now(UTC)
        await self.session.flush()
        return True


class BacktestTradeRepository(BaseRepository[BacktestTrade]):
    """Backtest trade repository."""

    def __init__(self, session: AsyncSession):
        super().__init__(BacktestTrade, session)

    async def get_backtest_trades(self, backtest_id: UUID) -> list[BacktestTrade]:
        """Get all trades for a backtest."""
        query = (
            select(BacktestTrade)
            .where(BacktestTrade.backtest_id == backtest_id)
            .order_by(BacktestTrade.entry_date)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def bulk_create_trades(self, trades: list[dict]) -> int:
        """Bulk create trades."""
        if not trades:
            return 0

        from sqlalchemy.dialects.postgresql import insert

        stmt = insert(BacktestTrade).values(trades)
        result = await self.session.execute(stmt)
        return result.rowcount
