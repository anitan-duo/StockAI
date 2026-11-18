import { api } from './client';
import type { Prediction, PredictionHistory, PredictionHistoryItem, ScreenerResult } from '@/types';

export async function getPrediction(symbol: string, exchange: string, horizon = '1d'): Promise<Prediction | null> {
  try {
    return await api.getPrediction(symbol, exchange, horizon);
  } catch (err) {
    console.warn('[predictions] getPrediction failed', err);
    return null;
  }
}

export async function getPredictions(symbols: string[], exchange: string, horizon = '1d'): Promise<Prediction[]> {
  const results = await Promise.all(
    symbols.map(s => api.getPrediction(s, exchange, horizon).catch((err) => {
      console.warn('[predictions] getPrediction failed', s, err);
      return null;
    }))
  );
  return results.filter((p): p is Prediction => p !== null);
}

export async function getPredictionHistory(symbol: string, exchange: string, horizon = '1d', limit = 100): Promise<PredictionHistory> {
  return api.getPredictionHistory(symbol, exchange, horizon, limit);
}

export async function getPredictionFactors(symbol: string, exchange: string, horizon = '1d') {
  return api.getPredictionFactors(symbol, exchange, horizon);
}

export async function getTopPredictions(filters?: {
  market?: string;
  direction?: 'up' | 'neutral' | 'down';
  confidenceMin?: number;
  expectedReturnMin?: number;
  limit?: number;
}): Promise<Prediction[]> {
  return api.getTopPredictions(filters);
}

export async function getScreenerPredictions(filters: Record<string, unknown>): Promise<ScreenerResult[]> {
  return api.screenStocks(filters);
}