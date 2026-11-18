import { api } from './client';
import type { BacktestResult, BacktestTrade } from '@/types';

export async function runBacktest(config: unknown): Promise<BacktestResult> {
  return api.createBacktest(config as never);
}

export async function getBacktest(backtestId: string): Promise<BacktestResult> {
  return api.getBacktest(backtestId);
}

export async function runBacktestById(backtestId: string): Promise<BacktestResult> {
  return api.runBacktest(backtestId);
}

export async function getBacktestStrategies(): Promise<string[]> {
  // This would be an endpoint on the backend
  return ['ML Ensemble v1.0', 'Momentum + ML', 'Mean Reversion + ML', 'Trend Following + ML'];
}