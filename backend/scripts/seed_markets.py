"""
Seed markets and exchanges - idempotent.

Run: python scripts/seed_markets.py
"""
import asyncio
import sys
from pathlib import Path
from datetime import time

sys.path.insert(0, str(Path(__file__).parent.parent))

from apps.api.database import async_session_factory
from sqlalchemy import select
from apps.api.models.market import Market, Exchange

MARKETS = [
    {
        "code": "US",
        "name": "United States",
        "country_code": "USA",
        "currency": "USD",
        "timezone": "America/New_York",
        "market_open": time(9, 30),
        "market_close": time(16, 0),
        "pre_market_open": time(4, 0),
        "post_market_close": time(20, 0),
    },
    {
        "code": "IN",
        "name": "India",
        "country_code": "IND",
        "currency": "INR",
        "timezone": "Asia/Kolkata",
        "market_open": time(9, 15),
        "market_close": time(15, 30),
        "pre_market_open": time(9, 0),
        "post_market_close": time(16, 0),
    },
    {
        "code": "EU",
        "name": "Europe",
        "country_code": "DEU",
        "currency": "EUR",
        "timezone": "Europe/Berlin",
        "market_open": time(9, 0),
        "market_close": time(17, 30),
        "pre_market_open": time(8, 0),
        "post_market_close": time(20, 0),
    },
]

EXCHANGES = [
    # US
    {"code": "NASDAQ", "name": "NASDAQ", "market_code": "US", "timezone": "America/New_York", "currency": "USD", "market_open": time(9, 30), "market_close": time(16, 0), "pre_market_open": time(4, 0), "post_market_close": time(20, 0)},
    {"code": "NYSE", "name": "New York Stock Exchange", "market_code": "US", "timezone": "America/New_York", "currency": "USD", "market_open": time(9, 30), "market_close": time(16, 0), "pre_market_open": time(4, 0), "post_market_close": time(20, 0)},
    {"code": "NYSEARCA", "name": "NYSE Arca", "market_code": "US", "timezone": "America/New_York", "currency": "USD", "market_open": time(9, 30), "market_close": time(16, 0), "pre_market_open": time(4, 0), "post_market_close": time(20, 0)},
    # India
    {"code": "NSE", "name": "National Stock Exchange of India", "market_code": "IN", "timezone": "Asia/Kolkata", "currency": "INR", "market_open": time(9, 15), "market_close": time(15, 30), "pre_market_open": time(9, 0), "post_market_close": time(16, 0)},
    {"code": "BSE", "name": "Bombay Stock Exchange", "market_code": "IN", "timezone": "Asia/Kolkata", "currency": "INR", "market_open": time(9, 15), "market_close": time(15, 30), "pre_market_open": time(9, 0), "post_market_close": time(16, 0)},
    # Europe
    {"code": "LSE", "name": "London Stock Exchange", "market_code": "EU", "timezone": "Europe/London", "currency": "GBP", "market_open": time(8, 0), "market_close": time(16, 30), "pre_market_open": time(7, 0), "post_market_close": time(17, 0)},
    {"code": "XETRA", "name": "Xetra", "market_code": "EU", "timezone": "Europe/Berlin", "currency": "EUR", "market_open": time(9, 0), "market_close": time(17, 30), "pre_market_open": time(8, 0), "post_market_close": time(20, 0)},
    {"code": "EURONEXT", "name": "Euronext", "market_code": "EU", "timezone": "Europe/Paris", "currency": "EUR", "market_open": time(9, 0), "market_close": time(17, 30), "pre_market_open": time(8, 0), "post_market_close": time(20, 0)},
    {"code": "SIX", "name": "SIX Swiss Exchange", "market_code": "EU", "timezone": "Europe/Zurich", "currency": "CHF", "market_open": time(9, 0), "market_close": time(17, 30), "pre_market_open": time(8, 0), "post_market_close": time(20, 0)},
]

async def seed():
    async with async_session_factory() as session:
        # Markets
        for m in MARKETS:
            existing = await session.execute(select(Market).where(Market.code == m["code"]))
            if existing.scalar_one_or_none():
                print(f"Market {m['code']} exists, skipping")
                continue
            market = Market(**m)
            session.add(market)
            await session.flush()
            print(f"Created market {m['code']}")

        await session.commit()

        # Build market code -> id map
        result = await session.execute(select(Market))
        markets = {m.code: m for m in result.scalars().all()}

        # Exchanges
        for e in EXCHANGES:
            market = markets.get(e["market_code"])
            if not market:
                print(f"Market {e['market_code']} not found for exchange {e['code']}, skipping")
                continue
            existing = await session.execute(select(Exchange).where(Exchange.code == e["code"]))
            if existing.scalar_one_or_none():
                print(f"Exchange {e['code']} exists, skipping")
                continue
            exch_data = {k: v for k, v in e.items() if k != "market_code"}
            exch_data["market_id"] = market.id
            exch = Exchange(**exch_data)
            session.add(exch)
            await session.flush()
            print(f"Created exchange {e['code']} -> {e['market_code']}")

        await session.commit()
        print("Seed complete")

        # Verify counts
        for tbl, model in [("markets", Market), ("exchanges", Exchange)]:
            result = await session.execute(select(model))
            count = len(result.scalars().all())
            print(f"{tbl}: {count}")

if __name__ == "__main__":
    asyncio.run(seed())
