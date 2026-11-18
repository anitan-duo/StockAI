export interface Stock {
  symbol: string;
  name: string;
  exchange: string;
  currency: string;
  sector?: string;
  industry?: string;
  marketCap?: number;
}

export interface Quote {
  symbol: string;
  price: number;
  change: number;
  changePercent: number;
  volume: number;
  high: number;
  low: number;
  open: number;
  previousClose: number;
  timestamp: string;
  marketStatus: 'open' | 'closed' | 'pre-market' | 'after-hours' | string;
  /** Backend-classified data status: fresh | recent | delayed | stale | unavailable */
  freshness?: string;
  /** Provider that supplied the data (e.g. yahoo_finance, finnhub) */
  provider?: string | null;
  /** Provider-reported source time of the data */
  sourceTimestamp?: string | null;
  /** When our system fetched/persisted the data */
  ingestedAt?: string | null;
  exchange?: string | null;
  currency?: string | null;
}

export interface HistoricalBar {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface Prediction {
  symbol: string;
  horizon: '1d';
  direction: 'up' | 'neutral' | 'down';
  probabilities: {
    up: number;
    neutral: number;
    down: number;
  };
  expectedReturn: number;
  expectedRange: {
    low: number;
    high: number;
  };
  confidence: number | null;
  modelVersion: string;
  dataTimestamp: string;
  noClearEdge: boolean;
  factors: {
    positive: string[];
    neutral: string[];
    negative: string[];
  };
}

export interface PredictionHistoryItem {
  date: string;
  prediction: 'up' | 'neutral' | 'down';
  upProbability: number;
  expectedReturn: number;
  actualReturn: number | null;
  actualDirection?: 'up' | 'neutral' | 'down' | null;
  result: 'correct' | 'incorrect' | 'neutral' | 'pending' | null;
  countedInAccuracy?: boolean;
}

export interface PredictionHistory {
  symbol: string;
  items: PredictionHistoryItem[];
  summary: {
    totalPredictions: number;
    correctPredictions: number;
    incorrectPredictions?: number;
    neutralPredictions?: number;
    neutralCorrect?: number;
    directionalCount?: number;
    /** Canonical directional hit rate in percent; null when unreliable/absent. */
    accuracy: number | null;
    accuracyReliable?: boolean;
    minimumSample?: number;
    confidenceIntervalLower?: number | null;
    confidenceIntervalUpper?: number | null;
    coverage?: number | null;
    scoringPolicy?: string | null;
    averageReturn: number;
    completedCount?: number;
    pendingCount?: number;
  };
}

export interface MarketIndex {
  symbol: string;
  name: string;
  price: number;
  change: number;
  changePercent: number;
  status: 'open' | 'closed' | 'pre-market' | 'after-hours';
  timestamp: string;
  region: 'us' | 'europe' | 'india';
}

export interface MarketMover {
  symbol: string;
  name: string;
  price: number;
  change: number;
  changePercent: number;
  volume: number;
}

export interface MarketData {
  indices: MarketIndex[];
  gainers: MarketMover[];
  losers: MarketMover[];
  highVolume: MarketMover[];
  sectorPerformance: SectorPerformance[];
}

export interface SectorPerformance {
  sector: string;
  changePercent: number;
}

export interface WatchlistItem {
  symbol: string;
  name: string;
  price: number;
  change: number;
  changePercent: number;
  prediction?: Prediction;
  exchange?: string;
  sector?: string;
  volume?: number;
  rsi?: number;
  volatility?: number;
}

export interface BacktestConfig {
  symbol: string;
  strategy: string;
  startDate: string;
  endDate: string;
  horizon: '1d' | '1w' | '1m';
  initialCapital: number;
}

export interface BacktestResult {
  config: BacktestConfig;
  totalReturn: number;
  annualizedReturn: number;
  sharpeRatio: number;
  maxDrawdown: number;
  winRate: number;
  profitFactor: number;
  equityCurve: { date: string; value: number }[];
  drawdownCurve: { date: string; value: number }[];
  returnsDistribution: { range: string; count: number }[];
  trades: BacktestTrade[];
}

export interface BacktestTrade {
  date: string;
  action: 'buy' | 'sell';
  price: number;
  shares: number;
  value: number;
  return?: number;
}

export interface ScreenerFilter {
  market?: string[];
  exchange?: string[];
  sector?: string[];
  priceMin?: number;
  priceMax?: number;
  performanceMin?: number;
  performanceMax?: number;
  rsiMin?: number;
  rsiMax?: number;
  volatilityMin?: number;
  volatilityMax?: number;
  predictionProbabilityMin?: number;
  expectedReturnMin?: number;
  confidenceMin?: number;
}

export interface ScreenerResult {
  symbol: string;
  name: string;
  exchange: string;
  price: number;
  changePercent: number;
  sector: string;
  rsi?: number;
  volatility?: number;
  prediction?: Prediction;
}

export interface User {
  id: string;
  email: string;
  name: string;
  avatar?: string;
  preferences: UserPreferences;
}

export interface UserPreferences {
  theme: 'light' | 'dark' | 'system';
  defaultMarket: string;
  defaultHorizon: '1d' | '1w' | '1m';
  notifications: {
    email: boolean;
    push: boolean;
    predictions: boolean;
    alerts: boolean;
  };
}

export interface Alert {
  id: string;
  symbol: string;
  type: 'price' | 'prediction' | 'volume' | 'technical';
  condition: string;
  targetValue: number;
  enabled: boolean;
  createdAt: string;
}

export type Timeframe = '1D' | '1W' | '1M' | '3M' | '6M' | '1Y' | '5Y' | 'MAX' | '1d' | '1w' | '1m' | '3m' | '6m' | '1y' | '5y' | 'max';

export interface Market {
  code: string;
  name: string;
  country_code: string;
  currency: string;
  timezone: string;
  is_active: boolean;
}

export interface Exchange {
  code: string;
  name: string;
  market: string;
  currency: string;
}

export interface Instrument {
  symbol: string;
  name: string;
  exchange: string;
  currency: string;
  sector?: string;
}

export interface Watchlist {
  id: string;
  name: string;
  description?: string;
  is_default: boolean;
  items?: WatchlistItem[];
}

export type ChartType = 'line' | 'candlestick' | 'area';

export interface ChartIndicator {
  id: string;
  name: string;
  enabled: boolean;
  params?: Record<string, number | string>;
}
export interface RankingEntry {
  instrument_id: string;
  symbol: string;
  exchange: string;
  rank: number;
  score: number;
  percentile: number;
  quintile: number;
  relative_label: string;
}

export interface RankingSnapshot {
  market: string | null;
  horizon: '1d' | '5d' | '10d';
  as_of_date: string;
  generated_at: string;
  objective: string;
  model_version: string;
  artifact_sha: string;
  feature_version: string;
  universe_size: number;
  market_universe_size: number;
  ranked_count: number;
  excluded: Record<string, string>;
  entries: RankingEntry[];
  evaluation: Record<string, unknown>;
  caveats: string[];
  score_semantics: string | null;
}

export interface RankingQuintilePerformance {
  n: number;
  hit_rate: number | null;
}

export interface RankingPerformance {
  market: string;
  horizon: string;
  n_outcomes: number;
  hit_rate: number | null;
  reliable: boolean;
  mean_snapshot_rank_ic: number | null;
  by_quintile: Record<string, RankingQuintilePerformance>;
}
