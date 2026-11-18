import { api } from './client';
import type { Market, Exchange, Instrument, Quote, HistoricalBar, Timeframe } from '@/types';

export async function getMarkets() {
  return api.getMarkets();
}

export async function getExchanges(marketCode: string) {
  return api.getExchanges(marketCode);
}

export async function searchInstruments(query: string, options?: {
  market?: string;
  exchange?: string;
  type?: string;
  limit?: number;
}) {
  return api.searchInstruments(query, options);
}

export async function getInstrument(symbol: string, exchange: string) {
  return api.getInstrument(symbol, exchange);
}

export async function getQuote(symbol: string, exchange: string) {
  return api.getQuote(symbol, exchange);
}

export async function getHistoricalData(symbol: string, exchange: string, timeframe: Timeframe = '1d', start?: string, end?: string, limit = 500) {
  return api.getHistory(symbol, exchange, { timeframe, start, end, limit });
}

export async function ingestInstrument(symbol: string, exchange: string, timeframe: Timeframe = '1d') {
  return api.ingestInstrument(symbol, exchange, timeframe);
}