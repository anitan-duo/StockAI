"""
Seed instruments - validates via provider before inserting, idempotent.
Run: python scripts/seed_instruments.py
"""
import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from apps.api.database import async_session_factory
from apps.api.models.market import Exchange, Market, Instrument
from services.ingestion.providers.factory import ProviderFactory

# Candidate universe - will be validated via provider
CANDIDATES = [
    # US
    ("AAPL", "NASDAQ", "US", "Apple Inc.", "Technology", "Consumer Electronics"),
    ("MSFT", "NASDAQ", "US", "Microsoft Corporation", "Technology", "Software"),
    ("GOOGL", "NASDAQ", "US", "Alphabet Inc.", "Technology", "Internet"),
    ("AMZN", "NASDAQ", "US", "Amazon.com Inc.", "Consumer Cyclical", "Internet Retail"),
    ("NVDA", "NASDAQ", "US", "NVIDIA Corporation", "Technology", "Semiconductors"),
    ("META", "NASDAQ", "US", "Meta Platforms", "Technology", "Internet"),
    ("TSLA", "NASDAQ", "US", "Tesla Inc.", "Consumer Cyclical", "Auto Manufacturers"),
    # India
    ("RELIANCE", "NSE", "IN", "Reliance Industries", "Energy", "Oil & Gas"),
    ("TCS", "NSE", "IN", "Tata Consultancy Services", "Technology", "IT Services"),
    ("INFY", "NSE", "IN", "Infosys Ltd", "Technology", "IT Services"),
    ("HDFCBANK", "NSE", "IN", "HDFC Bank Ltd", "Financial Services", "Banks"),
    ("ICICIBANK", "NSE", "IN", "ICICI Bank Ltd", "Financial Services", "Banks"),
    ("SBIN", "NSE", "IN", "State Bank of India", "Financial Services", "Banks"),
    # UK
    ("HSBA", "LSE", "EU", "HSBC Holdings", "Financial Services", "Banks"),
    ("SHEL", "LSE", "EU", "Shell plc", "Energy", "Oil & Gas"),
    ("AZN", "LSE", "EU", "AstraZeneca plc", "Healthcare", "Biotechnology"),
    # Germany
    ("SAP", "XETRA", "EU", "SAP SE", "Technology", "Software"),
    ("SIE", "XETRA", "EU", "Siemens AG", "Industrials", "Conglomerates"),
    # Additional
    ("ASML", "XETRA", "EU", "ASML Holding", "Technology", "Semiconductors"),
]

async def seed():
    # First validate providers are available
    fallback = ProviderFactory.get_fallback_provider()
    # Build exchange map
    async with async_session_factory() as session:
        result = await session.execute(select(Exchange))
        exchanges = {e.code: e for e in result.scalars().all()}
        print(f"Exchanges in DB: {list(exchanges.keys())}")
        if not exchanges:
            print("No exchanges found, run seed_markets.py first")
            return

        inserted = 0
        skipped = 0
        validated = 0
        for symbol, exch_code, market_code, name, sector, industry in CANDIDATES:
            exch = exchanges.get(exch_code)
            if not exch:
                print(f"Exchange {exch_code} not found for {symbol}, skipping")
                skipped += 1
                continue
            # Check exists
            existing = await session.execute(select(Instrument).where(Instrument.symbol == symbol, Instrument.exchange_id == exch.id))
            if existing.scalar_one_or_none():
                print(f"{symbol}:{exch_code} exists, skipping")
                skipped += 1
                continue
            # Validate via provider (optional - if provider fails, still insert with warning)
            try:
                info = await fallback.get_instrument(symbol, exch_code, market_code)
                if info:
                    name = info.name or name
                    validated += 1
                    print(f"Validated {symbol}:{exch_code} via {info.metadata.get('source','provider')}")
                else:
                    print(f"Warning: {symbol}:{exch_code} not validated via provider, inserting anyway")
            except Exception as e:
                print(f"Warning: provider validation failed for {symbol}:{exch_code}: {e}, inserting anyway")

            inst = Instrument(
                symbol=symbol,
                name=name,
                exchange_id=exch.id,
                currency=exch.currency,
                sector=sector,
                industry=industry,
                is_active=True,
                is_tradable=True,
            )
            session.add(inst)
            await session.flush()
            print(f"Inserted {symbol}:{exch_code}")
            inserted += 1

        await session.commit()
        print(f"\nDone: inserted {inserted}, skipped {skipped}, validated {validated}")
        # Verify counts
        result = await session.execute(select(Instrument))
        all_insts = result.scalars().all()
        print(f"Total instruments: {len(all_insts)}")
        # Show sample
        for inst in all_insts[:5]:
            print(f"  - {inst.symbol} ({inst.exchange.code if hasattr(inst.exchange, 'code') else inst.exchange_id})")

    await ProviderFactory.close_all()

if __name__ == "__main__":
    asyncio.run(seed())
