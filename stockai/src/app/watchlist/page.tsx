'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api/client';
import {
  getWatchlists,
  createWatchlist,
  getWatchlist,
  addToWatchlist,
  removeFromWatchlist,
  updateWatchlist,
  deleteWatchlist,
  reorderWatchlist,
} from '@/lib/api/watchlist';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  Star,
  Search,
  Plus,
  Trash2,
  Pencil,
  GripVertical,
  ArrowUpDown,
  ArrowUp,
  ArrowDown,
  Loader2,
  AlertCircle,
  CheckCircle2,
  X,
  StarOff,
  Bookmark,
  TrendingUp,
  TrendingDown,
  Minus,
  RefreshCw,
  ChevronUp,
  ChevronDown,
  ListChecks,
  Sparkles,
} from 'lucide-react';
import { cn } from '@/lib/utils';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type Toast = {
  id: string;
  message: string;
  type: 'success' | 'error';
};

type SortField =
  | 'symbol'
  | 'name'
  | 'price'
  | 'changePercent'
  | 'prediction'
  | 'confidence'
  | 'expectedReturn';

type SortDir = 'asc' | 'desc';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatPrice(v: any, currency = 'USD'): string {
  const n = Number(v);
  if (!Number.isFinite(n)) return '—';
  try {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency,
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(n);
  } catch {
    return `$${n.toFixed(2)}`;
  }
}

function formatPercent(v: any): string {
  const n = Number(v);
  if (!Number.isFinite(n)) return '—';
  const sign = n > 0 ? '+' : '';
  return `${sign}${n.toFixed(2)}%`;
}

function normalizePrediction(p: any) {
  if (!p) return null;
  const dir = (p.predicted_direction || p.direction || 'neutral').toLowerCase() as
    | 'up'
    | 'down'
    | 'neutral';
  const confidence = Number(p.confidence ?? 0);
  // expected_return may be decimal 0.015 => 1.5%
  let expectedReturn = Number(p.expected_return ?? p.expectedReturn ?? 0);
  if (Math.abs(expectedReturn) < 1 && Math.abs(expectedReturn) > 0) {
    // heuristic: if less than 1 in absolute and less than 0.5 maybe decimal
    // but predicted range is often small like 0.02 => 2% , convert
    // we keep check: if expectedReturn between -1 and 1 and not zero, multiply if *100 would be <30
    const cand = expectedReturn * 100;
    if (Math.abs(cand) < 30 && Math.abs(cand) > 0.05) expectedReturn = cand;
  }
  return { dir, confidence, expectedReturn, raw: p };
}

function predictionBadgeClass(dir: string) {
  if (dir === 'up') return 'bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-300';
  if (dir === 'down') return 'bg-red-50 text-red-700 ring-1 ring-red-200 dark:bg-red-950/40 dark:text-red-300';
  return 'bg-amber-50 text-amber-700 ring-1 ring-amber-200 dark:bg-amber-950/40 dark:text-amber-300';
}

function isUnauthorizedError(err: any) {
  const msg = String(err?.message || '').toLowerCase();
  return msg.includes('unauthorized') || msg.includes('401') || msg === 'unauthorized';
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function WatchlistPage() {
  const router = useRouter();

  // Watchlists list
  const [watchlists, setWatchlists] = useState<any[] | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [isLoadingWatchlists, setIsLoadingWatchlists] = useState(true);
  const [watchlistsError, setWatchlistsError] = useState<string | null>(null);

  // Detail
  const [detail, setDetail] = useState<any | null>(null);
  const [isLoadingDetail, setIsLoadingDetail] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  // Toasts
  const [toasts, setToasts] = useState<Toast[]>([]);

  // Create / rename / delete
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [newWatchlistName, setNewWatchlistName] = useState('');
  const [newWatchlistDesc, setNewWatchlistDesc] = useState('');
  const [isCreating, setIsCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const [editingId, setEditingId] = useState<string | null>(null);
  const [editName, setEditName] = useState('');
  const [isRenaming, setIsRenaming] = useState(false);
  const [renameError, setRenameError] = useState<string | null>(null);

  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);

  // Search / add
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<any[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [addingInstrumentKey, setAddingInstrumentKey] = useState<string | null>(null);
  const [removingKey, setRemovingKey] = useState<string | null>(null);

  // Sort & order
  const [sortField, setSortField] = useState<SortField>('symbol');
  const [sortDir, setSortDir] = useState<SortDir>('asc');
  const [isReordering, setIsReordering] = useState(false);

  // ---------------------------------------------------------------------------
  // Toast helpers
  // ---------------------------------------------------------------------------
  const pushToast = useCallback((message: string, type: Toast['type'] = 'success') => {
    const id = Math.random().toString(36).slice(2, 9);
    setToasts((prev) => [...prev, { id, message, type }]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 3500);
  }, []);

  const dismissToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  // ---------------------------------------------------------------------------
  // Fetch watchlists
  // ---------------------------------------------------------------------------
  const fetchWatchlists = useCallback(
    async (opts?: { silent?: boolean }) => {
      if (!opts?.silent) setIsLoadingWatchlists(true);
      setWatchlistsError(null);
      try {
        const lists = await getWatchlists();
        const normalized: any[] = Array.isArray(lists) ? lists : [];
        // If empty, create default watchlist
        if (normalized.length === 0) {
          try {
            const created = await createWatchlist({ name: 'My Watchlist', is_default: true });
            setWatchlists([created]);
            setSelectedId(String(created.id));
            pushToast('Default watchlist created', 'success');
            return;
          } catch (e: any) {
            // if creation fails due to race or auth, keep empty but surface error
            if (isUnauthorizedError(e)) {
              router.push('/login');
              return;
            }
            // still set empty to show empty UI
            setWatchlists([]);
            if (!opts?.silent) setWatchlistsError(e?.message || 'Failed to create default watchlist');
            return;
          }
        }
        setWatchlists(normalized);
        // auto-select default or first
        if (!selectedId || !normalized.some((w) => String(w.id) === selectedId)) {
          const def = normalized.find((w) => w.is_default) || normalized[0];
          if (def) setSelectedId(String(def.id));
        }
      } catch (err: any) {
        if (isUnauthorizedError(err)) {
          router.push('/login');
          return;
        }
        setWatchlistsError(err?.message || 'Failed to load watchlists');
        setWatchlists([]);
      } finally {
        setIsLoadingWatchlists(false);
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [pushToast, router, selectedId]
  );

  const fetchDetail = useCallback(
    async (watchlistId: string) => {
      if (!watchlistId) return;
      setIsLoadingDetail(true);
      setDetailError(null);
      try {
        const data = await getWatchlist(watchlistId);
        setDetail(data);
      } catch (err: any) {
        if (isUnauthorizedError(err)) {
          router.push('/login');
          return;
        }
        setDetailError(err?.message || 'Failed to load watchlist');
        setDetail(null);
      } finally {
        setIsLoadingDetail(false);
      }
    },
    [router]
  );

  useEffect(() => {
    fetchWatchlists();
  }, [fetchWatchlists]);

  useEffect(() => {
    if (selectedId) fetchDetail(selectedId);
    else setDetail(null);
  }, [selectedId, fetchDetail]);

  // ---------------------------------------------------------------------------
  // Watchlist CRUD
  // ---------------------------------------------------------------------------
  const handleCreate = async (e?: React.FormEvent) => {
    e?.preventDefault();
    const name = newWatchlistName.trim();
    if (!name) {
      setCreateError('Name is required');
      return;
    }
    if (name.length > 100) {
      setCreateError('Name must be ≤ 100 characters');
      return;
    }
    setIsCreating(true);
    setCreateError(null);
    try {
      const created = await createWatchlist({
        name,
        description: newWatchlistDesc.trim() || undefined,
        is_default: watchlists?.length === 0,
      });
      pushToast(`Watchlist "${created.name}" created`, 'success');
      setNewWatchlistName('');
      setNewWatchlistDesc('');
      setShowCreateDialog(false);
      await fetchWatchlists({ silent: true });
      // ensure selected
      setSelectedId(String(created.id));
    } catch (err: any) {
      if (isUnauthorizedError(err)) {
        router.push('/login');
        return;
      }
      const msg = err?.message || 'Failed to create watchlist';
      if (msg.toLowerCase().includes('already exists') || msg.includes('409')) {
        setCreateError('A watchlist with this name already exists');
      } else {
        setCreateError(msg);
      }
    } finally {
      setIsCreating(false);
    }
  };

  const startRename = (wl: any) => {
    setEditingId(String(wl.id));
    setEditName(wl.name);
    setRenameError(null);
  };

  const handleRename = async (e?: React.FormEvent) => {
    e?.preventDefault();
    if (!editingId) return;
    const name = editName.trim();
    if (!name) {
      setRenameError('Name is required');
      return;
    }
    setIsRenaming(true);
    setRenameError(null);
    try {
      await updateWatchlist(editingId, { name });
      pushToast('Watchlist renamed', 'success');
      setEditingId(null);
      await fetchWatchlists({ silent: true });
      if (selectedId === editingId) await fetchDetail(editingId);
    } catch (err: any) {
      if (isUnauthorizedError(err)) {
        router.push('/login');
        return;
      }
      const msg = err?.message || 'Failed to rename';
      if (msg.toLowerCase().includes('already exists') || msg.includes('409')) {
        setRenameError('A watchlist with this name already exists');
      } else {
        setRenameError(msg);
      }
    } finally {
      setIsRenaming(false);
    }
  };

  const handleDelete = async () => {
    if (!deleteConfirmId) return;
    setIsDeleting(true);
    try {
      await deleteWatchlist(deleteConfirmId);
      pushToast('Watchlist deleted', 'success');
      const remaining = (watchlists || []).filter((w) => String(w.id) !== deleteConfirmId);
      setDeleteConfirmId(null);
      if (selectedId === deleteConfirmId) {
        if (remaining.length > 0) {
          const next = remaining.find((w) => w.is_default) || remaining[0];
          setSelectedId(String(next.id));
        } else {
          setSelectedId(null);
          setDetail(null);
        }
      }
      await fetchWatchlists({ silent: true });
      // If no remaining, trigger default creation logic next fetch will create default
      if (remaining.length === 0) {
        // force refetch to create default
        await fetchWatchlists();
      }
    } catch (err: any) {
      if (isUnauthorizedError(err)) {
        router.push('/login');
        return;
      }
      pushToast(err?.message || 'Failed to delete watchlist', 'error');
    } finally {
      setIsDeleting(false);
    }
  };

  const handleSetDefault = async (watchlistId: string) => {
    try {
      await updateWatchlist(watchlistId, { is_default: true });
      pushToast('Default watchlist updated', 'success');
      await fetchWatchlists({ silent: true });
    } catch (err: any) {
      if (isUnauthorizedError(err)) {
        router.push('/login');
        return;
      }
      pushToast(err?.message || 'Failed to set default', 'error');
    }
  };

  // ---------------------------------------------------------------------------
  // Search
  // ---------------------------------------------------------------------------
  useEffect(() => {
    if (!searchQuery.trim()) {
      setSearchResults([]);
      setSearchError(null);
      return;
    }
    const query = searchQuery.trim();
    if (query.length < 1) return;
    const timer = setTimeout(async () => {
      setIsSearching(true);
      setSearchError(null);
      try {
        const results = await api.searchInstruments(query, { limit: 8 } as any);
        // normalize results: ensure array
        const arr = Array.isArray(results) ? results : [];
        setSearchResults(arr);
      } catch (err: any) {
        if (isUnauthorizedError(err)) {
          router.push('/login');
          return;
        }
        setSearchError(err?.message || 'Search failed');
        setSearchResults([]);
      } finally {
        setIsSearching(false);
      }
    }, 350);
    return () => clearTimeout(timer);
  }, [searchQuery, router]);

  const handleAdd = async (result: any) => {
    if (!selectedId) {
      pushToast('Select a watchlist first', 'error');
      return;
    }
    const symbol: string = result.symbol;
    const exchangeCode: string = result.exchange_code || result.exchange || 'NASDAQ';
    const key = `${symbol}-${exchangeCode}`;
    setAddingInstrumentKey(key);
    try {
      // Need instrument_id - fetch instrument to get UUID
      let instrumentId: string | null = (result as any).id || null;
      // If search result has id, use it; else fetch
      if (!instrumentId) {
        try {
          const inst = await api.getInstrument(symbol, exchangeCode);
          instrumentId = String((inst as any).id || (inst as any).instrument_id || '');
          if (!instrumentId) throw new Error('Instrument not found');
        } catch (e: any) {
          // try fallback: search alternative exchange
          // If exchange missing, try NSE then NASDAQ
          if (!instrumentId) {
            throw e;
          }
        }
      }
      if (!instrumentId) throw new Error('Unable to resolve instrument');
      await addToWatchlist(selectedId, instrumentId);
      pushToast(`${symbol} added to watchlist`, 'success');
      setSearchQuery('');
      setSearchResults([]);
      await fetchDetail(selectedId);
      await fetchWatchlists({ silent: true });
    } catch (err: any) {
      if (isUnauthorizedError(err)) {
        router.push('/login');
        return;
      }
      const msg = String(err?.message || 'Failed to add stock');
      if (msg.toLowerCase().includes('already')) {
        pushToast(`${symbol} is already in watchlist`, 'error');
      } else {
        pushToast(msg, 'error');
      }
    } finally {
      setAddingInstrumentKey(null);
    }
  };

  const handleRemove = async (instrumentId: string, symbol: string) => {
    if (!selectedId) return;
    const key = String(instrumentId);
    setRemovingKey(key);
    try {
      await removeFromWatchlist(selectedId, instrumentId);
      pushToast(`${symbol} removed`, 'success');
      await fetchDetail(selectedId);
      await fetchWatchlists({ silent: true });
    } catch (err: any) {
      if (isUnauthorizedError(err)) {
        router.push('/login');
        return;
      }
      pushToast(err?.message || 'Failed to remove', 'error');
    } finally {
      setRemovingKey(null);
    }
  };

  // ---------------------------------------------------------------------------
  // Sorting & reordering
  // ---------------------------------------------------------------------------
  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDir((prev) => (prev === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortField(field);
      setSortDir('asc');
    }
  };

  const handleMove = async (index: number, direction: 'up' | 'down') => {
    if (!detail?.items || !selectedId) return;
    const items = [...detail.items];
    const newIndex = direction === 'up' ? index - 1 : index + 1;
    if (newIndex < 0 || newIndex >= items.length) return;
    // swap
    const temp = items[index];
    items[index] = items[newIndex];
    items[newIndex] = temp;
    // optimistic update
    setDetail({ ...detail, items });
    setIsReordering(true);
    try {
      const orderedIds = items.map((it: any) => String(it.id || it.instrument_id));
      await reorderWatchlist(selectedId, orderedIds);
      pushToast('Watchlist order updated', 'success');
    } catch (err: any) {
      if (isUnauthorizedError(err)) {
        router.push('/login');
        return;
      }
      pushToast(err?.message || 'Failed to reorder', 'error');
      // revert
      await fetchDetail(selectedId);
    } finally {
      setIsReordering(false);
    }
  };

  // client-side sorted items
  const sortedItems = useMemo(() => {
    if (!detail?.items) return [];
    const items = [...detail.items] as any[];
    const dir = sortDir === 'asc' ? 1 : -1;
    const getVal = (it: any, field: SortField) => {
      switch (field) {
        case 'symbol':
          return (it.instrument?.symbol || '').toString().toLowerCase();
        case 'name':
          return (it.instrument?.name || '').toString().toLowerCase();
        case 'price':
          return Number(it.quote?.price ?? it.instrument?.price ?? 0);
        case 'changePercent':
          return Number(it.quote?.change_percent ?? it.quote?.changePercent ?? 0);
        case 'prediction': {
          const p = normalizePrediction(it.prediction);
          if (!p) return '';
          // order: up > neutral > down alphabetically but map to numeric
          const order = p.dir === 'up' ? 2 : p.dir === 'neutral' ? 1 : 0;
          return order;
        }
        case 'confidence': {
          const p = normalizePrediction(it.prediction);
          return p ? Number(p.confidence) : -1;
        }
        case 'expectedReturn': {
          const p = normalizePrediction(it.prediction);
          return p ? Number(p.expectedReturn) : -9999;
        }
        default:
          return '';
      }
    };
    items.sort((a, b) => {
      const av = getVal(a, sortField);
      const bv = getVal(b, sortField);
      if (typeof av === 'string' && typeof bv === 'string') {
        return av.localeCompare(bv) * dir;
      }
      const an = Number(av);
      const bn = Number(bv);
      if (Number.isNaN(an) || Number.isNaN(bn)) return 0;
      return (an - bn) * dir;
    });
    return items;
  }, [detail, sortField, sortDir]);

  // ---------------------------------------------------------------------------
  // Derived stats for sidebar
  // ---------------------------------------------------------------------------
  const selectedWatchlistMeta = useMemo(() => {
    if (!watchlists || !selectedId) return null;
    return watchlists.find((w) => String(w.id) === selectedId) || null;
  }, [watchlists, selectedId]);

  // ---------------------------------------------------------------------------
  // Render helpers
  // ---------------------------------------------------------------------------
  const SortIcon = ({ field }: { field: SortField }) => {
    if (sortField !== field) return <ArrowUpDown className="h-3.5 w-3.5 text-slate-400" />;
    return sortDir === 'asc' ? (
      <ArrowUp className="h-3.5 w-3.5 text-primary" />
    ) : (
      <ArrowDown className="h-3.5 w-3.5 text-primary" />
    );
  };

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------
  return (
    <div className="min-h-screen bg-slate-50/50 dark:bg-slate-950">
      {/* Toasts */}
      <div className="pointer-events-none fixed bottom-4 right-4 z-[100] flex flex-col gap-2">
        {toasts.map((t) => (
          <div
            key={t.id}
            className={cn(
              'pointer-events-auto flex min-w-[320px] max-w-[420px] items-start gap-3 rounded-lg border px-4 py-3 shadow-lg backdrop-blur supports-[backdrop-filter]:bg-white/90',
              t.type === 'success'
                ? 'border-emerald-200 bg-white text-slate-900 dark:border-emerald-900/30 dark:bg-slate-900 dark:text-slate-100'
                : 'border-red-200 bg-white text-slate-900 dark:border-red-900/30 dark:bg-slate-900 dark:text-slate-100'
            )}
          >
            <div
              className={cn(
                'mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full',
                t.type === 'success'
                  ? 'bg-emerald-100 text-emerald-600 dark:bg-emerald-950/50 dark:text-emerald-300'
                  : 'bg-red-100 text-red-600 dark:bg-red-950/50 dark:text-red-300'
              )}
            >
              {t.type === 'success' ? <CheckCircle2 className="h-4 w-4" /> : <AlertCircle className="h-4 w-4" />}
            </div>
            <p className="flex-1 text-sm font-medium leading-5">{t.message}</p>
            <button
              onClick={() => dismissToast(t.id)}
              className="shrink-0 rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600 dark:hover:bg-slate-800"
              aria-label="Dismiss"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        ))}
      </div>

      {/* Delete confirmation dialog */}
      <Dialog open={!!deleteConfirmId} onOpenChange={(open) => !open && setDeleteConfirmId(null)}>
        <DialogContent className="sm:max-w-[420px]">
          <DialogHeader>
            <DialogTitle>Delete watchlist</DialogTitle>
            <DialogDescription>
              Are you sure you want to delete this watchlist? This action cannot be undone. Stocks in the watchlist
              will not be deleted, only the watchlist itself.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteConfirmId(null)} disabled={isDeleting}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={handleDelete} disabled={isDeleting}>
              {isDeleting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Rename dialog */}
      <Dialog open={!!editingId} onOpenChange={(open) => !open && setEditingId(null)}>
        <DialogContent className="sm:max-w-[420px]">
          <DialogHeader>
            <DialogTitle>Rename watchlist</DialogTitle>
            <DialogDescription>Enter a new name for your watchlist.</DialogDescription>
          </DialogHeader>
          <form onSubmit={handleRename} className="space-y-4">
            <div className="space-y-2">
              <Input
                value={editName}
                onChange={(e) => setEditName(e.target.value)}
                placeholder="Watchlist name"
                maxLength={100}
                autoFocus
                disabled={isRenaming}
              />
              {renameError && <p className="text-sm text-red-600 dark:text-red-400">{renameError}</p>}
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setEditingId(null)} disabled={isRenaming}>
                Cancel
              </Button>
              <Button type="submit" disabled={isRenaming}>
                {isRenaming ? <Loader2 className="h-4 w-4 animate-spin" /> : <Pencil className="h-4 w-4" />}
                Save
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <div className="mx-auto max-w-[1400px] px-4 py-6 sm:px-6 lg:px-8">
        {/* Header */}
        <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div className="space-y-1.5">
            <div className="flex items-center gap-3">
              <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-slate-900 text-white dark:bg-white dark:text-slate-900">
                <Star className="h-5 w-5" />
              </div>
              <div>
                <h1 className="text-2xl font-semibold tracking-tight text-slate-900 dark:text-white">Watchlist</h1>
                <p className="text-sm text-muted-foreground">
                  Track your favorite stocks with AI-powered predictions and real-time prices
                </p>
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => fetchWatchlists()}
              disabled={isLoadingWatchlists || isLoadingDetail}
              className="bg-white dark:bg-slate-900"
            >
              <RefreshCw className={cn('h-4 w-4', (isLoadingWatchlists || isLoadingDetail) && 'animate-spin')} />
              Refresh
            </Button>
            <Button size="sm" className="gap-1.5" onClick={() => setShowCreateDialog(true)}>
              <Plus className="h-4 w-4" />
              New watchlist
            </Button>
            <Dialog open={showCreateDialog} onOpenChange={setShowCreateDialog}>
              <DialogContent className="sm:max-w-[480px]">
                <DialogHeader>
                  <DialogTitle>Create watchlist</DialogTitle>
                  <DialogDescription>
                    Create a new watchlist to organize your tracked stocks. You can set it as default later.
                  </DialogDescription>
                </DialogHeader>
                <form onSubmit={handleCreate} className="space-y-4">
                  <div className="space-y-2">
                    <label htmlFor="wl-name" className="text-sm font-medium">
                      Name *
                    </label>
                    <Input
                      id="wl-name"
                      value={newWatchlistName}
                      onChange={(e) => setNewWatchlistName(e.target.value)}
                      placeholder="e.g. Tech Leaders"
                      maxLength={100}
                      disabled={isCreating}
                      required
                    />
                  </div>
                  <div className="space-y-2">
                    <label htmlFor="wl-desc" className="text-sm font-medium">
                      Description <span className="font-normal text-muted-foreground">(optional)</span>
                    </label>
                    <Input
                      id="wl-desc"
                      value={newWatchlistDesc}
                      onChange={(e) => setNewWatchlistDesc(e.target.value)}
                      placeholder="Brief description"
                      maxLength={500}
                      disabled={isCreating}
                    />
                  </div>
                  {createError && (
                    <Alert variant="destructive" className="py-2">
                      <AlertCircle className="h-4 w-4" />
                      <AlertDescription className="text-sm">{createError}</AlertDescription>
                    </Alert>
                  )}
                  <DialogFooter>
                    <Button type="button" variant="outline" onClick={() => setShowCreateDialog(false)} disabled={isCreating}>
                      Cancel
                    </Button>
                    <Button type="submit" disabled={isCreating}>
                      {isCreating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
                      Create
                    </Button>
                  </DialogFooter>
                </form>
              </DialogContent>
            </Dialog>
          </div>
        </div>

        {/* Global error */}
        {watchlistsError && (
          <Alert variant="destructive" className="mt-6">
            <AlertCircle className="h-4 w-4" />
            <AlertTitle>Failed to load watchlists</AlertTitle>
            <AlertDescription className="flex flex-wrap items-center gap-3">
              <span>{watchlistsError}</span>
              <Button variant="outline" size="sm" onClick={() => fetchWatchlists()} className="h-7 bg-white">
                <RefreshCw className="h-3.5 w-3.5" />
                Retry
              </Button>
            </AlertDescription>
          </Alert>
        )}

        <div className="mt-6 grid gap-6 lg:grid-cols-[320px_1fr]">
          {/* Sidebar: watchlists list */}
          <div className="space-y-4">
            <Card className="border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                  <CardTitle className="flex items-center gap-2 text-[13px] font-semibold uppercase tracking-widest">
                    <ListChecks className="h-4 w-4 text-slate-500" />
                    My watchlists
                  </CardTitle>
                  <Badge variant="secondary" className="rounded-full bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300">
                    {watchlists?.length ?? 0}
                  </Badge>
                </div>
                <CardDescription className="text-xs">Select a watchlist to view its stocks</CardDescription>
              </CardHeader>
              <CardContent className="space-y-2">
                {isLoadingWatchlists ? (
                  <div className="space-y-3">
                    {Array.from({ length: 3 }).map((_, i) => (
                      <div key={i} className="flex items-center gap-3 rounded-lg border border-slate-100 p-3 dark:border-slate-800">
                        <Skeleton className="h-9 w-9 rounded-md" />
                        <div className="flex-1 space-y-2">
                          <Skeleton className="h-4 w-28" />
                          <Skeleton className="h-3 w-20" />
                        </div>
                        <Skeleton className="h-6 w-8 rounded-full" />
                      </div>
                    ))}
                  </div>
                ) : !watchlists || watchlists.length === 0 ? (
                  <div className="rounded-lg border border-dashed border-slate-200 bg-slate-50/60 p-6 text-center dark:border-slate-800 dark:bg-slate-800/30">
                    <div className="mx-auto flex h-10 w-10 items-center justify-center rounded-full bg-white dark:bg-slate-900">
                      <Bookmark className="h-5 w-5 text-slate-400" />
                    </div>
                    <p className="mt-3 text-sm font-medium text-slate-900 dark:text-white">No watchlists yet</p>
                    <p className="mt-1 text-xs leading-5 text-muted-foreground">
                      Create your first watchlist to start tracking stocks.
                    </p>
                    <Button size="sm" className="mt-4" onClick={() => setShowCreateDialog(true)}>
                      <Plus className="h-4 w-4" />
                      Create watchlist
                    </Button>
                  </div>
                ) : (
                  <div className="space-y-2">
                    {watchlists.map((wl) => {
                      const isSelected = String(wl.id) === selectedId;
                      return (
                        <div
                          key={String(wl.id)}
                          className={cn(
                            'group relative flex items-center gap-3 rounded-lg border p-3 transition-colors',
                            isSelected
                              ? 'border-primary/30 bg-primary/5 dark:border-primary/20 dark:bg-primary/10'
                              : 'border-slate-200 bg-white hover:bg-slate-50 dark:border-slate-800 dark:bg-slate-900 dark:hover:bg-slate-800/60'
                          )}
                        >
                          <button
                            onClick={() => setSelectedId(String(wl.id))}
                            className="flex flex-1 items-center gap-3 text-left"
                          >
                            <div
                              className={cn(
                                'flex h-9 w-9 shrink-0 items-center justify-center rounded-md border text-slate-600 dark:text-slate-300',
                                isSelected
                                  ? 'border-primary/20 bg-white text-primary dark:bg-slate-900'
                                  : 'border-slate-200 bg-slate-50 dark:border-slate-800 dark:bg-slate-800'
                              )}
                            >
                              {wl.is_default ? <Star className="h-4 w-4 fill-amber-400 text-amber-500" /> : <Bookmark className="h-4 w-4" />}
                            </div>
                            <div className="min-w-0 flex-1">
                              <div className="flex items-center gap-2">
                                <span className="truncate text-sm font-semibold text-slate-900 dark:text-white">{wl.name}</span>
                                {wl.is_default && (
                                  <Badge className="hidden h-5 rounded-full bg-amber-100 px-1.5 text-[10px] font-bold tracking-wide text-amber-700 ring-1 ring-amber-200 dark:bg-amber-950/40 dark:text-amber-300 sm:inline-flex">
                                    DEFAULT
                                  </Badge>
                                )}
                              </div>
                              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                                <span>{wl.item_count ?? detail?.items?.length ?? 0} stocks</span>
                                {wl.description && (
                                  <>
                                    <span className="h-1 w-1 rounded-full bg-slate-300 dark:bg-slate-600" />
                                    <span className="truncate max-w-[120px]">{wl.description}</span>
                                  </>
                                )}
                              </div>
                            </div>
                          </button>
                          <div className="flex shrink-0 items-center gap-1">
                            <Button
                              variant="ghost"
                              size="icon-sm"
                              className="h-7 w-7"
                              onClick={() => startRename(wl)}
                              aria-label="Rename"
                              title="Rename"
                            >
                              <Pencil className="h-4 w-4" />
                            </Button>
                            {!wl.is_default && (
                              <Button
                                variant="ghost"
                                size="icon-sm"
                                className="h-7 w-7"
                                onClick={() => handleSetDefault(String(wl.id))}
                                aria-label="Set as default"
                                title="Set as default"
                              >
                                <Star className="h-4 w-4" />
                              </Button>
                            )}
                            <Button
                              variant="ghost"
                              size="icon-sm"
                              className="h-7 w-7 text-slate-400 hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-950/30"
                              onClick={() => setDeleteConfirmId(String(wl.id))}
                              aria-label="Delete"
                              title="Delete"
                            >
                              <Trash2 className="h-4 w-4" />
                            </Button>
                          </div>
                          {isSelected && <div className="absolute inset-y-2 left-0 w-0.5 rounded-full bg-primary" />}
                        </div>
                      );
                    })}
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Info card */}
            <Card className="border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
              <CardContent className="p-4">
                <div className="flex gap-3">
                  <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-violet-100 text-violet-600 dark:bg-violet-950/40 dark:text-violet-300">
                    <Sparkles className="h-4 w-4" />
                  </div>
                  <div className="space-y-1">
                    <p className="text-sm font-medium text-slate-900 dark:text-white">Pro tip</p>
                    <p className="text-xs leading-5 text-muted-foreground">
                      Add stocks via search, then sort by prediction or drag to reorder your watchlist.
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Main panel */}
          <div className="space-y-4">
            {/* Selected watchlist header + search */}
            <Card className="overflow-hidden border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
              <CardHeader className="pb-4">
                {isLoadingWatchlists || isLoadingDetail ? (
                  <div className="space-y-3">
                    <Skeleton className="h-6 w-40" />
                    <Skeleton className="h-4 w-64" />
                    <Skeleton className="h-10 w-full" />
                  </div>
                ) : !selectedId || !selectedWatchlistMeta ? (
                  <div className="flex flex-col items-center justify-center py-6 text-center">
                    <div className="flex h-12 w-12 items-center justify-center rounded-full bg-slate-100 dark:bg-slate-800">
                      <Star className="h-6 w-6 text-slate-400" />
                    </div>
                    <p className="mt-3 text-sm font-medium text-slate-900 dark:text-white">Select a watchlist</p>
                    <p className="text-xs text-muted-foreground">Choose a watchlist from the left to view and manage stocks.</p>
                  </div>
                ) : (
                  <>
                    <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <CardTitle className="truncate text-lg tracking-tight">
                            {selectedWatchlistMeta.name}
                          </CardTitle>
                          {selectedWatchlistMeta.is_default && (
                            <Badge className="rounded-full bg-amber-100 text-amber-700 ring-1 ring-amber-200 dark:bg-amber-950/30 dark:text-amber-300">
                              <Star className="h-3 w-3 fill-amber-500 text-amber-500" />
                              Default
                            </Badge>
                          )}
                          <Badge variant="outline" className="rounded-full font-mono text-xs">
                            {detail?.items?.length ?? selectedWatchlistMeta.item_count ?? 0} items
                          </Badge>
                        </div>
                        {selectedWatchlistMeta.description && (
                          <CardDescription className="mt-1 max-w-[560px] text-xs leading-5">
                            {selectedWatchlistMeta.description}
                          </CardDescription>
                        )}
                        <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                          <span className="inline-flex items-center gap-1.5">
                            <ListChecks className="h-3 w-3" />
                            Sort via column headers or reorder with up/down
                          </span>
                          {isReordering && (
                            <span className="inline-flex items-center gap-1 text-amber-600 dark:text-amber-400">
                              <Loader2 className="h-3 w-3 animate-spin" />
                              Saving order…
                            </span>
                          )}
                        </div>
                      </div>
                      <div className="flex shrink-0 items-center gap-2">
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => selectedId && fetchDetail(selectedId)}
                          disabled={isLoadingDetail}
                          className="bg-white dark:bg-slate-900"
                        >
                          <RefreshCw className={cn('h-4 w-4', isLoadingDetail && 'animate-spin')} />
                          Reload
                        </Button>
                      </div>
                    </div>

                    {/* Search to add */}
                    <div className="relative mt-4">
                      <div className="relative">
                        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                        <Input
                          placeholder="Search for a stock to add (e.g. AAPL, RELIANCE, TCS)"
                          value={searchQuery}
                          onChange={(e) => setSearchQuery(e.target.value)}
                          className="pl-10 pr-10"
                        />
                        {searchQuery && (
                          <button
                            onClick={() => {
                              setSearchQuery('');
                              setSearchResults([]);
                            }}
                            className="absolute right-3 top-1/2 -translate-y-1/2 rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600 dark:hover:bg-slate-800"
                            aria-label="Clear"
                          >
                            <X className="h-4 w-4" />
                          </button>
                        )}
                        {isSearching && (
                          <Loader2 className="absolute right-10 top-1/2 h-4 w-4 -translate-y-1/2 animate-spin text-slate-400" />
                        )}
                      </div>
                      {searchError && (
                        <Alert variant="destructive" className="mt-3 py-2">
                          <AlertCircle className="h-4 w-4" />
                          <AlertDescription className="text-xs">{searchError}</AlertDescription>
                        </Alert>
                      )}
                      {searchResults.length > 0 && (
                        <Card className="absolute left-0 right-0 top-full z-20 mt-2 max-h-[320px] overflow-hidden border-slate-200 shadow-lg dark:border-slate-800">
                          <CardContent className="p-0">
                            <div className="max-h-[320px] overflow-auto">
                              {searchResults.map((r) => {
                                const key = `${r.symbol}-${r.exchange_code || r.exchange}`;
                                const isAdding = addingInstrumentKey === key;
                                return (
                                  <div
                                    key={key}
                                    className="flex items-center justify-between gap-3 border-b border-slate-100 px-3 py-2.5 last:border-0 hover:bg-slate-50 dark:border-slate-800 dark:hover:bg-slate-800/50"
                                  >
                                    <div className="min-w-0 flex-1">
                                      <div className="flex items-center gap-2">
                                        <span className="font-mono text-sm font-semibold tracking-wide">{r.symbol}</span>
                                        <Badge variant="outline" className="h-5 rounded-md px-1.5 text-[11px]">
                                          {r.exchange_code || r.exchange}
                                        </Badge>
                                        <Badge variant="secondary" className="hidden h-5 rounded-full text-[11px] sm:inline-flex">
                                          {r.market}
                                        </Badge>
                                      </div>
                                      <p className="truncate text-xs text-muted-foreground">{r.name}</p>
                                      <p className="text-[11px] text-muted-foreground">{r.type} • {r.currency}</p>
                                    </div>
                                    <Button
                                      size="sm"
                                      onClick={() => handleAdd(r)}
                                      disabled={isAdding}
                                      className="shrink-0 gap-1"
                                    >
                                      {isAdding ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
                                      Add
                                    </Button>
                                  </div>
                                );
                              })}
                            </div>
                          </CardContent>
                        </Card>
                      )}
                      {searchQuery.trim() && !isSearching && searchResults.length === 0 && !searchError && (
                        <p className="mt-2 text-xs text-muted-foreground">No results for &quot;{searchQuery}&quot;. Try a symbol like AAPL or NSE:TCS.</p>
                      )}
                    </div>
                  </>
                )}
              </CardHeader>

              {/* Table/content */}
              <CardContent className="p-0">
                {isLoadingDetail ? (
                  <div className="space-y-3 p-4 sm:p-6">
                    <div className="flex gap-2">
                      <Skeleton className="h-8 w-full" />
                    </div>
                    {Array.from({ length: 4 }).map((_, i) => (
                      <Skeleton key={i} className="h-14 w-full" />
                    ))}
                  </div>
                ) : detailError ? (
                  <div className="p-4 sm:p-6">
                    <Alert variant="destructive">
                      <AlertCircle className="h-4 w-4" />
                      <AlertTitle>Failed to load watchlist</AlertTitle>
                      <AlertDescription className="flex flex-wrap items-center gap-3">
                        <span>{detailError}</span>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => selectedId && fetchDetail(selectedId)}
                          className="h-7 bg-white"
                        >
                          <RefreshCw className="h-3.5 w-3.5" />
                          Retry
                        </Button>
                      </AlertDescription>
                    </Alert>
                  </div>
                ) : !detail || !selectedId ? (
                  <div className="flex flex-col items-center justify-center px-4 py-12 text-center sm:px-6">
                    <div className="flex h-12 w-12 items-center justify-center rounded-full bg-slate-100 dark:bg-slate-800">
                      <Search className="h-6 w-6 text-slate-400" />
                    </div>
                    <p className="mt-4 text-sm font-medium text-slate-900 dark:text-white">No watchlist selected</p>
                    <p className="mt-1 max-w-sm text-sm leading-5 text-muted-foreground">
                      Select an existing watchlist or create a new one to start tracking stocks.
                    </p>
                  </div>
                ) : sortedItems.length === 0 ? (
                  <div className="flex flex-col items-center justify-center px-4 py-12 text-center sm:px-6">
                    <div className="flex h-12 w-12 items-center justify-center rounded-full bg-slate-100 dark:bg-slate-800">
                      <StarOff className="h-6 w-6 text-slate-400" />
                    </div>
                    <p className="mt-4 text-sm font-medium text-slate-900 dark:text-white">Your watchlist is empty. Search for a stock to start tracking it.</p>
                    <p className="mt-1 max-w-sm text-xs leading-5 text-muted-foreground">
                      Use the search field above to find stocks by symbol or company name, then click Add to track them here. Your
                      watchlist is sortable and persisted per account.
                    </p>
                    <div className="mt-4 flex flex-wrap items-center justify-center gap-2 text-xs text-muted-foreground">
                      <span className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-white px-2.5 py-1 dark:border-slate-800 dark:bg-slate-900">
                        <Search className="h-3 w-3" />
                        Search symbol
                      </span>
                      <span className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-white px-2.5 py-1 dark:border-slate-800 dark:bg-slate-900">
                        <Plus className="h-3 w-3" />
                        Add to watchlist
                      </span>
                      <span className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-white px-2.5 py-1 dark:border-slate-800 dark:bg-slate-900">
                        <ArrowUpDown className="h-3 w-3" />
                        Sort columns
                      </span>
                    </div>
                  </div>
                ) : (
                  <div className="overflow-x-auto">
                    <Table>
                      <TableHeader className="bg-slate-50/70 dark:bg-slate-800/50">
                        <TableRow className="hover:bg-transparent">
                          <TableHead className="w-10 text-center">
                            <GripVertical className="mx-auto h-4 w-4 text-slate-400" />
                          </TableHead>
                          <TableHead>
                            <button
                              onClick={() => handleSort('symbol')}
                              className="inline-flex items-center gap-1.5 font-semibold hover:text-slate-900 dark:hover:text-white"
                            >
                              Symbol <SortIcon field="symbol" />
                            </button>
                          </TableHead>
                          <TableHead>
                            <button
                              onClick={() => handleSort('name')}
                              className="inline-flex items-center gap-1.5 font-semibold hover:text-slate-900"
                            >
                              Name <SortIcon field="name" />
                            </button>
                          </TableHead>
                          <TableHead className="text-right">
                            <button
                              onClick={() => handleSort('price')}
                              className="inline-flex items-center gap-1.5 font-semibold hover:text-slate-900"
                            >
                              Price <SortIcon field="price" />
                            </button>
                          </TableHead>
                          <TableHead className="text-right">
                            <button
                              onClick={() => handleSort('changePercent')}
                              className="inline-flex items-center gap-1.5 font-semibold hover:text-slate-900"
                            >
                              Daily change <SortIcon field="changePercent" />
                            </button>
                          </TableHead>
                          <TableHead>
                            <button
                              onClick={() => handleSort('prediction')}
                              className="inline-flex items-center gap-1.5 font-semibold hover:text-slate-900"
                            >
                              Prediction <SortIcon field="prediction" />
                            </button>
                          </TableHead>
                          <TableHead className="text-right">
                            <button
                              onClick={() => handleSort('confidence')}
                              className="inline-flex items-center gap-1.5 font-semibold hover:text-slate-900"
                            >
                              Confidence <SortIcon field="confidence" />
                            </button>
                          </TableHead>
                          <TableHead className="text-right">
                            <button
                              onClick={() => handleSort('expectedReturn')}
                              className="inline-flex items-center gap-1.5 font-semibold hover:text-slate-900"
                            >
                              Expected return <SortIcon field="expectedReturn" />
                            </button>
                          </TableHead>
                          <TableHead className="w-24 text-center">Reorder</TableHead>
                          <TableHead className="w-12 text-center">Remove</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {sortedItems.map((item: any, idx: number) => {
                          const instrument = item.instrument || {};
                          const quote = item.quote || {};
                          const predRaw = item.prediction;
                          const pred = normalizePrediction(predRaw);
                          const symbol: string = instrument.symbol || item.symbol || '—';
                          const name: string = instrument.name || item.name || '—';
                          const exchangeCode: string = instrument.exchange?.code || instrument.exchange_code || quote.exchange || '';
                          const price = quote.price ?? quote.close ?? instrument.price;
                          const change = quote.change ?? 0;
                          const changePercent = quote.change_percent ?? quote.changePercent ?? 0;
                          const currency = quote.currency || instrument.currency || 'USD';
                          const isPositive = Number(changePercent) >= 0;
                          const isNeg = Number(changePercent) < 0;
                          const removing = String(item.instrument_id) === removingKey || String(item.instrument?.id) === removingKey;

                          // Find original index for reorder (client sorted order may differ from persisted order)
                          // We use detail.items index to determine move target
                          const originalIndex = detail.items.findIndex(
                            (orig: any) => String(orig.id) === String(item.id)
                          );

                          return (
                            <TableRow key={String(item.id || item.instrument_id || symbol)} className="group">
                              <TableCell className="text-center">
                                <div className="flex justify-center">
                                  <GripVertical className="h-4 w-4 text-slate-300 group-hover:text-slate-500" />
                                </div>
                              </TableCell>
                              <TableCell className="py-3">
                                <div className="flex flex-col">
                                  <span className="font-mono text-sm font-semibold tracking-wide text-slate-900 dark:text-white">
                                    {symbol}
                                  </span>
                                  <span className="text-[11px] font-medium text-muted-foreground">{exchangeCode}</span>
                                </div>
                              </TableCell>
                              <TableCell className="py-3">
                                <div className="max-w-[180px] truncate text-sm font-medium text-slate-700 dark:text-slate-300" title={name}>
                                  {name}
                                </div>
                                {instrument.sector && (
                                  <div className="text-[11px] text-muted-foreground">{instrument.sector}</div>
                                )}
                              </TableCell>
                              <TableCell className="py-3 text-right font-mono text-sm tabular-nums">
                                {price !== undefined && price !== null && String(price) !== '' ? formatPrice(price, currency) : <span className="text-muted-foreground">—</span>}
                              </TableCell>
                              <TableCell className="py-3 text-right">
                                <span
                                  className={cn(
                                    'inline-flex items-center justify-end gap-1 rounded-full px-2 py-0.5 text-xs font-semibold tabular-nums ring-1',
                                    Number(changePercent) > 0
                                      ? 'bg-emerald-50 text-emerald-700 ring-emerald-200 dark:bg-emerald-950/30 dark:text-emerald-300 dark:ring-emerald-900'
                                      : Number(changePercent) < 0
                                        ? 'bg-red-50 text-red-700 ring-red-200 dark:bg-red-950/30 dark:text-red-300 dark:ring-red-900'
                                        : 'bg-slate-50 text-slate-600 ring-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:ring-slate-700'
                                  )}
                                >
                                  {isPositive && Number(changePercent) !== 0 ? (
                                    <TrendingUp className="h-3 w-3" />
                                  ) : isNeg ? (
                                    <TrendingDown className="h-3 w-3" />
                                  ) : (
                                    <Minus className="h-3 w-3" />
                                  )}
                                  {formatPercent(changePercent)}{' '}
                                  <span className="hidden text-[11px] font-normal opacity-70 xl:inline">({Number(change) >= 0 ? '+' : ''}{Number(change).toFixed(2)})</span>
                                </span>
                              </TableCell>
                              <TableCell className="py-3">
                                {pred ? (
                                  <Badge className={cn('gap-1 rounded-full border px-2 py-0.5 text-xs font-semibold capitalize', predictionBadgeClass(pred.dir))}>
                                    {pred.dir === 'up' ? <TrendingUp className="h-3 w-3" /> : pred.dir === 'down' ? <TrendingDown className="h-3 w-3" /> : <Minus className="h-3 w-3" />}
                                    {pred.dir}
                                  </Badge>
                                ) : (
                                  <Badge variant="outline" className="rounded-full text-xs font-normal text-muted-foreground">
                                    —
                                  </Badge>
                                )}
                              </TableCell>
                              <TableCell className="py-3 text-right font-mono text-sm tabular-nums">
                                {pred ? (
                                  <span className={cn(pred.confidence >= 70 ? 'text-emerald-600 dark:text-emerald-400' : pred.confidence >= 50 ? 'text-amber-600 dark:text-amber-400' : 'text-slate-500')}>
                                    {pred.confidence}
                                  </span>
                                ) : (
                                  <span className="text-muted-foreground">—</span>
                                )}
                              </TableCell>
                              <TableCell className="py-3 text-right font-mono text-sm tabular-nums">
                                {pred ? (
                                  <span className={cn(pred.expectedReturn >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-600 dark:text-red-400')}>
                                    {pred.expectedReturn >= 0 ? '+' : ''}
                                    {pred.expectedReturn.toFixed(2)}%
                                  </span>
                                ) : (
                                  <span className="text-muted-foreground">—</span>
                                )}
                              </TableCell>
                              <TableCell className="py-3 text-center">
                                <div className="flex items-center justify-center gap-1">
                                  <Button
                                    variant="ghost"
                                    size="icon-sm"
                                    className="h-7 w-7"
                                    disabled={originalIndex <= 0 || isReordering}
                                    onClick={() => handleMove(originalIndex, 'up')}
                                    aria-label="Move up"
                                  >
                                    <ChevronUp className="h-4 w-4" />
                                  </Button>
                                  <Button
                                    variant="ghost"
                                    size="icon-sm"
                                    className="h-7 w-7"
                                    disabled={originalIndex >= detail.items.length - 1 || isReordering}
                                    onClick={() => handleMove(originalIndex, 'down')}
                                    aria-label="Move down"
                                  >
                                    <ChevronDown className="h-4 w-4" />
                                  </Button>
                                </div>
                              </TableCell>
                              <TableCell className="py-3 text-center">
                                <Button
                                  variant="ghost"
                                  size="icon-sm"
                                  className="h-7 w-7 text-slate-400 hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-950/30 dark:hover:text-red-400"
                                  onClick={() => handleRemove(String(instrument.id || item.instrument_id), symbol)}
                                  disabled={removing}
                                  aria-label={`Remove ${symbol}`}
                                >
                                  {removing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
                                </Button>
                              </TableCell>
                            </TableRow>
                          );
                        })}
                      </TableBody>
                    </Table>
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Footer note when has items */}
            {detail?.items?.length > 0 && (
              <p className="px-1 text-xs leading-5 text-muted-foreground">
                Prices and predictions are refreshed from the backend. Click column headers to sort; use up/down to persist custom order. Remove with the trash icon. All changes are saved to your watchlist.
              </p>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
