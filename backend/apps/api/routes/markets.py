from datetime import UTC, datetime, timedelta
from decimal import Decimal

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from apps.api.database import get_session
from apps.api.repositories.market import (
    ExchangeRepository,
    InstrumentRepository,
    MarketRepository,
    MarketSnapshotRepository,
    PriceBarRepository,
)
from apps.api.routes.auth import get_current_user
from packages.schemas.market import (
    ExchangeResponse,
    HistoricalPriceResponse,
    IndexQuote,
    InstrumentResponse,
    InstrumentSearchResult,
    MarketMover,
    MarketOverviewResponse,
    MarketResponse,
    QuoteResponse,
)
from services.ingestion.ingestion_service import IngestionService
from services.ingestion.providers.factory import ProviderFactory

router = APIRouter(prefix="/markets", tags=["markets"])
logger = logging.getLogger(__name__)


@router.get("", response_model=list[MarketResponse])
async def list_markets(
    session: AsyncSession = Depends(get_session),
) -> list[MarketResponse]:
    """List all markets."""
    repo = MarketRepository(session)
    markets = await repo.get_active_markets()
    return [MarketResponse.model_validate(m) for m in markets]


# Major index universe per market. Codes MUST match the markets table
# (US / IN / EU — see seed_markets.py). Previous code used India/Europe here,
# which missed the market_rows lookup and skipped session/freshness derivation.
INDEX_UNIVERSE: dict[str, list[tuple[str, str]]] = {
    "US": [
        ("^GSPC", "S&P 500"),
        ("^IXIC", "NASDAQ Composite"),
        ("^DJI", "Dow Jones Industrial Average"),
    ],
    "IN": [
        ("^NSEI", "NIFTY 50"),
        ("^BSESN", "BSE SENSEX"),
    ],
    "EU": [
        ("^GDAXI", "DAX"),
        ("^FTSE", "FTSE 100"),
        ("^STOXX50E", "EURO STOXX 50"),
    ],
}
# Back-compat: providers registered under India/Europe still resolve via
# ProviderRouter aliasing, so either spelling works for live fetch.


@router.get("/overview", response_model=MarketOverviewResponse)
async def market_overview(
    session: AsyncSession = Depends(get_session),
) -> MarketOverviewResponse:
    """Market overview: major indices (live fetch, short cache) + movers
    from persisted snapshots. Absent data is simply absent — never synthetic."""
    from sqlalchemy import func, select

    from apps.api.models.market import Exchange, Instrument
    from apps.api.models.price import MarketSnapshot
    from services.cache import cache_get, cache_set
    from services.freshness import Freshness, classify_freshness

    now_utc = datetime.now(UTC)
    indices: list[IndexQuote] = []
    provider = ProviderFactory.get_fallback_provider()

    if provider is not None:
        import asyncio

        from apps.api.models.market import Market as MarketModel
        from services.market_session import derive_market_status, refine_source_timestamp

        # Session-status derivation needs each market's calendar row.
        market_rows: dict[str, MarketModel] = {}
        for mc in INDEX_UNIVERSE:
            row = await session.scalar(select(MarketModel).where(MarketModel.code == mc))
            if row is not None:
                market_rows[mc] = row

        async def _fetch_index(market_code: str, sym: str, name: str) -> IndexQuote | None:
            """Fetch one index quote. Touches cache + providers only (no DB
            session), so many of these can safely run concurrently."""
            cache_key = f"index:{sym}"
            payload = await cache_get(cache_key)
            if isinstance(payload, dict):
                try:
                    return IndexQuote.model_validate(payload)
                except Exception:
                    payload = None
            try:
                q = await provider.get_quote(sym, "INDEX", market_code)
            except Exception:
                q = None
            if q is None or q.price <= 0:
                return None
            m_row = market_rows.get(market_code)
            if m_row is not None:
                from dataclasses import replace as _dc_replace

                eff_status = q.market_status
                if eff_status == "unknown":
                    eff_status = derive_market_status(m_row)
                eff_ts, _ = refine_source_timestamp(q.timestamp, m_row, q.metadata)
                if eff_status != q.market_status or eff_ts != q.timestamp:
                    q = _dc_replace(q, timestamp=eff_ts, market_status=eff_status)
            fresh = classify_freshness(
                q.timestamp, ingested_at=now_utc, market_status=q.market_status
            )
            iq = IndexQuote(
                symbol=sym,
                name=name,
                price=q.price,
                change=q.change,
                change_percent=q.change_percent,
                market_status=q.market_status,
                timestamp=q.timestamp.isoformat(),
                provider=q.provider or provider.name,
                freshness=fresh.value,
                currency=q.metadata.get("currency", "USD") if isinstance(q.metadata, dict) else "USD",
            )
            if fresh in (Freshness.FRESH, Freshness.RECENT, Freshness.DELAYED):
                await cache_set(cache_key, iq.model_dump(mode="json"), ttl=60)
            return iq

        # 8 indices fetched concurrently (was sequential ~7.5s; now ~provider
        # latency of the slowest single fetch). Order preserved for the UI.
        jobs = [
            _fetch_index(market_code, sym, name)
            for market_code, entries in INDEX_UNIVERSE.items()
            for sym, name in entries
        ]
        for iq in await asyncio.gather(*jobs):
            if iq is not None:
                indices.append(iq)

    # Movers from the freshest snapshot per instrument (no fabrication).
    async def _movers(descending: bool, limit: int = 5) -> list[MarketMover]:
        latest_ts = (
            select(
                MarketSnapshot.instrument_id,
                func.max(MarketSnapshot.timestamp).label("ts"),
            )
            .group_by(MarketSnapshot.instrument_id)
            .subquery()
        )
        stmt = (
            select(MarketSnapshot, Instrument, Exchange)
            .join(latest_ts, (latest_ts.c.instrument_id == MarketSnapshot.instrument_id) & (latest_ts.c.ts == MarketSnapshot.timestamp))
            .join(Instrument, Instrument.id == MarketSnapshot.instrument_id)
            .join(Exchange, Exchange.id == Instrument.exchange_id)
            # Exchange.market is a lazy relationship; accessing it on an ORM
            # row inside async code raises MissingGreenlet unless eager-loaded.
            .options(joinedload(Exchange.market))
            .order_by(MarketSnapshot.change_percent.desc() if descending else MarketSnapshot.change_percent.asc())
            .limit(limit)
        )
        rows = (await session.execute(stmt)).all()
        movers = []
        for snap, inst, exch in rows:
            fresh = classify_freshness(
                snap.timestamp, ingested_at=snap.ingested_at, market_status=snap.market_status
            )
            movers.append(
                MarketMover(
                    symbol=inst.symbol,
                    name=inst.name,
                    exchange=exch.code,
                    market=exch.market.code if exch.market else "",
                    price=snap.price,
                    change_percent=snap.change_percent,
                    volume=snap.volume,
                    timestamp=snap.timestamp.isoformat(),
                    freshness=fresh.value,
                )
            )
        return movers

    try:
        gainers = await _movers(descending=True)
        losers = await _movers(descending=False)
    except Exception:
        # Degrade gracefully but never silently: movers are a best-effort
        # section of the overview, yet the operator must see why they are
        # missing (an empty list here is "unavailable", not "no movers").
        logger.exception("market_overview movers query failed")
        gainers, losers = [], []

    stale = all(i.freshness in ("stale", "unavailable") for i in indices) if indices else True
    return MarketOverviewResponse(
        indices=indices,
        gainers=gainers,
        losers=losers,
        as_of=now_utc.isoformat(),
        stale=stale,
    )


@router.get("/{market_code}", response_model=MarketResponse)
async def get_market(
    market_code: str,
    session: AsyncSession = Depends(get_session),
) -> MarketResponse:
    """Get market by code."""
    repo = MarketRepository(session)
    market = await repo.get_by_code(market_code)
    if not market:
        raise HTTPException(status_code=404, detail="Market not found")
    return MarketResponse.model_validate(market)


@router.get("/{market_code}/exchanges", response_model=list[ExchangeResponse])
async def list_exchanges(
    market_code: str,
    session: AsyncSession = Depends(get_session),
) -> list[ExchangeResponse]:
    """List exchanges for a market."""
    market_repo = MarketRepository(session)
    market = await market_repo.get_by_code(market_code)
    if not market:
        raise HTTPException(status_code=404, detail="Market not found")

    repo = ExchangeRepository(session)
    exchanges = await repo.get_by_market(market.id)
    return [ExchangeResponse.model_validate(e) for e in exchanges]


@router.get("/exchanges/{exchange_code}", response_model=ExchangeResponse)
async def get_exchange(
    exchange_code: str,
    market_code: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> ExchangeResponse:
    """Get exchange by code."""
    market_id = None
    if market_code:
        market_repo = MarketRepository(session)
        market = await market_repo.get_by_code(market_code)
        if market:
            market_id = market.id

    repo = ExchangeRepository(session)
    exchange = await repo.get_by_code(exchange_code, market_id)
    if not exchange:
        raise HTTPException(status_code=404, detail="Exchange not found")
    return ExchangeResponse.model_validate(exchange)


@router.get("/instruments/search", response_model=list[InstrumentSearchResult])
async def search_instruments(
    q: str = Query(..., min_length=1, max_length=100),
    market: str | None = None,
    exchange: str | None = None,
    type: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
) -> list[InstrumentSearchResult]:
    """Search instruments by symbol or name."""
    repo = InstrumentRepository(session)
    instruments = await repo.search(q, market, exchange, type, limit)

    results = []
    for inst in instruments:
        results.append(InstrumentSearchResult(
            symbol=inst.symbol,
            name=inst.name,
            exchange=inst.exchange.name if inst.exchange else "",
            exchange_code=inst.exchange.code if inst.exchange else "",
            market=inst.exchange.market.code if inst.exchange and inst.exchange.market else "",
            type=inst.type,
            currency=inst.currency,
        ))
    return results


@router.get("/instruments/{symbol}", response_model=InstrumentResponse)
async def get_instrument(
    symbol: str,
    exchange_code: str = Query(..., alias="exchange"),
    session: AsyncSession = Depends(get_session),
) -> InstrumentResponse:
    """Get instrument by symbol and exchange."""
    exchange_repo = ExchangeRepository(session)
    exchange = await exchange_repo.get_by_code(exchange_code)
    if not exchange:
        raise HTTPException(status_code=404, detail="Exchange not found")

    # Eager-load exchange.market: InstrumentResponse nests exchange.market,
    # and touching that lazy relationship inside async validation raises
    # MissingGreenlet (500). Search already uses this pattern.
    from sqlalchemy.orm import selectinload

    from apps.api.models.market import Exchange as ExchangeModel
    from apps.api.models.market import Instrument as InstrumentModel

    stmt = (
        select(InstrumentModel)
        .options(
            selectinload(InstrumentModel.exchange).selectinload(ExchangeModel.market)
        )
        .where(
            InstrumentModel.symbol == symbol.upper(),
            InstrumentModel.exchange_id == exchange.id,
        )
    )
    instrument = (await session.execute(stmt)).scalar_one_or_none()
    if not instrument:
        raise HTTPException(status_code=404, detail="Instrument not found")

    return InstrumentResponse.model_validate(instrument)


@router.get("/instruments/{symbol}/quote", response_model=QuoteResponse)
async def get_quote(
    symbol: str,
    exchange_code: str = Query(..., alias="exchange"),
    live: bool = Query(default=True, description="Attempt a live provider fetch before falling back to persisted data"),
    session: AsyncSession = Depends(get_session),
) -> QuoteResponse:
    """Get a quote with an explicit, backend-classified freshness status.

    Order of preference:
      1. Live provider fetch (short-TTL cached, single-flight per symbol).
      2. Latest persisted snapshot — freshness classified from its
         source/ingestion timestamps, never presented as live if stale.
      3. Latest persisted daily bar — labeled historical (stale), with a
         previous_close derived from the prior bar, never fabricated.
    """
    from services.cache import cache_get, cache_set
    from services.freshness import Freshness, classify_freshness, freshness_rank, is_presentable_as_current

    exchange_repo = ExchangeRepository(session)
    exchange = await exchange_repo.get_by_code(exchange_code)
    if not exchange:
        raise HTTPException(status_code=404, detail="Exchange not found")

    repo = InstrumentRepository(session)
    instrument = await repo.get_by_symbol_exchange(symbol.upper(), exchange.id)
    if not instrument:
        raise HTTPException(status_code=404, detail="Instrument not found")

    sym = instrument.symbol
    # exchange.market is lazy; load the Market row directly by FK (its
    # timezone + trading hours feed the session-status derivation below).
    from apps.api.models.market import Market

    market_row = await session.scalar(select(Market).where(Market.id == exchange.market_id))
    market_code = market_row.code if market_row else None
    cache_key = f"quote:{exchange_code}:{sym}"

    best: QuoteResponse | None = None

    # 1) Live provider fetch (cached briefly to protect provider rate limits)
    if live:
        cached = await cache_get(cache_key)
        if isinstance(cached, dict):
            try:
                cached_q = QuoteResponse.model_validate(cached)
                if is_presentable_as_current(Freshness(cached_q.freshness)):
                    return cached_q
            except Exception:
                cached = None
        if cached is None:
            provider = ProviderFactory.get_fallback_provider()
            if provider is not None:
                try:
                    quote_data = await provider.get_quote(sym, exchange_code, market_code)
                except Exception:
                    quote_data = None
                if quote_data is not None and quote_data.price > 0:
                    now_utc = datetime.now(UTC)
                    # Session honesty: providers that cannot know session
                    # state report "unknown"; derive it from the market's
                    # calendar instead of trusting a hardcoded guess.
                    # Date-only source timestamps (Alpha Vantage) are
                    # refined to the provable session-open bound.
                    if market_row is not None:
                        from dataclasses import replace as _dc_replace

                        from services.market_session import (
                            derive_market_status,
                            refine_source_timestamp,
                        )

                        eff_status = quote_data.market_status
                        if eff_status == "unknown":
                            eff_status = derive_market_status(market_row)
                        eff_ts, _ = refine_source_timestamp(
                            quote_data.timestamp, market_row, quote_data.metadata
                        )
                        if eff_status != quote_data.market_status or eff_ts != quote_data.timestamp:
                            quote_data = _dc_replace(
                                quote_data, timestamp=eff_ts, market_status=eff_status
                            )
                    fresh = classify_freshness(
                        quote_data.timestamp,
                        ingested_at=now_utc,
                        market_status=quote_data.market_status,
                    )
                    best = _quote_response_from_provider(
                        sym, exchange_code, instrument.currency, quote_data, provider.name, fresh, now_utc
                    )
                    # Only cache presentable data; stale data must not be
                    # seeded into the cache as if it were current.
                    if is_presentable_as_current(fresh):
                        await cache_set(cache_key, best.model_dump(mode="json"), ttl=30)

    # 2) Latest persisted snapshot, honestly classified
    snapshot_repo = MarketSnapshotRepository(session)
    snapshot = await snapshot_repo.get_latest(instrument.id)
    if snapshot:
        snap_fresh = classify_freshness(
            snapshot.timestamp,
            ingested_at=snapshot.ingested_at,
            market_status=snapshot.market_status,
        )
        snap_quote = _quote_response_from_snapshot(sym, exchange_code, instrument.currency, snapshot, snap_fresh)
        if best is None or freshness_rank(snap_fresh) < freshness_rank(Freshness(best.freshness)):
            best = snap_quote

    if best is not None:
        return best

    # 3) Latest persisted bar — historical data, explicitly labeled.
    price_bar_repo = PriceBarRepository(session)
    bars = await price_bar_repo.get_latest(instrument.id, "1d", 2)
    if bars:
        bar = bars[0]
        prior = bars[1] if len(bars) > 1 else None
        # Previous close from the prior session bar. With no prior bar the
        # true previous close is unknown; the session open is used as the
        # change reference (change is then vs. open). The response is
        # labeled stale either way.
        previous_close = prior.close if prior is not None else bar.open
        change = bar.close - previous_close
        change_percent = (
            (change / previous_close * 100).quantize(Decimal("0.01"))
            if previous_close > 0
            else Decimal("0")
        )
        return QuoteResponse(
            symbol=sym,
            price=bar.close,
            change=change,
            change_percent=change_percent,
            volume=bar.volume,
            high=bar.high,
            low=bar.low,
            open=bar.open,
            previous_close=previous_close,
            timestamp=bar.timestamp.isoformat(),
            market_status="closed",
            exchange=exchange_code,
            currency=instrument.currency,
            provider=bar.source,
            freshness=Freshness.STALE.value,
            delayed=False,
            source_timestamp=bar.timestamp.isoformat(),
            ingested_at=bar.ingested_at.isoformat() if bar.ingested_at else None,
        )

    raise HTTPException(status_code=404, detail="No price data available")


def _quote_response_from_provider(
    symbol: str,
    exchange_code: str,
    currency: str,
    quote_data,
    provider_name: str,
    fresh,
    now_utc,
) -> QuoteResponse:
    """Build a QuoteResponse from a live provider quote."""
    from services.freshness import Freshness

    return QuoteResponse(
        symbol=symbol,
        price=quote_data.price,
        change=quote_data.change,
        change_percent=quote_data.change_percent,
        volume=quote_data.volume,
        high=quote_data.high,
        low=quote_data.low,
        open=quote_data.open,
        previous_close=quote_data.previous_close,
        timestamp=quote_data.timestamp.isoformat(),
        market_status=quote_data.market_status,
        exchange=exchange_code,
        currency=currency,
        provider=quote_data.provider or provider_name,
        freshness=fresh.value,
        delayed=(quote_data.data_status == "delayed") or fresh == Freshness.DELAYED,
        source_timestamp=quote_data.timestamp.isoformat(),
        ingested_at=now_utc.isoformat(),
    )


def _quote_response_from_snapshot(
    symbol: str,
    exchange_code: str,
    currency: str,
    snapshot,
    snap_fresh,
) -> QuoteResponse:
    """Build a QuoteResponse from a persisted snapshot with honest freshness."""
    return QuoteResponse(
        symbol=symbol,
        price=snapshot.price,
        change=snapshot.change,
        change_percent=snapshot.change_percent,
        volume=snapshot.volume,
        high=snapshot.high,
        low=snapshot.low,
        open=snapshot.open,
        previous_close=snapshot.previous_close,
        timestamp=snapshot.timestamp.isoformat(),
        market_status=snapshot.market_status,
        exchange=exchange_code,
        currency=currency,
        provider=snapshot.source,
        freshness=snap_fresh.value,
        delayed=snap_fresh.value == "delayed",
        source_timestamp=snapshot.timestamp.isoformat(),
        ingested_at=snapshot.ingested_at.isoformat() if snapshot.ingested_at else None,
    )


@router.get("/instruments/{symbol}/history", response_model=list[HistoricalPriceResponse])
async def get_history(
    symbol: str,
    exchange_code: str = Query(..., alias="exchange"),
    timeframe: str = Query(default="1d", pattern="^(1m|5m|15m|1h|1d|1w|1M)$"),
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = Query(default=500, ge=1, le=5000),
    session: AsyncSession = Depends(get_session),
) -> list[HistoricalPriceResponse]:
    """Get historical price data for an instrument (newest-biased).

    When the caller omits start/end (the frontend chart path), the window is
    sized from `limit` so 5Y/MAX actually return years of history instead of
    being silently clipped to 365d. get_range returns the newest N rows.
    """
    exchange_repo = ExchangeRepository(session)
    exchange = await exchange_repo.get_by_code(exchange_code)
    if not exchange:
        raise HTTPException(status_code=404, detail="Exchange not found")

    repo = InstrumentRepository(session)
    instrument = await repo.get_by_symbol_exchange(symbol.upper(), exchange.id)
    if not instrument:
        raise HTTPException(status_code=404, detail="Instrument not found")

    # Default window: derive from limit so large chart requests (5Y/MAX)
    # are not silently truncated to 1 year. Daily bars trade ~252d/yr;
    # multiply by 1.6 to cover weekends/holidays.
    if end is None:
        end = datetime.now(UTC)
    if start is None:
        if timeframe in ("1d", "1w", "1M"):
            per_bar_days = {"1d": 1.6, "1w": 8, "1M": 33}[timeframe]
            days = max(365, int(limit * per_bar_days) + 7)
        else:
            # Intraday: keep a bounded recent window.
            days = 30
        start = end - timedelta(days=days)

    price_bar_repo = PriceBarRepository(session)
    bars = await price_bar_repo.get_range(
        instrument.id, timeframe, start, end, limit
    )

    return [
        HistoricalPriceResponse(
            timestamp=bar.timestamp.isoformat(),
            open=bar.open,
            high=bar.high,
            low=bar.low,
            close=bar.close,
            volume=bar.volume,
            vwap=bar.vwap,
        )
        for bar in bars
    ]


@router.post("/instruments/{symbol}/ingest")
async def ingest_instrument(
    symbol: str,
    exchange_code: str = Query(..., alias="exchange"),
    timeframe: str = Query(default="1d", pattern="^(1m|5m|15m|1h|1d|1w|1M)$"),
    session: AsyncSession = Depends(get_session),
    _user=Depends(get_current_user),
) -> dict:
    """Trigger ingestion for a specific instrument (authenticated).

    Previously unauthenticated — anyone could burn provider quota / DoS.
    Now requires a valid JWT; rate limits still apply at the provider layer.
    """
    provider = ProviderFactory.get_fallback_provider()
    if not provider:
        raise HTTPException(status_code=503, detail="No market data provider configured")

    exchange_repo = ExchangeRepository(session)
    exchange = await exchange_repo.get_by_code(exchange_code)
    if not exchange:
        raise HTTPException(status_code=404, detail="Exchange not found")

    ingestion = IngestionService(session, provider)
    # ingest_quotes expects (symbol, exchange_code, market_code) tuples.
    # exchange.market is lazy; select the code directly by FK (see get_quote).
    from apps.api.models.market import Market

    market_code = await session.scalar(select(Market.code).where(Market.id == exchange.market_id))
    result = await ingestion.ingest_quotes([(symbol.upper(), exchange_code, market_code)])
    await session.commit()
    return result
