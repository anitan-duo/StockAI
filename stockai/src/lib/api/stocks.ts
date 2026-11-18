import { api } from './client';
import type { Stock, Quote, HistoricalBar, Timeframe } from '@/types';

export async function searchStocks(query: string): Promise<Stock[]> {
  return api.searchInstruments(query);
}

export async function getStock(symbol: string): Promise<Stock | null> {
  try {
    // This would need an exchange, so we'll use search for now
    const results = await api.searchInstruments(symbol);
    return results[0] || null;
  } catch (err) {
    console.warn('[stocks] getStock failed', err);
    return null;
  }
}

export async function getQuote(symbol: string, exchange: string): Promise<Quote> {
  return api.getQuote(symbol, exchange);
}

export async function getHistoricalData(symbol: string, timeframe: Timeframe, exchange: string): Promise<HistoricalBar[]> {
  return api.getHistory(symbol, exchange, { timeframe });
}

export async function getStocksBySymbols(symbols: string[]): Promise<Stock[]> {
  const results = await Promise.all(
    symbols.map(s => api.searchInstruments(s).then(r => r[0]).catch((err) => {
      console.warn('[stocks] getStock failed', s, err);
      return null;
    }))
  );
  return results.filter((s): s is Stock => s !== null);
}