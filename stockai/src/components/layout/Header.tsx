'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useTheme } from 'next-themes';
import { cn } from '@/lib/utils';
import { api } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Sheet, SheetContent, SheetTrigger } from '@/components/ui/sheet';
import {
  Search,
  Menu,
  X,
  Sun,
  Moon,
  LogOut,
  User,
  BarChart2,
  BookOpen,
  FlaskConical,
  List,
  Globe,
  Zap,
  UserPlus,
  LogIn,
  Bell,
  Cpu,
  Target,
  LineChart,
  Trophy,
} from 'lucide-react';
import { CommandPalette, useCommandPalette } from '@/components/command-palette';

const navigation = [
  { name: 'Dashboard', href: '/dashboard', icon: BarChart2 },
  { name: 'Markets', href: '/markets', icon: Globe },
  { name: 'Predictions', href: '/predictions', icon: Zap },
  { name: 'Rankings', href: '/rankings', icon: Trophy },
  { name: 'Screener', href: '/screener', icon: Search },
  { name: 'Watchlist', href: '/watchlist', icon: List },
  { name: 'Alerts', href: '/alerts', icon: Bell },
  { name: 'Backtesting', href: '/backtesting', icon: FlaskConical },
  { name: 'Analytics', href: '/analytics', icon: LineChart },
  { name: 'MLOps', href: '/mlops', icon: Cpu },
  { name: 'Lab', href: '/scenarios', icon: Target },
  { name: 'Research', href: '/research', icon: BookOpen },
];

function LogoIcon() {
  return (
    <svg className="h-6 w-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M18 20V10" />
      <path d="M12 20V4" />
      <path d="M6 20v-6" />
    </svg>
  );
}

export function Header() {
  const pathname = usePathname();
  const router = useRouter();
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [suggestions, setSuggestions] = useState<any[]>([]);
  const [showSuggest, setShowSuggest] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [user, setUser] = useState<any>(null);
  const [isLoadingUser, setIsLoadingUser] = useState(true);
  const { open, setOpen } = useCommandPalette();
  const suggestTimer = React.useRef<ReturnType<typeof setTimeout> | null>(null);

  const handleLogout = async () => {
    try {
      await api.logout();
    } catch (err) {
      console.warn('[header] logout failed', err);
    }
    window.location.href = '/login';
  };

  const fetchUser = async () => {
    // Do not call getMe if we are not authenticated - avoids 401 loop for logged-out visitors
    if (!api.isAuthenticated()) {
      setUser(null);
      setIsLoadingUser(false);
      return;
    }
    try {
      const userData = await api.getMe();
      setUser(userData);
    } catch (err) {
      const msg = err instanceof Error ? err.message : '';
      if (!msg.toLowerCase().includes('401') && !msg.toLowerCase().includes('unauthorized')) {
        console.warn('[header] getMe failed', err);
      }
      setUser(null);
    } finally {
      setIsLoadingUser(false);
    }
  };

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (mounted) fetchUser();
  }, [mounted]);

  if (!mounted) {
    return (
      <header className="sticky top-0 z-50 w-full border-b border-slate-200 dark:border-slate-800 bg-white/95 dark:bg-slate-950/95 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-[1400px] items-center justify-between px-4">
          <Link href="/dashboard" className="flex items-center gap-2 font-bold text-xl text-primary">
            <LogoIcon />
            <span>StockAI</span>
          </Link>
        </div>
      </header>
    );
  }

  return (
    <header className="sticky top-0 z-50 w-full border-b border-slate-200 dark:border-slate-800 bg-white/95 dark:bg-slate-950/95 backdrop-blur supports-[backdrop-filter]:bg-white/60">
      <div className="mx-auto flex h-14 max-w-[1400px] items-center justify-between px-4">
        <div className="flex items-center gap-6">
          <Link href="/dashboard" className="flex items-center gap-2 font-bold text-xl text-primary">
            <LogoIcon />
            <span>StockAI</span>
          </Link>
          <nav className="hidden md:flex items-center gap-1" aria-label="Main navigation">
            {navigation.map((item) => (
              <Link
                key={item.name}
                href={item.href}
                className={cn(
                  'flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-colors',
                  pathname === item.href
                    ? 'bg-primary text-primary-foreground'
                    : 'text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800'
                )}
              >
                <item.icon className="h-4 w-4" />
                {item.name}
              </Link>
            ))}
          </nav>
        </div>

        <div className="hidden md:flex items-center gap-4">
          <div className="relative">
            <form
              onSubmit={(e) => {
                e.preventDefault();
                if (suggestions[0]) {
                  const s = suggestions[0];
                  router.push(`/stocks/${encodeURIComponent(s.symbol)}?exchange=${encodeURIComponent(s.exchange_code || s.exchange)}`);
                } else if (searchQuery.trim()) {
                  router.push(`/stocks/${encodeURIComponent(searchQuery.trim().toUpperCase())}?exchange=NASDAQ`);
                }
                setShowSuggest(false);
              }}
            >
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
              <Input
                placeholder="Search ticker or company…  ⌘K"
                className="w-64 pl-10 pr-4 py-2 text-sm"
                value={searchQuery}
                onChange={(e) => {
                  const v = e.target.value;
                  setSearchQuery(v);
                  setShowSuggest(true);
                  if (suggestTimer.current) clearTimeout(suggestTimer.current);
                  if (!v.trim()) {
                    setSuggestions([]);
                    setSearchError(null);
                    return;
                  }
                  suggestTimer.current = setTimeout(async () => {
                    try {
                      const r = await api.searchInstruments(v.trim(), { limit: 6 });
                      setSuggestions(Array.isArray(r) ? r : []);
                      setSearchError(null);
                    } catch (err) {
                      console.warn('[header] instrument search failed', err);
                      setSuggestions([]);
                      setSearchError('Search unavailable - showing no results.');
                    }
                  }, 220);
                }}
                onFocus={() => setOpen(false)}
                onKeyDown={(e) => {
                  if (e.key === 'k' && (e.metaKey || e.ctrlKey)) {
                    e.preventDefault();
                    setOpen(true);
                  }
                }}
                aria-label="Search instruments"
              />
            </form>
            {searchError && showSuggest && (
              <p className="absolute top-11 z-50 w-80 px-3 py-2 text-xs text-amber-600 dark:text-amber-400 bg-popover border border-border rounded-xl shadow-xl">
                {searchError}
              </p>
            )}
            {showSuggest && suggestions.length > 0 && (
              <div className="absolute top-11 z-50 w-80 overflow-hidden rounded-xl border border-border bg-popover shadow-xl">
                {suggestions.map((s: any) => (
                  <button
                    key={`${s.symbol}-${s.exchange_code || s.exchange}`}
                    onClick={() => {
                      setShowSuggest(false);
                      setSearchQuery('');
                      router.push(`/stocks/${encodeURIComponent(s.symbol)}?exchange=${encodeURIComponent(s.exchange_code || s.exchange)}`);
                    }}
                    className="flex w-full items-center gap-3 px-3 py-2 text-left text-sm hover:bg-muted"
                  >
                    <span className="font-mono font-bold">{s.symbol}</span>
                    <span className="rounded border border-border px-1 text-[10px] text-muted-foreground">{s.exchange_code || s.exchange}</span>
                    <span className="truncate text-xs text-muted-foreground">{s.name} · {s.market}</span>
                  </button>
                ))}
                <button
                  onClick={() => {
                    setShowSuggest(false);
                    setOpen(true);
                  }}
                  className="w-full border-t border-border px-3 py-2 text-left text-xs text-muted-foreground hover:bg-muted"
                >
                  Open command palette (⌘K) for more…
                </button>
              </div>
            )}
          </div>
          <CommandPalette open={open} onClose={() => setOpen(false)} />

          <Button variant="ghost" size="icon" onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')} aria-label="Toggle theme">
            {theme === 'dark' ? <Sun className="h-5 w-5" /> : <Moon className="h-5 w-5" />}
          </Button>

          {isLoadingUser ? (
            <div className="h-8 w-8 rounded-full bg-slate-200 dark:bg-slate-700 animate-pulse" />
          ) : user ? (
            <DropdownMenu>
              <DropdownMenuTrigger render={<Button variant="ghost" aria-label="User menu" className="relative h-8 w-8 rounded-full" />}>
                  <Avatar className="h-8 w-8">
                    <AvatarImage src={user.avatar || `https://ui-avatars.com/api/?name=${encodeURIComponent(user.name || user.email)}`} />
                    <AvatarFallback>{user.name?.charAt(0) || user.email.charAt(0)}</AvatarFallback>
                  </Avatar>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-56">
                <div className="px-2 py-1">
                  <p className="text-sm font-medium">{user.name || 'User'}</p>
                  <p className="text-xs text-slate-500">{user.email}</p>
                </div>
                <DropdownMenuSeparator />
                <DropdownMenuItem render={<Link href="/settings" className="flex w-full" />}>
                    <User className="mr-2 h-4 w-4" />
                    Profile & Settings
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={handleLogout} className="text-red-600 focus:text-red-600">
                  <LogOut className="mr-2 h-4 w-4" />
                  Log out
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          ) : (
            <div className="flex items-center gap-2">
              <Link href="/login">
                <Button variant="ghost" size="sm">Sign in</Button>
              </Link>
              <Link href="/signup">
                <Button size="sm">Get Started</Button>
              </Link>
            </div>
          )}
        </div>

        <Sheet open={mobileMenuOpen} onOpenChange={setMobileMenuOpen}>
          <SheetTrigger render={<Button variant="ghost" size="icon" className="md:hidden" aria-label="Open menu" />}>
              <Menu className="h-6 w-6" />
          </SheetTrigger>
          <SheetContent side="right" className="w-72">
            <div className="flex flex-col gap-4 p-4">
              <div className="flex items-center justify-between">
                <h3 className="font-semibold">Menu</h3>
                <Button variant="ghost" size="icon" onClick={() => setMobileMenuOpen(false)}>
                  <X className="h-5 w-5" />
                </Button>
              </div>
              <nav className="flex flex-col gap-2">
                {navigation.map((item) => (
                  <Link
                    key={item.name}
                    href={item.href}
                    onClick={() => setMobileMenuOpen(false)}
                    className={cn(
                      'flex items-center gap-3 px-3 py-2 rounded-lg text-base font-medium',
                      pathname === item.href
                        ? 'bg-primary text-primary-foreground'
                        : 'text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800'
                    )}
                  >
                    <item.icon className="h-5 w-5" />
                    {item.name}
                  </Link>
                ))}
              </nav>
              <div className="border-t pt-4">
                {isLoadingUser ? (
                  <div className="h-8 w-8 rounded-full bg-slate-200 dark:bg-slate-700 animate-pulse mx-auto" />
                ) : user ? (
                  <div className="flex items-center gap-3 px-2">
                    <Avatar className="h-10 w-10">
                      <AvatarImage src={user.avatar || `https://ui-avatars.com/api/?name=${encodeURIComponent(user.name || user.email)}`} />
                      <AvatarFallback>{user.name?.charAt(0) || user.email.charAt(0)}</AvatarFallback>
                    </Avatar>
                    <div className="flex-1 min-w-0">
                      <p className="font-medium truncate">{user.name || 'User'}</p>
                      <p className="text-xs text-slate-500 truncate">{user.email}</p>
                    </div>
                  </div>
                ) : (
                  <div className="flex flex-col gap-2">
                    <Link href="/login" onClick={() => setMobileMenuOpen(false)}>
                      <Button className="w-full justify-start gap-2">
                        <LogIn className="h-4 w-4" /> Sign in
                      </Button>
                    </Link>
                    <Link href="/signup" onClick={() => setMobileMenuOpen(false)}>
                      <Button variant="outline" className="w-full justify-start gap-2">
                        <UserPlus className="h-4 w-4" /> Sign up
                      </Button>
                    </Link>
                  </div>
                )}
              </div>
            </div>
          </SheetContent>
        </Sheet>
      </div>
    </header>
  );
}
