const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1';

class ApiClient {
  private baseUrl: string;
  private accessToken: string | null = null;
  private refreshToken: string | null = null;
  private isRefreshing = false;
  private refreshPromise: Promise<boolean> | null = null;

  constructor(baseUrl: string = API_BASE_URL) {
    this.baseUrl = baseUrl;
    if (typeof window !== 'undefined') {
      this.accessToken = localStorage.getItem('access_token');
      this.refreshToken = localStorage.getItem('refresh_token');
    }
  }

  isAuthenticated(): boolean {
    if (typeof window !== 'undefined') {
      // re-read in case another tab changed it
      this.accessToken = localStorage.getItem('access_token');
      this.refreshToken = localStorage.getItem('refresh_token');
    }
    return !!this.accessToken;
  }

  hasRefreshToken(): boolean {
    if (typeof window !== 'undefined') {
      this.refreshToken = localStorage.getItem('refresh_token');
    }
    return !!this.refreshToken;
  }

  setTokens(accessToken: string, refreshToken: string) {
    this.accessToken = accessToken;
    this.refreshToken = refreshToken;
    if (typeof window !== 'undefined') {
      localStorage.setItem('access_token', accessToken);
      localStorage.setItem('refresh_token', refreshToken);
    }
  }

  clearTokens() {
    this.accessToken = null;
    this.refreshToken = null;
    if (typeof window !== 'undefined') {
      localStorage.removeItem('access_token');
      localStorage.removeItem('refresh_token');
    }
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const url = `${this.baseUrl}${endpoint}`;
    const headers: HeadersInit = {
      'Content-Type': 'application/json',
      ...options.headers,
    };

    // ensure tokens are fresh from storage before each request
    if (typeof window !== 'undefined' && !this.accessToken) {
      this.accessToken = localStorage.getItem('access_token');
    }

    const isAuthEndpoint = endpoint.startsWith('/auth/');
    const hadAuthHeader = !!this.accessToken;

    if (this.accessToken) {
      (headers as Record<string, string>)['Authorization'] = `Bearer ${this.accessToken}`;
    }

    const response = await fetch(url, {
      ...options,
      headers,
    });

    if (response.status === 401) {
      // Do not attempt refresh for auth endpoints themselves (login/register/refresh) - they legitimately return 401
      if (isAuthEndpoint) {
        throw new Error((await response.json().catch(() => ({ detail: 'Unauthorized' }))).detail || 'Unauthorized');
      }
      // Only attempt refresh if we had a token and we have a refresh token, and we are not already handling a 401
      if (!hadAuthHeader || !this.hasRefreshToken()) {
        // No token to refresh - just throw, let caller handle (do NOT redirect here)
        throw new Error('Unauthorized');
      }

      const refreshed = await this.refreshAccessToken();
      if (refreshed) {
        // Retry with new token
        const retryHeaders: HeadersInit = {
          'Content-Type': 'application/json',
          ...options.headers,
          Authorization: `Bearer ${this.accessToken}`,
        };
        const retryResponse = await fetch(url, {
          ...options,
          headers: retryHeaders,
        });
        if (retryResponse.ok) {
          return retryResponse.json();
        }
        // retry also 401 - fall through to throw
        if (retryResponse.status === 401) {
          this.clearTokens();
          throw new Error('Unauthorized');
        }
        // other error on retry - handle as normal response below
        if (!retryResponse.ok) {
          const error = await retryResponse.json().catch(() => ({ detail: 'Request failed' }));
          throw new Error(error.detail || `Request failed with status ${retryResponse.status}`);
        }
        return retryResponse.json();
      }
      // refresh failed - clear and throw, do NOT auto-redirect (caller decides)
      this.clearTokens();
      throw new Error('Unauthorized');
    }

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Request failed' }));
      const detail = error?.detail;
      const message =
        typeof detail === 'string'
          ? detail
          : detail?.reason || detail?.message || (detail ? JSON.stringify(detail) : `Request failed with status ${response.status}`);
      throw new Error(message);
    }

    if (response.status === 204) {
      return undefined as T;
    }

    return response.json();
  }

  private async refreshAccessToken(): Promise<boolean> {
    if (!this.hasRefreshToken()) return false;

    // Prevent simultaneous refresh requests
    if (this.isRefreshing && this.refreshPromise) {
      return this.refreshPromise;
    }

    this.isRefreshing = true;
    this.refreshPromise = (async () => {
      try {
        const token = typeof window !== 'undefined' ? localStorage.getItem('refresh_token') : this.refreshToken;
        if (!token) return false;
        const response = await fetch(`${this.baseUrl}/auth/refresh`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ refresh_token: token }),
        });

        if (!response.ok) return false;

        const data = await response.json();
        this.setTokens(data.access_token, data.refresh_token);
        return true;
      } catch (err) {
        console.warn('[api] refresh token failed', err);
        return false;
      } finally {
        this.isRefreshing = false;
        this.refreshPromise = null;
      }
    })();

    return this.refreshPromise;
  }

  // Auth
  async login(email: string, password: string, rememberMe = false) {
    const data = await this.request<{
      access_token: string;
      refresh_token: string;
      token_type: string;
      expires_in: number;
    }>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password, remember_me: rememberMe }),
    });
    this.setTokens(data.access_token, data.refresh_token);
    return data;
  }

  async register(email: string, password: string, fullName?: string) {
    const data = await this.request<{
      user: any;
      tokens: { access_token: string; refresh_token: string; token_type: string; expires_in: number };
    }>('/auth/register', {
      method: 'POST',
      body: JSON.stringify({ email, password, full_name: fullName }),
    });
    this.setTokens(data.tokens.access_token, data.tokens.refresh_token);
    return data;
  }

  async logout() {
    await this.request('/auth/logout', {
      method: 'POST',
    });
    this.clearTokens();
  }

  async refresh() {
    const data = await this.request<{
      access_token: string;
      refresh_token: string;
      token_type: string;
      expires_in: number;
    }>('/auth/refresh', {
      method: 'POST',
      body: JSON.stringify({ refresh_token: this.refreshToken }),
    });
    this.setTokens(data.access_token, data.refresh_token);
    return data;
  }

  async getMe() {
    return this.request<any>('/auth/me');
  }

  async forgotPassword(email: string) {
    return this.request<any>('/auth/forgot-password', {
      method: 'POST',
      body: JSON.stringify({ email }),
    });
  }

  async resetPassword(token: string, newPassword: string) {
    return this.request<any>('/auth/reset-password', {
      method: 'POST',
      body: JSON.stringify({ token, new_password: newPassword }),
    });
  }

  // Generic request for custom endpoints (public wrapper)
  async customRequest<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
    return this.request<T>(endpoint, options);
  }

  // Markets
  async getMarkets() {
    return this.request<any[]>('/markets');
  }

  /** Market overview: major indices + movers, each with backend-classified freshness. */
  async getMarketOverview() {
    return this.request<any>('/markets/overview');
  }

  async getMarket(marketCode: string) {
    return this.request<any>(`/markets/${marketCode}`);
  }

  async getExchanges(marketCode: string) {
    return this.request<any[]>(`/markets/${marketCode}/exchanges`);
  }

  async getExchange(exchangeCode: string, marketCode?: string) {
    const params = marketCode ? `?market_code=${marketCode}` : '';
    return this.request<any>(`/markets/exchanges/${exchangeCode}${params}`);
  }

  async searchInstruments(query: string, options?: {
    market?: string;
    exchange?: string;
    type?: string;
    limit?: number;
  }) {
    const params = new URLSearchParams();
    params.append('q', query);
    if (options?.market) params.append('market', options.market);
    if (options?.exchange) params.append('exchange', options.exchange);
    if (options?.type) params.append('type', options.type);
    if (options?.limit) params.append('limit', options.limit.toString());
    return this.request<any[]>(`/markets/instruments/search?${params.toString()}`);
  }

  async getInstrument(symbol: string, exchange: string) {
    return this.request<any>(`/markets/instruments/${symbol}?exchange=${exchange}`);
  }

  async getQuote(symbol: string, exchange: string) {
    return this.request<any>(`/markets/instruments/${symbol}/quote?exchange=${exchange}`);
  }

  async getHistory(symbol: string, exchange: string, options?: {
    timeframe?: string;
    start?: string;
    end?: string;
    limit?: number;
  }) {
    const params = new URLSearchParams();
    params.append('exchange', exchange);
    if (options?.timeframe) params.append('timeframe', options.timeframe);
    if (options?.start) params.append('start', options.start);
    if (options?.end) params.append('end', options.end);
    if (options?.limit) params.append('limit', options.limit.toString());
    return this.request<any[]>(`/markets/instruments/${symbol}/history?${params.toString()}`);
  }

  async ingestInstrument(symbol: string, exchange: string, timeframe = '1d') {
    return this.request<any>(`/markets/instruments/${symbol}/ingest?exchange=${exchange}&timeframe=${timeframe}`, {
      method: 'POST',
    });
  }

  // Predictions
  async getPrediction(symbol: string, exchange: string, horizon = '1d') {
    return this.request<any>(`/predictions/stocks/${symbol}?exchange=${exchange}&horizon=${horizon}`);
  }

  async getPredictionHistory(symbol: string, exchange: string, horizon = '1d', limit = 100) {
    return this.request<any>(`/predictions/stocks/${symbol}/history?exchange=${exchange}&horizon=${horizon}&limit=${limit}`);
  }

  async getPredictionFactors(symbol: string, exchange: string, horizon = '1d') {
    return this.request<any>(`/predictions/stocks/${symbol}/factors?exchange=${exchange}&horizon=${horizon}`);
  }

  async getPredictionExplanation(predictionId: string) {
    return this.request<any>(`/predictions/${predictionId}/explanation`);
  }

  async getStockRsi(symbol: string, exchange: string) {
    return this.request<any>(`/predictions/stocks/${symbol}/rsi?exchange=${encodeURIComponent(exchange)}`);
  }

  async getTopPredictions(options?: {
    horizon?: string;
    direction?: string;
    confidenceMin?: number;
    expectedReturnMin?: number;
    limit?: number;
  }) {
    const params = new URLSearchParams();
    if (options?.horizon) params.append('horizon', options.horizon);
    if (options?.direction) params.append('direction', options.direction);
    if (options?.confidenceMin) params.append('confidence_min', options.confidenceMin.toString());
    if (options?.expectedReturnMin) params.append('expected_return_min', options.expectedReturnMin.toString());
    if (options?.limit) params.append('limit', options.limit.toString());
    return this.request<any[]>(`/predictions?${params.toString()}`);
  }

  // Rankings (cross-sectional relative performance)
  async getRankings(options?: { market?: string; horizon?: string; limit?: number }) {
    const params = new URLSearchParams();
    if (options?.market) params.append('market', options.market);
    if (options?.horizon) params.append('horizon', options.horizon);
    if (options?.limit) params.append('limit', options.limit.toString());
    return this.request<any>(`/rankings?${params.toString()}`);
  }

  async refreshRankings(options?: { market?: string; horizon?: string; limit?: number }) {
    const params = new URLSearchParams();
    if (options?.market) params.append('market', options.market);
    if (options?.horizon) params.append('horizon', options.horizon);
    if (options?.limit) params.append('limit', options.limit.toString());
    return this.request<any>(`/rankings/refresh?${params.toString()}`, { method: 'POST' });
  }

  async getRankingPerformance(options?: { market?: string; horizon?: string }) {
    const params = new URLSearchParams();
    if (options?.market) params.append('market', options.market);
    if (options?.horizon) params.append('horizon', options.horizon);
    return this.request<any>(`/rankings/performance?${params.toString()}`);
  }

  // Screener
  async screenStocks(filters: any, page = 1, pageSize = 20) {
    return this.request<any>('/screener', {
      method: 'POST',
      body: JSON.stringify({ ...filters, page, page_size: pageSize }),
    });
  }

  async getSectors() {
    return this.request<string[]>('/screener/filters/sectors');
  }

  async getScreenerExchanges(market?: string) {
    const params = market ? `?market=${market}` : '';
    return this.request<any[]>(`/screener/filters/exchanges${params}`);
  }

  // Keep alias for backwards compat but delegate
  async getExchangesFiltered(market?: string) {
    return this.getScreenerExchanges(market);
  }

  // Watchlist
  async getWatchlists() {
    return this.request<any[]>('/watchlist');
  }

  async createWatchlist(data: { name: string; description?: string; is_default?: boolean }) {
    return this.request<any>('/watchlist', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async getWatchlist(watchlistId: string) {
    return this.request<any>(`/watchlist/${watchlistId}`);
  }

  async updateWatchlist(watchlistId: string, data: { name?: string; description?: string; is_default?: boolean }) {
    return this.request<any>(`/watchlist/${watchlistId}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  }

  async deleteWatchlist(watchlistId: string) {
    return this.request<void>(`/watchlist/${watchlistId}`, {
      method: 'DELETE',
    });
  }

  async addToWatchlist(watchlistId: string, instrumentId: string, notes?: string) {
    return this.request<any>(`/watchlist/${watchlistId}/items`, {
      method: 'POST',
      body: JSON.stringify({ instrument_id: instrumentId, notes }),
    });
  }

  async removeFromWatchlist(watchlistId: string, instrumentId: string) {
    return this.request<void>(`/watchlist/${watchlistId}/items/${instrumentId}`, {
      method: 'DELETE',
    });
  }

  async reorderWatchlist(watchlistId: string, itemIds: string[]) {
    return this.request<any>(`/watchlist/${watchlistId}/reorder`, {
      method: 'PUT',
      body: JSON.stringify(itemIds),
    });
  }

  // Alerts
  async getAlerts(status?: string) {
    const params = status ? `?status=${status}` : '';
    return this.request<any[]>(`/alerts${params}`);
  }

  async createAlert(data: {
    instrument_id: string;
    name: string;
    alert_type: string;
    condition: string;
    target_value: number;
    secondary_value?: number;
    expires_at?: string;
    notify_email?: boolean;
    notify_push?: boolean;
    notify_in_app?: boolean;
  }) {
    return this.request<any>('/alerts', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async getAlert(alertId: string) {
    return this.request<any>(`/alerts/${alertId}`);
  }

  async updateAlert(alertId: string, data: {
    name?: string;
    target_value?: number;
    secondary_value?: number;
    expires_at?: string;
    notify_email?: boolean;
    notify_push?: boolean;
    notify_in_app?: boolean;
    status?: string;
  }) {
    return this.request<any>(`/alerts/${alertId}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  }

  async acknowledgeAlert(alertId: string) {
    return this.request<any>(`/alerts/${alertId}/acknowledge`, {
      method: 'POST',
    });
  }

  async disableAlert(alertId: string) {
    return this.request<any>(`/alerts/${alertId}/disable`, {
      method: 'POST',
    });
  }

  async deleteAlert(alertId: string) {
    return this.request<void>(`/alerts/${alertId}`, {
      method: 'DELETE',
    });
  }

  async getAlertTriggers(alertId: string, limit = 50) {
    return this.request<any[]>(`/alerts/${alertId}/triggers?limit=${limit}`);
  }

  async getAlertTypes() {
    return this.request<any>('/alerts/types/available');
  }

  // MLOps (reads: authenticated; mutations: admin only, enforced server-side)
  async getChampion() {
    return this.request<any>('/mlops/champion');
  }

  async getExperiments(status?: string, limit = 50) {
    const params = new URLSearchParams();
    if (status) params.append('status', status);
    params.append('limit', String(limit));
    return this.request<any>(`/mlops/experiments?${params.toString()}`);
  }

  async getExperiment(experimentId: string) {
    return this.request<any>(`/mlops/experiments/${encodeURIComponent(experimentId)}`);
  }

  async getTrainingJobs(status?: string, limit = 50) {
    const params = new URLSearchParams();
    if (status) params.append('status', status);
    params.append('limit', String(limit));
    return this.request<any>(`/mlops/jobs?${params.toString()}`);
  }

  async getPromotions(limit = 50) {
    return this.request<any>(`/mlops/promotions?limit=${limit}`);
  }

  async getMlMonitoring() {
    return this.request<any>('/mlops/monitoring');
  }

  async getAnalyticsPerformance(options?: { days?: number; symbol?: string; exchange?: string; recentLimit?: number }) {
    const params = new URLSearchParams();
    params.append('days', String(options?.days ?? 90));
    if (options?.symbol) params.append('symbol', options.symbol);
    if (options?.exchange) params.append('exchange', options.exchange);
    if (options?.recentLimit) params.append('recent_limit', String(options.recentLimit));
    return this.request<any>(`/analytics/performance?${params.toString()}`);
  }

  async acknowledgeDrift(observationId: string) {
    return this.request<any>(`/mlops/drift/${observationId}/acknowledge`, {
      method: 'POST',
    });
  }

  async rejectExperiment(experimentId: string, reason: string) {
    return this.request<any>(
      `/mlops/experiments/${encodeURIComponent(experimentId)}/reject?reason=${encodeURIComponent(reason)}`,
      { method: 'POST' },
    );
  }

  async approveExperiment(experimentId: string, rationale: string) {
    return this.request<any>(
      `/mlops/experiments/${encodeURIComponent(experimentId)}/approve?rationale=${encodeURIComponent(rationale)}`,
      { method: 'POST' },
    );
  }

  async rollbackChampion(rationale: string) {
    return this.request<any>(`/mlops/rollback?rationale=${encodeURIComponent(rationale)}`, {
      method: 'POST',
    });
  }

  async triggerEvolution() {
    return this.request<any>('/mlops/jobs/run-evolution', { method: 'POST' });
  }

  // Backtests
  async getBacktests(options?: {
    status?: string;
    skip?: number;
    limit?: number;
  }) {
    const params = new URLSearchParams();
    if (options?.status) params.append('status', options.status);
    if (options?.skip) params.append('skip', options.skip.toString());
    if (options?.limit) params.append('limit', options.limit.toString());
    return this.request<any[]>(`/backtests${params.toString() ? `?${params.toString()}` : ''}`);
  }

  async createBacktest(data: {
    instrument_id: string;
    model_version_id: string;
    start_date: string;
    end_date: string;
    horizon: string;
    initial_capital: number;
  }) {
    return this.request<any>('/backtests', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async getBacktest(backtestId: string) {
    return this.request<any>(`/backtests/${backtestId}`);
  }

  async runBacktest(backtestId: string) {
    return this.request<any>(`/backtests/${backtestId}/run`, {
      method: 'POST',
    });
  }

  async deleteBacktest(backtestId: string) {
    return this.request<void>(`/backtests/${backtestId}`, {
      method: 'DELETE',
    });
  }

  // Health
  async healthCheck() {
    return this.request<any>('/health');
  }

  async readinessCheck() {
    return this.request<any>('/health/ready');
  }

  // Scenario lab (blind challenges; blindness enforced server-side)
  async getForecastTasks() {
    return this.request<any>('/scenarios/tasks');
  }

  async createScenario(data: {
    symbol: string;
    exchange: string;
    decision_date: string;
    task_id?: string;
    split?: string;
  }) {
    const params = new URLSearchParams({
      symbol: data.symbol,
      exchange: data.exchange,
      decision_date: data.decision_date,
      task_id: data.task_id ?? 'h1d',
      split: data.split ?? 'train',
    });
    return this.request<any>(`/scenarios?${params.toString()}`, { method: 'POST' });
  }

  async getScenarioBars(scenarioId: string, limit = 400) {
    return this.request<any>(`/scenarios/${scenarioId}/bars?limit=${limit}`);
  }

  async submitChallenge(
    scenarioId: string,
    data: {
      experiment_id: string;
      up: number;
      neutral: number;
      down: number;
      action: string;
      model_version?: string;
    },
  ) {
    const params = new URLSearchParams({
      experiment_id: data.experiment_id,
      up: String(data.up),
      neutral: String(data.neutral),
      down: String(data.down),
      action: data.action,
      model_version: data.model_version ?? 'ensemble-v1.0',
    });
    return this.request<any>(`/scenarios/${scenarioId}/submit?${params.toString()}`, {
      method: 'POST',
    });
  }

  async revealChallenge(attemptId: string) {
    return this.request<any>(`/scenarios/attempts/${attemptId}/reveal`, {
      method: 'POST',
    });
  }

  async getChallengeAttempts(experimentId?: string, limit = 20) {
    const params = new URLSearchParams({ limit: String(limit) });
    if (experimentId) params.append('experiment_id', experimentId);
    return this.request<any>(`/scenarios/attempts?${params.toString()}`);
  }

  async getStreaks(experimentId?: string) {
    const params = experimentId ? `?experiment_id=${encodeURIComponent(experimentId)}` : '';
    return this.request<any>(`/scenarios/streaks${params}`);
  }

  async getAttemptDiagnosis(attemptId: string) {
    return this.request<any>(`/scenarios/attempts/${attemptId}/diagnosis`);
  }
}

export const api = new ApiClient();
export default api;