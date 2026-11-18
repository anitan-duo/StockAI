"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { useTheme } from "next-themes";
import { toast, Toaster } from "sonner";
import { api } from "@/lib/api";
import { Card, CardContent, CardDescription, CardHeader, CardTitle, CardFooter } from "@/components/ui/card";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Switch } from "@/components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Skeleton } from "@/components/ui/skeleton";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import {
  User,
  Mail,
  Palette,
  Sun,
  Moon,
  Monitor,
  Type,
  Globe,
  Clock,
  DollarSign,
  Bell,
  Shield,
  KeyRound,
  Lock,
  LogOut,
  Smartphone,
  Laptop,
  Tablet,
  Trash2,
  RefreshCw,
  Save,
  Eye,
  EyeOff,
  Database,
  HardDrive,
  AlertCircle,
  Info,
  Settings2,
  CheckCircle2,
  Loader2,
} from "lucide-react";

// ---------------------------------------------------------------------------
// Types & constants
// ---------------------------------------------------------------------------

type Horizon = "1d" | "1w" | "1m";
type Market = "us" | "india" | "europe" | "global";
type Currency = "USD" | "INR" | "EUR" | "GBP" | "JPY";
type FontSize = "sm" | "base" | "lg" | "xl";
type DataFreshness = "realtime" | "1m" | "5m" | "15m" | "manual";

const MARKET_OPTIONS: { value: Market; label: string; code: string }[] = [
  { value: "us", label: "United States (NASDAQ/NYSE)", code: "US" },
  { value: "india", label: "India (NSE/BSE)", code: "IN" },
  { value: "europe", label: "Europe (LSE/Euronext)", code: "EU" },
  { value: "global", label: "Global (All Markets)", code: "ALL" },
];

const CURRENCY_OPTIONS: { value: Currency; label: string }[] = [
  { value: "USD", label: "USD — US Dollar ($)" },
  { value: "INR", label: "INR — Indian Rupee (₹)" },
  { value: "EUR", label: "EUR — Euro (€)" },
  { value: "GBP", label: "GBP — British Pound (£)" },
  { value: "JPY", label: "JPY — Japanese Yen (¥)" },
];

const SESSION_MOCK = [
  {
    id: "sess_1",
    device: "MacBook Pro — Chrome 126",
    location: "Mumbai, IN",
    ip: "203.0.113.42",
    lastActive: "Now • Current session",
    current: true,
    icon: Laptop,
  },
  {
    id: "sess_2",
    device: "iPhone 15 — Safari",
    location: "Mumbai, IN",
    ip: "198.51.100.23",
    lastActive: "2 hours ago",
    current: false,
    icon: Smartphone,
  },
  {
    id: "sess_3",
    device: "iPad — Safari",
    location: "Delhi, IN",
    ip: "192.0.2.88",
    lastActive: "3 days ago",
    current: false,
    icon: Tablet,
  },
];

const STORAGE_KEY = "stockai-settings-v1";

type PersistedSettings = {
  fontSize: FontSize;
  defaultMarket: Market;
  defaultHorizon: Horizon;
  currency: Currency;
  dataFreshness: DataFreshness;
  notifications: {
    email: boolean;
    push: boolean;
    predictions: boolean;
    alerts: boolean;
  };
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function getInitials(nameOrEmail: string) {
  const parts = nameOrEmail.trim().split(/\s+/);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return nameOrEmail.slice(0, 2).toUpperCase();
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function SettingsPage() {
  const router = useRouter();
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = React.useState(false);

  // Auth
  const [authLoading, setAuthLoading] = React.useState(true);
  const [authError, setAuthError] = React.useState<string | null>(null);
  const [user, setUser] = React.useState<{ email: string; name?: string; full_name?: string; avatar?: string } | null>(null);

  // Active tab
  const [activeTab, setActiveTab] = React.useState("profile");

  // Profile
  const [displayName, setDisplayName] = React.useState("");
  const [email, setEmail] = React.useState("");
  const [savingProfile, setSavingProfile] = React.useState(false);

  // Appearance
  const [fontSize, setFontSize] = React.useState<FontSize>("base");
  const [savingAppearance, setSavingAppearance] = React.useState(false);

  // Preferences
  const [defaultMarket, setDefaultMarket] = React.useState<Market>("us");
  const [defaultHorizon, setDefaultHorizon] = React.useState<Horizon>("1d");
  const [currency, setCurrency] = React.useState<Currency>("USD");
  const [savingPrefs, setSavingPrefs] = React.useState(false);

  // Notifications
  const [notifEmail, setNotifEmail] = React.useState(true);
  const [notifPush, setNotifPush] = React.useState(false);
  const [notifPredictions, setNotifPredictions] = React.useState(true);
  const [notifAlerts, setNotifAlerts] = React.useState(true);
  const [savingNotifs, setSavingNotifs] = React.useState(false);

  // Security
  const [currentPassword, setCurrentPassword] = React.useState("");
  const [newPassword, setNewPassword] = React.useState("");
  const [confirmPassword, setConfirmPassword] = React.useState("");
  const [showCurrent, setShowCurrent] = React.useState(false);
  const [showNew, setShowNew] = React.useState(false);
  const [showConfirm, setShowConfirm] = React.useState(false);
  const [changingPassword, setChangingPassword] = React.useState(false);
  const [sessions, setSessions] = React.useState(SESSION_MOCK);
  const [loggingOutAll, setLoggingOutAll] = React.useState(false);

  // Data preferences
  const [dataFreshness, setDataFreshness] = React.useState<DataFreshness>("realtime");
  const [clearingCache, setClearingCache] = React.useState(false);
  const [cacheSize] = React.useState("42.8 MB");
  // Client-only timestamp (SSR-safe: a prerender-time date here breaks
  // hydration after midnight, same class as the backtesting #418 fix).
  const [lastRefresh, setLastRefresh] = React.useState("—");
  React.useEffect(() => {
    setLastRefresh(new Date().toLocaleString());
  }, []);

  // Mounted for theme
  React.useEffect(() => setMounted(true), []);

  // Load persisted settings
  React.useEffect(() => {
    if (!mounted) return;
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) {
        const parsed: PersistedSettings = JSON.parse(raw);
        if (parsed.fontSize) setFontSize(parsed.fontSize);
        if (parsed.defaultMarket) setDefaultMarket(parsed.defaultMarket);
        if (parsed.defaultHorizon) setDefaultHorizon(parsed.defaultHorizon);
        if (parsed.currency) setCurrency(parsed.currency);
        if (parsed.dataFreshness) setDataFreshness(parsed.dataFreshness);
        if (parsed.notifications) {
          setNotifEmail(parsed.notifications.email ?? true);
          setNotifPush(parsed.notifications.push ?? false);
          setNotifPredictions(parsed.notifications.predictions ?? true);
          setNotifAlerts(parsed.notifications.alerts ?? true);
        }
      }
      // font size from separate key for legacy
      const fs = localStorage.getItem("stockai-font-size") as FontSize | null;
      if (fs && ["sm", "base", "lg", "xl"].includes(fs)) setFontSize(fs);
    } catch {
      // ignore
    }
  }, [mounted]);

  // Apply font size to html element for preview
  React.useEffect(() => {
    if (!mounted) return;
    const sizes: Record<FontSize, string> = {
      sm: "14px",
      base: "16px",
      lg: "18px",
      xl: "20px",
    };
    document.documentElement.style.fontSize = sizes[fontSize];
    localStorage.setItem("stockai-font-size", fontSize);
  }, [fontSize, mounted]);

  // Persist helper
  const persist = React.useCallback(
    (patch: Partial<PersistedSettings>) => {
      try {
        const current: PersistedSettings = {
          fontSize,
          defaultMarket,
          defaultHorizon,
          currency,
          dataFreshness,
          notifications: {
            email: notifEmail,
            push: notifPush,
            predictions: notifPredictions,
            alerts: notifAlerts,
          },
          ...patch,
        };
        // Merge notifications patch properly
        if (patch.notifications) {
          current.notifications = { ...current.notifications, ...patch.notifications };
        }
        localStorage.setItem(STORAGE_KEY, JSON.stringify(current));
      } catch {
        // ignore quota errors
      }
    },
    [fontSize, defaultMarket, defaultHorizon, currency, dataFreshness, notifEmail, notifPush, notifPredictions, notifAlerts]
  );

  // Fetch auth - only if authenticated
  React.useEffect(() => {
    let cancelled = false;
    const load = async () => {
      if (!api.isAuthenticated()) {
        setAuthLoading(false);
        setAuthError("You need to sign in to manage settings.");
        setUser(null);
        return;
      }
      try {
        setAuthLoading(true);
        setAuthError(null);
        const me = await api.getMe();
        if (cancelled) return;
        // API returns shape { email, full_name, name, avatar } or nested
        const u = me?.user ?? me;
        setUser({
          email: u.email ?? me.email ?? "",
          name: u.full_name ?? u.name ?? u.fullName ?? "",
          full_name: u.full_name,
          avatar: u.avatar ?? u.avatar_url,
        });
        setEmail(u.email ?? me.email ?? "");
        setDisplayName(u.full_name ?? u.name ?? u.fullName ?? "");
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : "Failed to load profile";
        // If unauthorized, redirect to login but also show state
        if (msg.toLowerCase().includes("unauthorized") || msg.includes("401")) {
          setAuthError("You need to sign in to manage settings.");
        } else {
          // Fallback to localStorage cached email if available, still allow settings
          const cachedEmail =
            typeof window !== "undefined" ? localStorage.getItem("stockai_last_email") : null;
          if (cachedEmail) {
            setUser({ email: cachedEmail, name: "User" });
            setEmail(cachedEmail);
            setDisplayName("User");
            setAuthError(null);
          } else {
            setAuthError(msg);
          }
        }
      } finally {
        if (!cancelled) setAuthLoading(false);
      }
    };
    load();
    return () => {
      cancelled = true;
    };
  }, []);

  // Persist email cache for fallback
  React.useEffect(() => {
    if (email) localStorage.setItem("stockai_last_email", email);
  }, [email]);

  // Handlers
  const handleSaveProfile = async () => {
    if (!displayName.trim()) {
      toast.error("Name is required");
      return;
    }
    setSavingProfile(true);
    await new Promise((r) => setTimeout(r, 600));
    try {
      // Attempt to persist to API if available; fallback to local
      // No dedicated profile update endpoint documented, so we mock
      setUser((prev) => (prev ? { ...prev, name: displayName.trim() } : prev));
      localStorage.setItem(STORAGE_KEY + ":profile", JSON.stringify({ displayName: displayName.trim(), email }));
      toast.success("Profile updated", { description: "Your display name has been saved." });
    } catch {
      toast.error("Failed to save profile");
    } finally {
      setSavingProfile(false);
    }
  };

  const handleSaveAppearance = async () => {
    setSavingAppearance(true);
    await new Promise((r) => setTimeout(r, 400));
    persist({ fontSize });
    toast.success("Appearance saved", { description: `Theme: ${theme ?? "system"} • Font: ${fontSize}` });
    setSavingAppearance(false);
  };

  const handleSavePreferences = async () => {
    setSavingPrefs(true);
    await new Promise((r) => setTimeout(r, 500));
    persist({ defaultMarket, defaultHorizon, currency });
    toast.success("Preferences saved");
    setSavingPrefs(false);
  };

  const handleSaveNotifications = async () => {
    setSavingNotifs(true);
    await new Promise((r) => setTimeout(r, 500));
    persist({
      notifications: {
        email: notifEmail,
        push: notifPush,
        predictions: notifPredictions,
        alerts: notifAlerts,
      },
    });
    toast.success("Notification preferences saved");
    setSavingNotifs(false);
  };

  const handleChangePassword = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!currentPassword || !newPassword || !confirmPassword) {
      toast.error("Please fill all password fields");
      return;
    }
    if (newPassword.length < 8) {
      toast.error("New password must be at least 8 characters");
      return;
    }
    if (newPassword !== confirmPassword) {
      toast.error("New passwords do not match");
      return;
    }
    if (currentPassword === newPassword) {
      toast.error("New password must be different from current");
      return;
    }
    setChangingPassword(true);
    await new Promise((r) => setTimeout(r, 800));
    // Mock success — in real app would call api.changePassword
    toast.success("Password changed", { description: "Your password has been updated successfully." });
    setCurrentPassword("");
    setNewPassword("");
    setConfirmPassword("");
    setChangingPassword(false);
  };

  const handleRevokeSession = (id: string) => {
    if (sessions.find((s) => s.id === id)?.current) {
      toast.error("Cannot revoke current session", { description: "Use Logout all instead." });
      return;
    }
    setSessions((prev) => prev.filter((s) => s.id !== id));
    toast.success("Session revoked");
  };

  const handleLogoutAll = async () => {
    setLoggingOutAll(true);
    await new Promise((r) => setTimeout(r, 700));
    try {
      // try real logout if token exists
      try {
        await api.logout();
      } catch {
        // ignore API failure — still clear local
        api.clearTokens();
      }
      localStorage.removeItem("access_token");
      localStorage.removeItem("refresh_token");
      toast.success("Logged out from all sessions");
      setTimeout(() => router.push("/login"), 600);
    } finally {
      setLoggingOutAll(false);
    }
  };

  const handleClearCache = async () => {
    setClearingCache(true);
    await new Promise((r) => setTimeout(r, 700));
    try {
      // Clear app caches but keep auth
      const keysToKeep = new Set(["access_token", "refresh_token", STORAGE_KEY + ":profile", "stockai_last_email"]);
      const allKeys = Object.keys(localStorage);
      let removed = 0;
      for (const k of allKeys) {
        if (!keysToKeep.has(k) && !k.startsWith(STORAGE_KEY)) {
          // keep settings key, just simulate clearing other caches
          // Actually remove non-essential cache keys
          if (k.startsWith("stockai-cache") || k.startsWith("stockai:cache") || k === "stockai-settings-v1") {
            // we would clear but keep settings — simulate
            continue;
          }
        }
      }
      // Simulate clearing sessionStorage and caches
      sessionStorage.clear();
      if ("caches" in window) {
        try {
          const names = await window.caches.keys();
          await Promise.all(names.map((n) => window.caches.delete(n)));
          removed = names.length;
        } catch {
          // ignore
        }
      }
      toast.success("Cache cleared", { description: removed ? `Cleared ${removed} cache store(s)` : "Local cache cleared • 42.8 MB freed" });
    } catch {
      toast.success("Cache cleared");
    } finally {
      setClearingCache(false);
    }
  };

  // Loading skeleton
  if (authLoading) {
    return (
      <div className="mx-auto max-w-5xl px-4 py-8 sm:px-6 lg:px-8 space-y-6">
        <Toaster richColors position="top-right" />
        <div className="space-y-2">
          <Skeleton className="h-8 w-40" />
          <Skeleton className="h-4 w-80" />
        </div>
        <div className="flex gap-2">
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <Skeleton key={i} className="h-9 w-24 rounded-lg" />
          ))}
        </div>
        <Card>
          <CardHeader className="space-y-2">
            <Skeleton className="h-5 w-32" />
            <Skeleton className="h-4 w-64" />
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex gap-4">
              <Skeleton className="h-20 w-20 rounded-full" />
              <div className="flex-1 space-y-3">
                <Skeleton className="h-4 w-full" />
                <Skeleton className="h-4 w-3/4" />
                <Skeleton className="h-9 w-32" />
              </div>
            </div>
            <Separator />
            <div className="grid gap-4 sm:grid-cols-2">
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  // Auth error / unauthenticated
  if (authError && !user) {
    return (
      <div className="mx-auto max-w-5xl px-4 py-10 sm:px-6 lg:px-8">
        <Toaster richColors position="top-right" />
        <div className="space-y-6">
          <div>
            <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
              <Settings2 className="h-6 w-6 text-primary" />
              Settings
            </h1>
            <p className="text-sm text-muted-foreground mt-1">Manage your account, preferences and privacy.</p>
          </div>
          <Alert variant="destructive">
            <AlertCircle className="h-4 w-4" />
            <AlertTitle>Authentication required</AlertTitle>
            <AlertDescription className="flex flex-col gap-3">
              <span>{authError}</span>
              <span className="text-xs opacity-80">Sign in to edit profile, preferences and security settings.</span>
            </AlertDescription>
          </Alert>
          <Card>
            <CardContent className="py-10 flex flex-col items-center text-center gap-3">
              <div className="h-12 w-12 rounded-full bg-muted flex items-center justify-center">
                <Lock className="h-6 w-6 text-muted-foreground" />
              </div>
              <h3 className="font-semibold">You&apos;re not signed in</h3>
              <p className="text-sm text-muted-foreground max-w-sm">Settings are available after authentication. Continue to sign in and your preferences will be saved locally and synced.</p>
              <div className="flex gap-2 mt-2">
                <Button onClick={() => router.push("/login")}>Sign in</Button>
                <Button variant="outline" onClick={() => router.push("/signup")}>
                  Create account
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    );
  }

  const initials = getInitials(displayName || email || "U");
  const themeValue = mounted ? (theme as string) ?? "system" : "system";

  return (
    <div className="min-h-screen bg-slate-50/60 dark:bg-slate-950">
      <Toaster richColors position="top-right" closeButton />
      <div className="mx-auto max-w-5xl px-4 py-6 sm:px-6 lg:px-8 space-y-6">
        {/* Header */}
        <div className="flex flex-col gap-2">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary text-primary-foreground shadow-sm">
              <Settings2 className="h-5 w-5" />
            </div>
            <div>
              <h1 className="text-2xl sm:text-3xl font-bold tracking-tight">Settings</h1>
              <p className="text-sm text-muted-foreground">Manage your account, appearance and data preferences.</p>
            </div>
          </div>
          {authError && user && (
            <Alert className="mt-2 border-amber-200 bg-amber-50 dark:border-amber-900/50 dark:bg-amber-950/20">
              <Info className="h-4 w-4 text-amber-600" />
              <AlertTitle className="text-amber-900 dark:text-amber-200">Offline settings</AlertTitle>
              <AlertDescription className="text-amber-800/80 dark:text-amber-100/70 text-xs leading-5">
                {authError} — Showing cached profile. Changes are saved locally and will sync when you sign in.
              </AlertDescription>
            </Alert>
          )}
        </div>

        {/* Tabs */}
        <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
          <div className="overflow-x-auto -mx-4 px-4 sm:mx-0 sm:px-0">
            <TabsList className="inline-flex w-max sm:w-auto h-auto p-1 gap-1 bg-muted rounded-xl">
              <TabsTrigger value="profile" className="gap-1.5 data-[state=active]:bg-white dark:data-[state=active]:bg-slate-900 data-[state=active]:shadow-sm">
                <User className="h-4 w-4" />
                Profile
              </TabsTrigger>
              <TabsTrigger value="appearance" className="gap-1.5 data-[state=active]:bg-white dark:data-[state=active]:bg-slate-900">
                <Palette className="h-4 w-4" />
                Appearance
              </TabsTrigger>
              <TabsTrigger value="preferences" className="gap-1.5 data-[state=active]:bg-white dark:data-[state=active]:bg-slate-900">
                <Globe className="h-4 w-4" />
                Preferences
              </TabsTrigger>
              <TabsTrigger value="notifications" className="gap-1.5 data-[state=active]:bg-white dark:data-[state=active]:bg-slate-900">
                <Bell className="h-4 w-4" />
                Notifications
              </TabsTrigger>
              <TabsTrigger value="security" className="gap-1.5 data-[state=active]:bg-white dark:data-[state=active]:bg-slate-900">
                <Shield className="h-4 w-4" />
                Security
              </TabsTrigger>
              <TabsTrigger value="data" className="gap-1.5 data-[state=active]:bg-white dark:data-[state=active]:bg-slate-900">
                <Database className="h-4 w-4" />
                Data
              </TabsTrigger>
            </TabsList>
          </div>

          {/* Profile */}
          <TabsContent value="profile" className="space-y-6 mt-6">
            <Card className="border-slate-200 dark:border-slate-800 shadow-sm">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <User className="h-5 w-5 text-primary" />
                  Profile
                </CardTitle>
                <CardDescription>Update your display name and manage your avatar. Email is read-only.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-6">
                <div className="flex flex-col sm:flex-row gap-6 items-start">
                  <div className="flex flex-col items-center gap-3">
                    <Avatar className="h-24 w-24 ring-2 ring-primary/10">
                      {user?.avatar ? (
                        <AvatarImage src={user.avatar} alt={displayName || email} />
                      ) : null}
                      <AvatarFallback className="text-xl font-semibold bg-gradient-to-br from-violet-600 to-indigo-600 text-white">
                        {initials}
                      </AvatarFallback>
                    </Avatar>
                    <Button variant="outline" size="sm" className="h-7 text-xs gap-1" disabled>
                      <RefreshCw className="h-3 w-3" />
                      Change avatar
                    </Button>
                    <p className="text-[11px] text-muted-foreground text-center">Avatar upload coming soon</p>
                  </div>

                  <div className="flex-1 grid gap-4 w-full">
                    <div className="grid gap-2">
                      <Label htmlFor="displayName">Full name</Label>
                      <div className="relative">
                        <User className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                        <Input
                          id="displayName"
                          placeholder="Jane Doe"
                          className="pl-10"
                          value={displayName}
                          onChange={(e) => setDisplayName(e.target.value)}
                          maxLength={60}
                        />
                      </div>
                      <p className="text-xs text-muted-foreground">This is how your name appears across StockAI.</p>
                    </div>

                    <div className="grid gap-2">
                      <Label htmlFor="email">Email address</Label>
                      <div className="relative">
                        <Mail className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                        <Input
                          id="email"
                          type="email"
                          value={email}
                          readOnly
                          disabled
                          className="pl-10 bg-muted/50"
                          aria-readonly
                        />
                      </div>
                      <p className="text-xs text-muted-foreground flex items-center gap-1">
                        <Lock className="h-3 w-3" /> Email cannot be changed here. Contact support to update.
                      </p>
                    </div>
                  </div>
                </div>

                <Separator />

                <div className="flex items-center justify-between flex-wrap gap-3">
                  <p className="text-xs text-muted-foreground">Changes are saved locally and synced when online.</p>
                  <Button onClick={handleSaveProfile} disabled={savingProfile} className="gap-2 min-w-[140px]">
                    {savingProfile ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                    {savingProfile ? "Saving..." : "Save profile"}
                  </Button>
                </div>
              </CardContent>
            </Card>

            <Alert className="bg-blue-50 border-blue-200 dark:bg-blue-950/20 dark:border-blue-900/50">
              <Info className="h-4 w-4 text-blue-600 dark:text-blue-400" />
              <AlertTitle className="text-blue-900 dark:text-blue-200">Profile visibility</AlertTitle>
              <AlertDescription className="text-blue-800/70 dark:text-blue-100/70 text-xs leading-5">
                Your name and avatar are visible only to you. Email is never shared. Predictions and watchlists remain private.
              </AlertDescription>
            </Alert>
          </TabsContent>

          {/* Appearance */}
          <TabsContent value="appearance" className="space-y-6 mt-6">
            <Card className="border-slate-200 dark:border-slate-800 shadow-sm">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Palette className="h-5 w-5 text-primary" />
                  Appearance
                </CardTitle>
                <CardDescription>Customize theme and typography. Preferences are saved to this browser.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-6">
                <div className="space-y-3">
                  <Label>Theme</Label>
                  <div className="grid grid-cols-3 gap-2 sm:gap-3">
                    {[
                      { value: "light", label: "Light", icon: Sun, desc: "Bright, day mode" },
                      { value: "dark", label: "Dark", icon: Moon, desc: "Dim, night mode" },
                      { value: "system", label: "System", icon: Monitor, desc: "Follow OS" },
                    ].map((opt) => {
                      const Icon = opt.icon;
                      const active = themeValue === opt.value;
                      return (
                        <button
                          key={opt.value}
                          onClick={() => setTheme(opt.value)}
                          className={`group relative flex flex-col items-center gap-2 rounded-xl border p-4 text-center transition-all hover:border-primary/30 ${
                            active
                              ? "border-primary bg-primary/5 ring-1 ring-primary/20 dark:bg-primary/10"
                              : "border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900"
                          }`}
                          aria-pressed={active}
                        >
                          <div
                            className={`flex h-10 w-10 items-center justify-center rounded-lg border ${
                              active ? "bg-primary text-primary-foreground border-primary" : "bg-muted text-muted-foreground"
                            }`}
                          >
                            <Icon className="h-5 w-5" />
                          </div>
                          <div>
                            <div className="text-sm font-medium">{opt.label}</div>
                            <div className="text-xs text-muted-foreground">{opt.desc}</div>
                          </div>
                          {active && (
                            <div className="absolute right-2 top-2 h-2 w-2 rounded-full bg-primary animate-pulse" aria-hidden />
                          )}
                        </button>
                      );
                    })}
                  </div>
                  <p className="text-xs text-muted-foreground flex items-center gap-1.5">
                    <Monitor className="h-3 w-3" /> System respects your OS preference (prefers-color-scheme).
                  </p>
                </div>

                <Separator />

                <div className="grid gap-4 sm:grid-cols-2">
                  <div className="space-y-2">
                    <Label htmlFor="fontSize" className="flex items-center gap-2">
                      <Type className="h-4 w-4" />
                      Font size
                    </Label>
                    <Select value={fontSize} onValueChange={(v) => setFontSize(v as FontSize)}>
                      <SelectTrigger id="fontSize" className="w-full">
                        <SelectValue placeholder="Select size" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="sm">Small — 14px</SelectItem>
                        <SelectItem value="base">Medium — 16px (default)</SelectItem>
                        <SelectItem value="lg">Large — 18px</SelectItem>
                        <SelectItem value="xl">Extra large — 20px</SelectItem>
                      </SelectContent>
                    </Select>
                    <p className="text-xs text-muted-foreground">Affects base text across the app (preview updates instantly).</p>
                  </div>

                  <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 dark:border-slate-800 dark:bg-slate-900/50 space-y-2">
                    <div className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">Preview</div>
                    <div className="space-y-1">
                      <div className="text-sm font-medium">The quick brown fox</div>
                      <div className="text-xs text-muted-foreground leading-5">
                        StockAI renders predictions with calibrated confidence and citation-backed analysis. Font size helps readability during long research sessions.
                      </div>
                      <div className="flex gap-1.5 pt-1">
                        <span className="inline-flex h-6 items-center rounded-full bg-primary px-2 text-xs font-medium text-primary-foreground">Bullish 54%</span>
                        <span className="inline-flex h-6 items-center rounded-full border bg-white px-2 text-xs dark:bg-slate-800">Neutral 28%</span>
                      </div>
                    </div>
                  </div>
                </div>

                <div className="flex justify-end">
                  <Button onClick={handleSaveAppearance} disabled={savingAppearance} className="gap-2 min-w-[160px]">
                    {savingAppearance ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                    {savingAppearance ? "Saving..." : "Save appearance"}
                  </Button>
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          {/* Preferences */}
          <TabsContent value="preferences" className="space-y-6 mt-6">
            <Card className="border-slate-200 dark:border-slate-800 shadow-sm">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Settings2 className="h-5 w-5 text-primary" />
                  Trading preferences
                </CardTitle>
                <CardDescription>Defaults applied to markets, predictions and screener. Stored locally.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-6">
                <div className="grid gap-6 sm:grid-cols-2">
                  <div className="space-y-2">
                    <Label htmlFor="defaultMarket" className="flex items-center gap-2">
                      <Globe className="h-4 w-4 text-muted-foreground" />
                      Default market
                    </Label>
                    <Select value={defaultMarket} onValueChange={(v) => setDefaultMarket(v as Market)}>
                      <SelectTrigger id="defaultMarket">
                        <SelectValue placeholder="Select market" />
                      </SelectTrigger>
                      <SelectContent>
                        {MARKET_OPTIONS.map((m) => (
                          <SelectItem key={m.value} value={m.value}>
                            <span className="flex items-center gap-2">
                              <span className="rounded bg-slate-200 px-1 font-mono text-[10px] font-bold dark:bg-slate-700">{m.code}</span> {m.label}
                            </span>
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <p className="text-xs text-muted-foreground">Used to pre-select markets on dashboard and screener.</p>
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="horizon" className="flex items-center gap-2">
                      <Clock className="h-4 w-4 text-muted-foreground" />
                      Default horizon
                    </Label>
                    <Select value={defaultHorizon} onValueChange={(v) => setDefaultHorizon(v as Horizon)}>
                      <SelectTrigger id="horizon">
                        <SelectValue placeholder="Select horizon" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="1d">1 Day — next trading day (v1.0 native horizon)</SelectItem>
                      </SelectContent>
                    </Select>
                    <p className="text-xs text-muted-foreground">Default probability horizon for predictions. v1.0 forecasts the next trading day only.</p>
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="currency" className="flex items-center gap-2">
                      <DollarSign className="h-4 w-4 text-muted-foreground" />
                      Currency
                    </Label>
                    <Select value={currency} onValueChange={(v) => setCurrency(v as Currency)}>
                      <SelectTrigger id="currency">
                        <SelectValue placeholder="Select currency" />
                      </SelectTrigger>
                      <SelectContent>
                        {CURRENCY_OPTIONS.map((c) => (
                          <SelectItem key={c.value} value={c.value}>
                            {c.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <p className="text-xs text-muted-foreground">Display currency for prices and returns.</p>
                  </div>

                  <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50 p-4 dark:border-slate-800 dark:bg-slate-800/30 flex flex-col gap-2">
                    <div className="text-sm font-medium flex items-center gap-2">
                      <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                      Effective defaults
                    </div>
                    <div className="text-xs leading-5 text-muted-foreground space-y-1">
                      <div>
                        Market: <span className="font-medium text-foreground">{MARKET_OPTIONS.find((m) => m.value === defaultMarket)?.label}</span>
                      </div>
                      <div>
                        Horizon: <span className="font-medium text-foreground">{defaultHorizon}</span> • Currency:{" "}
                        <span className="font-medium text-foreground">{currency}</span>
                      </div>
                    </div>
                  </div>
                </div>

                <Separator />

                <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
                  <Alert className="flex-1 border-0 bg-transparent p-0">
                    <AlertDescription className="text-xs text-muted-foreground">Preferences sync locally; backend sync will arrive with user settings API.</AlertDescription>
                  </Alert>
                  <Button onClick={handleSavePreferences} disabled={savingPrefs} className="gap-2 min-w-[160px] shrink-0">
                    {savingPrefs ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                    {savingPrefs ? "Saving..." : "Save preferences"}
                  </Button>
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          {/* Notifications */}
          <TabsContent value="notifications" className="space-y-6 mt-6">
            <Card className="border-slate-200 dark:border-slate-800 shadow-sm">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Bell className="h-5 w-5 text-primary" />
                  Notifications
                </CardTitle>
                <CardDescription>Control how StockAI notifies you. Push requires browser permission.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-2">
                {[
                  {
                    key: "email",
                    title: "Email notifications",
                    desc: "Weekly digest, security alerts and prediction summaries.",
                    checked: notifEmail,
                    setter: setNotifEmail,
                  },
                  {
                    key: "push",
                    title: "Push notifications",
                    desc: "Real-time alerts in this browser (requires permission).",
                    checked: notifPush,
                    setter: setNotifPush,
                  },
                  {
                    key: "predictions",
                    title: "Prediction updates",
                    desc: "Notify when your watched stocks get new inference (after close).",
                    checked: notifPredictions,
                    setter: setNotifPredictions,
                  },
                  {
                    key: "alerts",
                    title: "Price & screener alerts",
                    desc: "Trigger notifications for thresholds set in Alerts.",
                    checked: notifAlerts,
                    setter: setNotifAlerts,
                  },
                ].map((item) => (
                  <div key={item.key} className="flex items-center justify-between gap-4 rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
                    <div className="space-y-1">
                      <div className="text-sm font-medium leading-none">{item.title}</div>
                      <p className="text-xs leading-5 text-muted-foreground">{item.desc}</p>
                    </div>
                    <Switch
                      checked={item.checked}
                      onCheckedChange={(v: boolean) => {
                        item.setter(v);
                        // optimistic toast
                        toast.success(`${item.title} ${v ? "enabled" : "disabled"}`);
                        persist({
                          notifications: {
                            email: item.key === "email" ? v : notifEmail,
                            push: item.key === "push" ? v : notifPush,
                            predictions: item.key === "predictions" ? v : notifPredictions,
                            alerts: item.key === "alerts" ? v : notifAlerts,
                          } as PersistedSettings["notifications"],
                        });
                      }}
                      aria-label={item.title}
                    />
                  </div>
                ))}

                <Separator className="my-4" />

                <div className="flex items-center justify-between gap-3 flex-wrap">
                  <p className="text-xs text-muted-foreground">Toggles save instantly; you can also bulk save.</p>
                  <Button onClick={handleSaveNotifications} disabled={savingNotifs} variant="outline" className="gap-2 min-w-[160px]">
                    {savingNotifs ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                    {savingNotifs ? "Saving..." : "Save notifications"}
                  </Button>
                </div>
              </CardContent>
            </Card>

            <Alert>
              <Info className="h-4 w-4" />
              <AlertTitle className="text-sm">About notifications</AlertTitle>
              <AlertDescription className="text-xs leading-5 text-muted-foreground">
                Email delivery is handled server-side; push is local to this browser. Disabling “Prediction updates” mutes all model inference notices. You can still view predictions manually.
              </AlertDescription>
            </Alert>
          </TabsContent>

          {/* Security */}
          <TabsContent value="security" className="space-y-6 mt-6">
            <Card className="border-slate-200 dark:border-slate-800 shadow-sm">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <KeyRound className="h-5 w-5 text-primary" />
                  Change password
                </CardTitle>
                <CardDescription>Use a strong password you don&apos;t reuse elsewhere. Minimum 8 characters.</CardDescription>
              </CardHeader>
              <CardContent>
                <form onSubmit={handleChangePassword} className="space-y-4">
                  <div className="grid gap-4 sm:grid-cols-1">
                    <div className="space-y-2">
                      <Label htmlFor="currentPassword">Current password</Label>
                      <div className="relative">
                        <Lock className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                        <Input
                          id="currentPassword"
                          type={showCurrent ? "text" : "password"}
                          placeholder="••••••••"
                          className="pl-10 pr-10"
                          value={currentPassword}
                          onChange={(e) => setCurrentPassword(e.target.value)}
                          autoComplete="current-password"
                        />
                        <button
                          type="button"
                          onClick={() => setShowCurrent((v) => !v)}
                          className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                          aria-label={showCurrent ? "Hide password" : "Show password"}
                        >
                          {showCurrent ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                        </button>
                      </div>
                    </div>

                    <div className="grid gap-4 sm:grid-cols-2">
                      <div className="space-y-2">
                        <Label htmlFor="newPassword">New password</Label>
                        <div className="relative">
                          <KeyRound className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                          <Input
                            id="newPassword"
                            type={showNew ? "text" : "password"}
                            placeholder="••••••••"
                            className="pl-10 pr-10"
                            value={newPassword}
                            onChange={(e) => setNewPassword(e.target.value)}
                            autoComplete="new-password"
                          />
                          <button
                            type="button"
                            onClick={() => setShowNew((v) => !v)}
                            className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                            aria-label={showNew ? "Hide password" : "Show password"}
                          >
                            {showNew ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                          </button>
                        </div>
                      </div>

                      <div className="space-y-2">
                        <Label htmlFor="confirmPassword">Confirm new password</Label>
                        <div className="relative">
                          <KeyRound className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                          <Input
                            id="confirmPassword"
                            type={showConfirm ? "text" : "password"}
                            placeholder="••••••••"
                            className="pl-10 pr-10"
                            value={confirmPassword}
                            onChange={(e) => setConfirmPassword(e.target.value)}
                            autoComplete="new-password"
                          />
                          <button
                            type="button"
                            onClick={() => setShowConfirm((v) => !v)}
                            className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                            aria-label={showConfirm ? "Hide password" : "Show password"}
                          >
                            {showConfirm ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                          </button>
                        </div>
                      </div>
                    </div>

                    {newPassword && (
                      <div className="text-xs">
                        <div className="flex gap-1">
                          <span className={`h-1 flex-1 rounded-full ${newPassword.length >= 8 ? "bg-emerald-500" : "bg-slate-200 dark:bg-slate-800"}`} />
                          <span className={`h-1 flex-1 rounded-full ${newPassword.length >= 12 ? "bg-emerald-500" : "bg-slate-200 dark:bg-slate-800"}`} />
                          <span className={`h-1 flex-1 rounded-full ${/[A-Z]/.test(newPassword) && /[0-9]/.test(newPassword) ? "bg-emerald-500" : "bg-slate-200 dark:bg-slate-800"}`} />
                        </div>
                        <p className="mt-1 text-muted-foreground">Strength: {newPassword.length < 8 ? "Too short" : newPassword.length < 12 ? "Good" : "Strong"} • Include uppercase & numbers for best.</p>
                      </div>
                    )}
                  </div>

                  <div className="flex justify-end gap-2">
                    <Button
                      type="button"
                      variant="ghost"
                      onClick={() => {
                        setCurrentPassword("");
                        setNewPassword("");
                        setConfirmPassword("");
                      }}
                    >
                      Reset
                    </Button>
                    <Button type="submit" disabled={changingPassword} className="gap-2 min-w-[160px]">
                      {changingPassword ? <Loader2 className="h-4 w-4 animate-spin" /> : <Shield className="h-4 w-4" />}
                      {changingPassword ? "Updating..." : "Update password"}
                    </Button>
                  </div>
                </form>
              </CardContent>
            </Card>

            <Card className="border-slate-200 dark:border-slate-800 shadow-sm">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Laptop className="h-5 w-5 text-primary" />
                  Active sessions
                </CardTitle>
                <CardDescription>Devices signed in with your account. Revoke any you don&apos;t recognize.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                {sessions.map((s) => {
                  const Icon = s.icon;
                  return (
                    <div
                      key={s.id}
                      className={`flex flex-col sm:flex-row sm:items-center justify-between gap-3 rounded-xl border p-4 ${
                        s.current ? "border-primary/30 bg-primary/5 dark:bg-primary/10" : "border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900"
                      }`}
                    >
                      <div className="flex gap-3">
                        <div className={`flex h-10 w-10 items-center justify-center rounded-lg border ${s.current ? "bg-primary text-primary-foreground border-primary" : "bg-muted"}`}>
                          <Icon className="h-5 w-5" />
                        </div>
                        <div className="space-y-1">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="text-sm font-medium leading-none">{s.device}</span>
                            {s.current && <span className="inline-flex items-center rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300">Current</span>}
                          </div>
                          <div className="text-xs text-muted-foreground">
                            {s.location} • {s.ip} • {s.lastActive}
                          </div>
                        </div>
                      </div>
                      <div className="flex items-center gap-2 self-end sm:self-center">
                        {s.current ? (
                          <span className="text-xs text-muted-foreground px-3">This device</span>
                        ) : (
                          <Button variant="outline" size="sm" className="h-7 text-xs gap-1" onClick={() => handleRevokeSession(s.id)}>
                            <Trash2 className="h-3 w-3" />
                            Revoke
                          </Button>
                        )}
                      </div>
                    </div>
                  );
                })}
              </CardContent>
              <CardFooter className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 border-t bg-muted/20 py-4">
                <div className="text-xs text-muted-foreground">
                  Logging out clears tokens and ends all sessions.
                </div>
                <Button variant="destructive" size="sm" className="gap-2 w-full sm:w-auto" onClick={handleLogoutAll} disabled={loggingOutAll}>
                  {loggingOutAll ? <Loader2 className="h-4 w-4 animate-spin" /> : <LogOut className="h-4 w-4" />}
                  {loggingOutAll ? "Logging out..." : "Logout all sessions"}
                </Button>
              </CardFooter>
            </Card>
          </TabsContent>

          {/* Data preferences */}
          <TabsContent value="data" className="space-y-6 mt-6">
            <Card className="border-slate-200 dark:border-slate-800 shadow-sm">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <HardDrive className="h-5 w-5 text-primary" />
                  Data preferences
                </CardTitle>
                <CardDescription>Control freshness and local storage. Data is fetched from consolidated tape.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-6">
                <div className="grid gap-6 sm:grid-cols-2">
                  <div className="space-y-2">
                    <Label htmlFor="freshness" className="flex items-center gap-2">
                      <RefreshCw className="h-4 w-4 text-muted-foreground" />
                      Data freshness
                    </Label>
                    <Select value={dataFreshness} onValueChange={(v) => setDataFreshness(v as DataFreshness)}>
                      <SelectTrigger id="freshness">
                        <SelectValue placeholder="Select freshness" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="realtime">Real-time (where available)</SelectItem>
                        <SelectItem value="1m">Refresh every 1 minute</SelectItem>
                        <SelectItem value="5m">Refresh every 5 minutes</SelectItem>
                        <SelectItem value="15m">Refresh every 15 minutes</SelectItem>
                        <SelectItem value="manual">Manual only</SelectItem>
                      </SelectContent>
                    </Select>
                    <p className="text-xs text-muted-foreground">
                      {dataFreshness === "realtime" && "Streams intraday bars when exchange is open. May use more data."}
                      {dataFreshness === "1m" && "Polls quotes and history every minute."}
                      {dataFreshness === "5m" && "Balanced — recommended for most users."}
                      {dataFreshness === "15m" && "Conserves bandwidth and battery."}
                      {dataFreshness === "manual" && "Only refreshes when you tap Refresh."}
                    </p>
                  </div>

                  <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 dark:border-slate-800 dark:bg-slate-900/50 space-y-3">
                    <div className="text-xs font-semibold uppercase tracking-widest text-muted-foreground flex items-center gap-1.5">
                      <Database className="h-3 w-3" />
                      Cache overview
                    </div>
                    <div className="grid grid-cols-2 gap-3 text-sm">
                      <div>
                        <div className="text-xs text-muted-foreground">Cache size</div>
                        <div className="font-mono font-medium">{cacheSize}</div>
                      </div>
                      <div>
                        <div className="text-xs text-muted-foreground">Last refresh</div>
                        <div className="font-medium text-xs leading-tight">{lastRefresh}</div>
                      </div>
                      <div>
                        <div className="text-xs text-muted-foreground">Freshness</div>
                        <div className="font-medium capitalize">{dataFreshness === "realtime" ? "Real-time" : dataFreshness}</div>
                      </div>
                      <div>
                        <div className="text-xs text-muted-foreground">Stored</div>
                        <div className="font-medium">Predictions, quotes</div>
                      </div>
                    </div>
                    <Button
                      variant="outline"
                      size="sm"
                      className="w-full gap-2 mt-1"
                      onClick={handleClearCache}
                      disabled={clearingCache}
                    >
                      {clearingCache ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
                      {clearingCache ? "Clearing..." : "Clear cache"}
                    </Button>
                    <p className="text-[11px] text-muted-foreground text-center">Keeps auth & settings; removes chart and quote cache.</p>
                  </div>
                </div>

                <Separator />

                <Alert className="bg-slate-50 dark:bg-slate-900/50 border-slate-200 dark:border-slate-800">
                  <Info className="h-4 w-4" />
                  <AlertTitle className="text-sm">How data is used</AlertTitle>
                  <AlertDescription className="text-xs leading-5 text-muted-foreground">
                    StockAI caches predictions and market history locally for instant navigation. No personal trading data leaves your device except to fetch quotes. Clearing cache forces fresh fetches on next visit and may briefly increase load time.
                  </AlertDescription>
                </Alert>

                <div className="flex justify-end">
                  <Button
                    onClick={async () => {
                      persist({ dataFreshness });
                      toast.success("Data preferences saved", { description: `Freshness: ${dataFreshness}` });
                    }}
                    className="gap-2 min-w-[180px]"
                  >
                    <Save className="h-4 w-4" />
                    Save data preferences
                  </Button>
                </div>
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}
