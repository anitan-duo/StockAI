export { api } from './client';
// Avoid duplicate export of getHistoricalData/getQuote from stocks vs markets
export * as StocksAPI from './stocks';
export * as MarketsAPI from './markets';
export * from './predictions';
export * from './watchlist';
export * from './backtesting';