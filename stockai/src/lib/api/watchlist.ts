import { api } from './client';
import type { Watchlist, WatchlistItem } from '@/types';

export async function getWatchlists() {
  return api.getWatchlists();
}

export async function createWatchlist(data: { name: string; description?: string; is_default?: boolean }) {
  return api.createWatchlist(data);
}

export async function getWatchlist(watchlistId: string) {
  return api.getWatchlist(watchlistId);
}

export async function updateWatchlist(watchlistId: string, data: { name?: string; description?: string; is_default?: boolean }) {
  return api.updateWatchlist(watchlistId, data);
}

export async function deleteWatchlist(watchlistId: string) {
  return api.deleteWatchlist(watchlistId);
}

export async function addToWatchlist(watchlistId: string, instrumentId: string, notes?: string) {
  return api.addToWatchlist(watchlistId, instrumentId, notes);
}

export async function removeFromWatchlist(watchlistId: string, instrumentId: string) {
  return api.removeFromWatchlist(watchlistId, instrumentId);
}

export async function reorderWatchlist(watchlistId: string, itemIds: string[]) {
  return api.reorderWatchlist(watchlistId, itemIds);
}