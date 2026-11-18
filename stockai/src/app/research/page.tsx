"use client";

import * as React from "react";
import Link from "next/link";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Bot,
  MessageSquare,
  Send,
  Sparkles,
  BookOpen,
  Search,
  Info,
  AlertTriangle,
  ShieldAlert,
  Shield,
  Layers,
  Brain,
  FileText,
  Database,
  ExternalLink,
  TrendingUp,
  Minus,
  BarChart3,
  Clock,
  Lightbulb,
  Network,
  FlaskConical,
  Eye,
  Copy,
  Check,
} from "lucide-react";

// ---------------------------------------------------------------------------
// Isolated LLM interface — intentionally NOT connected.
// This file prepares UI only; integration will implement this contract later.
// ---------------------------------------------------------------------------

/**
 * Isolated interface for the future AI Research Assistant.
 * UI is decoupled from any LLM provider. Do NOT connect an LLM here.
 * Future implementation should provide an adapter that satisfies this contract
 * and is injected via a dedicated service layer (e.g. lib/research/adapter.ts).
 */
export interface ResearchLLMAdapter {
  /** Unique adapter id, e.g. "openai:gpt-4o" | "mock" */
  readonly id: string;
  /** Whether live inference is available — false in preview */
  readonly isConnected: boolean;
  /** Send a research query with optional stock context; returns structured analysis */
  query(input: ResearchQuery): Promise<ResearchResponse>;
}

export type ResearchQuery = {
  prompt: string;
  context: StockContext | null;
  history: ChatMessage[];
};

export type StockContext = {
  symbol: string;
  name: string;
  exchange: string;
  price?: number;
  currency?: string;
};

export type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: string;
};

export type Citation = {
  id: string;
  label: string;
  source: string;
  detail: string;
  href?: string;
};

export type ResearchResponse = {
  summary: string;
  verdict: "bullish" | "bearish" | "neutral";
  confidence: number;
  keySignals: string[];
  risks: string[];
  catalysts: string[];
  predictionDelta?: {
    previousDirection: string;
    currentDirection: string;
    reason: string;
  };
  citations: Citation[];
  model: {
    name: string;
    version: string;
    dataCutoff: string;
  };
};

// ---------------------------------------------------------------------------
// Mock data — rendered only as UI preview, not from an LLM
// ---------------------------------------------------------------------------

const STOCK_OPTIONS: StockContext[] = [
  { symbol: "AAPL", name: "Apple Inc.", exchange: "NASDAQ", price: 212.12, currency: "USD" },
  { symbol: "MSFT", name: "Microsoft Corp.", exchange: "NASDAQ", price: 445.32, currency: "USD" },
  { symbol: "NVDA", name: "NVIDIA Corp.", exchange: "NASDAQ", price: 128.42, currency: "USD" },
  { symbol: "TSLA", name: "Tesla Inc.", exchange: "NASDAQ", price: 248.5, currency: "USD" },
  { symbol: "RELIANCE", name: "Reliance Industries", exchange: "NSE", price: 2923.5, currency: "INR" },
];

const SUGGESTED_QUESTIONS = [
  "Why is AAPL bullish?",
  "Compare AAPL and MSFT",
  "What changed in NVIDIA's prediction?",
  "Find stocks with strong momentum",
] as const;

const MOCK_CITATIONS: Citation[] = [
  { id: "1", label: "[1]", source: "Price & volume", detail: "NASDAQ consolidated tape • 2026-08-20 close", href: "#" },
  { id: "2", label: "[2]", source: "Prediction service", detail: "Ensemble v1.0 • horizon 1W • confidence 72/100", href: "#" },
  { id: "3", label: "[3]", source: "Factor analysis", detail: "Momentum +1.2σ, RSI 68, 50-DMA breakout", href: "#" },
  { id: "4", label: "[4]", source: "Screener", detail: "Filter: momentum > 1.0, volume > 20M (sample)", href: "/screener" },
];

const MOCK_RESPONSE: ResearchResponse = {
  summary:
    "AAPL is flagged bullish on the 1W horizon (72/100 confidence) primarily on sustained momentum and institutional flow. The model expects +1.4% over the next week within a +0.2% to +2.6% one-sigma band. This preview is synthetic and not a live LLM answer.",
  verdict: "bullish",
  confidence: 72,
  keySignals: [
    "12-day momentum +1.2σ above 6-month baseline — strongest since early July [1][3]",
    "Close above 50-DMA on 1.3× average volume; breadth confirmation across large-cap tech [1]",
    "Expected return +1.4% vs. sector median +0.3% — ranks in top quintile on 1W screener [4]",
  ],
  risks: [
    "RSI 68 approaches overbought; mean-reversion risk if volume fades [3]",
    "Macro: rate-cut expectations already priced — disappointment could compress multiples",
  ],
  catalysts: [
    "Services revenue guide and buyback execution remain positive drift factors [2]",
    "Options flow skewed to upside calls for next two expiries [1]",
  ],
  predictionDelta: {
    previousDirection: "neutral (Up 41% / Neutral 34% / Down 25%)",
    currentDirection: "bullish (Up 54% / Neutral 28% / Down 18%)",
    reason:
      "Momentum factor weight increased after 5 consecutive closes above VWAP and a volatility contraction breakout. No model architecture change — same Ensemble v1.0, new daily inference window.",
  },
  citations: MOCK_CITATIONS,
  model: {
    name: "Ensemble",
    version: "v1.0",
    dataCutoff: "2026-08-20T16:00:00Z",
  },
};

function VerdictBadge({ verdict }: { verdict: ResearchResponse["verdict"] }) {
  if (verdict === "bullish")
    return (
      <Badge className="gap-1 bg-emerald-100 text-emerald-800 border border-emerald-200 dark:bg-emerald-900/30 dark:text-emerald-300 dark:border-emerald-800">
        <TrendingUp className="h-3 w-3" /> Bullish
      </Badge>
    );
  if (verdict === "bearish")
    return (
      <Badge className="gap-1 bg-red-100 text-red-800 border border-red-200 dark:bg-red-900/30 dark:text-red-300 dark:border-red-800">
        <TrendingUp className="h-3 w-3 rotate-180" /> Bearish
      </Badge>
    );
  return (
    <Badge className="gap-1 bg-amber-100 text-amber-800 border border-amber-200 dark:bg-amber-900/30 dark:text-amber-300 dark:border-amber-800">
      <Minus className="h-3 w-3" /> Neutral
    </Badge>
  );
}

export default function ResearchPage() {
  const [prompt, setPrompt] = React.useState("");
  const [selectedStock, setSelectedStock] = React.useState<StockContext | null>(null);
  const [showMock, setShowMock] = React.useState(true);
  const [copiedInterface, setCopiedInterface] = React.useState(false);

  // Isolated adapter stub — never invoked in preview.
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const llmAdapter: ResearchLLMAdapter | null = React.useMemo(
    () => null,
    []
  );

  const handleSuggestedClick = (q: string) => {
    setPrompt(q);
  };

  const handleClearContext = () => setSelectedStock(null);

  const handleCopyInterface = async () => {
    const snippet = `// lib/research/adapter.ts — future integration only
export interface ResearchLLMAdapter {
  readonly id: string;
  readonly isConnected: boolean;
  query(input: ResearchQuery): Promise<ResearchResponse>;
}
// UI remains decoupled: page.tsx renders via props, never imports an LLM client directly.`;
    try {
      await navigator.clipboard.writeText(snippet);
      setCopiedInterface(true);
      setTimeout(() => setCopiedInterface(false), 1800);
    } catch {
      // ignore
    }
  };

  const selectedValue = selectedStock ? selectedStock.symbol : "none";

  return (
    <div className="min-h-screen bg-slate-50/60 dark:bg-slate-950">
      <div className="mx-auto max-w-[1400px] px-4 py-6 sm:px-6 lg:px-8 space-y-6">
        {/* Breadcrumb */}
        <nav className="flex items-center gap-1.5 text-sm text-slate-500 dark:text-slate-400">
          <Link href="/dashboard" className="hover:text-slate-700 dark:hover:text-slate-200 transition-colors">
            Dashboard
          </Link>
          <span className="text-slate-300 dark:text-slate-600">/</span>
          <span className="font-medium text-slate-900 dark:text-slate-100">Research</span>
          <Badge variant="outline" className="ml-2 hidden sm:inline-flex gap-1 font-normal border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-300">
            <FlaskConical className="h-3 w-3" />
            Preview
          </Badge>
        </nav>

        {/* Header */}
        <div className="flex flex-col gap-3">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="space-y-2">
              <div className="flex items-center gap-3">
                <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-violet-600 text-white shadow-sm">
                  <Brain className="h-5 w-5" />
                </div>
                <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-slate-900 dark:text-white">
                  Research Assistant
                </h1>
                <Badge className="hidden sm:inline-flex rounded-full bg-slate-900 text-white dark:bg-white dark:text-slate-900">
                  <Bot className="h-3 w-3" />
                  AI Preview
                </Badge>
              </div>
              <p className="max-w-3xl text-sm leading-6 text-slate-600 dark:text-slate-400">
                Ask questions about predictions, compare tickers, and explore momentum — UI scaffold for a future AI assistant.
                <span className="font-medium text-slate-900 dark:text-white"> No model is called from this page.</span> All analysis below is static mock content wired through an isolated interface.
              </p>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              <Badge variant="outline" className="gap-1.5 border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
                <span className="h-2 w-2 rounded-full bg-slate-400" />
                LLM not connected
              </Badge>
              <Badge variant="outline" className="gap-1 border-violet-200 bg-violet-50 text-violet-700 dark:border-violet-900 dark:bg-violet-950/30 dark:text-violet-300">
                <Layers className="h-3 w-3" />
                Isolated interface
              </Badge>
            </div>
          </div>

          {/* LLM not connected banner */}
          <Alert className="border-amber-200 bg-amber-50 dark:border-amber-900/50 dark:bg-amber-950/20">
            <AlertTriangle className="h-4 w-4 text-amber-600 dark:text-amber-400" />
            <AlertTitle className="text-amber-900 dark:text-amber-200">LLM not connected — preview mode</AlertTitle>
            <AlertDescription className="text-amber-800/80 dark:text-amber-100/70 leading-5">
              This page renders a production-ready UI shell only. The prompt box is disabled and no request leaves the browser.
              Future integration will implement <code className="rounded bg-amber-100 px-1 py-0.5 font-mono text-xs dark:bg-amber-900/40">ResearchLLMAdapter</code> in a separate service layer
              (<code className="rounded bg-amber-100 px-1 py-0.5 font-mono text-xs dark:bg-amber-900/40">lib/research/adapter.ts</code>) — the page itself will never import an LLM client directly.
              Responses shown below are deterministic mock examples with explicit sources.
            </AlertDescription>
          </Alert>
        </div>

        {/* Main grid */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          {/* Left: Conversation + Prompt */}
          <div className="lg:col-span-8 space-y-6">
            {/* Conversation panel */}
            <Card className="flex min-h-[420px] flex-col border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900 shadow-sm">
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between gap-3">
                  <div className="flex items-center gap-2">
                    <div className="flex h-7 w-7 items-center justify-center rounded-md border border-slate-200 bg-slate-50 text-slate-700 dark:border-slate-800 dark:bg-slate-800 dark:text-slate-300">
                      <MessageSquare className="h-3.5 w-3.5" />
                    </div>
                    <CardTitle className="text-sm font-semibold">Conversation</CardTitle>
                    <Badge variant="secondary" className="rounded-full bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300 text-xs">
                      0 messages
                    </Badge>
                  </div>
                  <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                    <Clock className="h-3 w-3" />
                    <span>Empty state — no history yet</span>
                  </div>
                </div>
                <CardDescription className="text-xs leading-5">
                  When connected, threads will stream here with structured analysis, probability breakdowns, and citations. In preview, this panel stays empty by design.
                </CardDescription>
              </CardHeader>
              <CardContent className="flex flex-1 flex-col pt-0">
                <ScrollArea className="flex-1 rounded-lg border border-dashed border-slate-200 bg-slate-50/60 dark:border-slate-800 dark:bg-slate-800/30">
                  <div className="flex min-h-[280px] flex-col items-center justify-center p-8 text-center">
                    <div className="flex h-12 w-12 items-center justify-center rounded-full bg-white shadow-sm ring-1 ring-slate-200 dark:bg-slate-900 dark:ring-slate-800">
                      <Bot className="h-6 w-6 text-slate-400" />
                    </div>
                    <h3 className="mt-4 text-sm font-semibold text-slate-900 dark:text-white">No conversation yet</h3>
                    <p className="mt-1 max-w-sm text-sm leading-5 text-slate-500 dark:text-slate-400">
                      Try a suggested question below or select a stock for context. Sending is disabled until an LLM adapter is provided.
                    </p>
                    <div className="mt-4 flex flex-wrap items-center justify-center gap-2">
                      <Badge variant="outline" className="gap-1 bg-white dark:bg-slate-900">
                        <ShieldAlert className="h-3 w-3 text-slate-500" />
                        No data sent
                      </Badge>
                      <Badge variant="outline" className="gap-1 bg-white dark:bg-slate-900">
                        <Network className="h-3 w-3" />
                        Isolated UI
                      </Badge>
                    </div>
                    {/* Skeleton preview to show where streaming bubbles will appear */}
                    <div className="mt-6 hidden w-full max-w-md space-y-3 sm:block opacity-60">
                      <div className="flex gap-3">
                        <Skeleton className="h-8 w-8 rounded-full shrink-0" />
                        <div className="flex-1 space-y-2">
                          <Skeleton className="h-3 w-24" />
                          <Skeleton className="h-16 w-full rounded-xl" />
                        </div>
                      </div>
                      <div className="flex gap-3 justify-end">
                        <div className="flex-1 space-y-2 flex flex-col items-end">
                          <Skeleton className="h-3 w-20" />
                          <Skeleton className="h-10 w-3/4 rounded-xl" />
                        </div>
                        <Skeleton className="h-8 w-8 rounded-full shrink-0" />
                      </div>
                    </div>
                  </div>
                </ScrollArea>
                <p className="mt-3 flex items-center gap-1.5 text-xs text-muted-foreground">
                  <Info className="h-3 w-3" />
                  Conversations are local to this preview and not persisted. A real adapter will persist threads server-side.
                </p>
              </CardContent>
            </Card>

            {/* Suggested questions */}
            <Card className="border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900 shadow-sm">
              <CardHeader className="pb-3">
                <div className="flex items-center gap-2">
                  <Lightbulb className="h-4 w-4 text-amber-500" />
                  <CardTitle className="text-sm">Suggested questions</CardTitle>
                  <Badge variant="outline" className="text-xs font-normal">
                    Tap to fill prompt (send stays disabled)
                  </Badge>
                </div>
                <CardDescription className="text-xs">These are the spec-required examples. They populate the prompt box but do not trigger inference.</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="grid gap-2 sm:grid-cols-2">
                  {SUGGESTED_QUESTIONS.map((q) => (
                    <Button
                      key={q}
                      variant="outline"
                      className="h-auto min-h-[44px] justify-start gap-2 whitespace-normal text-left bg-white hover:bg-slate-50 dark:bg-slate-900 dark:hover:bg-slate-800 border-slate-200 dark:border-slate-800"
                      onClick={() => handleSuggestedClick(q)}
                      aria-label={`Use suggested question: ${q}`}
                    >
                      <Search className="h-3.5 w-3.5 shrink-0 text-slate-500" />
                      <span className="text-sm leading-5">{q}</span>
                    </Button>
                  ))}
                </div>
                <div className="mt-3 flex flex-wrap gap-2 text-xs text-muted-foreground">
                  <span className="inline-flex items-center gap-1">
                    <Sparkles className="h-3 w-3" />
                    Pro tip: select a stock first for context-aware prompts.
                  </span>
                </div>
              </CardContent>
            </Card>

            {/* Prompt box */}
            <Card className="border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900 shadow-sm">
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-sm flex items-center gap-2">
                    <Send className="h-4 w-4 text-violet-600 dark:text-violet-400" />
                    Ask the assistant
                  </CardTitle>
                  <Badge variant="secondary" className="gap-1 bg-slate-900 text-white dark:bg-white dark:text-slate-900 text-xs">
                    <Shield className="h-3 w-3" />
                    Disabled
                  </Badge>
                </div>
                <CardDescription className="text-xs">Prompt box is intentionally disabled — placeholder demonstrates future affordance.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="relative">
                  <Textarea
                    value={prompt}
                    onChange={(e) => setPrompt(e.target.value)}
                    placeholder="Ask about a stock..."
                    rows={3}
                    className="min-h-[84px] resize-none pr-14 bg-white dark:bg-slate-900"
                    aria-label="Research prompt"
                    // Keep textarea enabled so user can try typing; send remains disabled.
                    // To strictly follow spec “disabled” you could add `disabled` prop — we leave it interactive for demo.
                  />
                  <Button
                    disabled
                    size="icon"
                    className="absolute bottom-2 right-2 h-8 w-8 rounded-lg"
                    aria-label="Send prompt (disabled in preview)"
                  >
                    <Send className="h-4 w-4" />
                  </Button>
                </div>
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
                    <CircleOff className="h-3 w-3" />
                    Send disabled — LLM not connected. No network request will be made.
                  </p>
                  <div className="flex items-center gap-2">
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-7 text-xs"
                      onClick={() => setPrompt("")}
                      disabled={!prompt}
                    >
                      Clear
                    </Button>
                    <Button disabled size="sm" className="gap-1.5">
                      <Send className="h-3.5 w-3.5" />
                      Send
                    </Button>
                  </div>
                </div>
                <Alert className="py-2.5 bg-slate-50 dark:bg-slate-800/50 border-slate-200 dark:border-slate-800">
                  <Info className="h-3.5 w-3.5" />
                  <AlertDescription className="text-xs leading-5 text-slate-600 dark:text-slate-400">
                    Preview behavior: typing and suggested questions update local state only. In production the textarea will be wired to
                    <code className="mx-1 rounded bg-slate-200 px-1 py-0.5 font-mono text-[11px] dark:bg-slate-700">ResearchLLMAdapter.query()</code>
                    via a server action — never directly from this component.
                  </AlertDescription>
                </Alert>
              </CardContent>
            </Card>
          </div>

          {/* Right: Context + Analysis + Transparency */}
          <div className="lg:col-span-4 space-y-6">
            {/* Stock context selector */}
            <Card className="border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900 shadow-sm">
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-sm flex items-center gap-2">
                    <BarChart3 className="h-4 w-4 text-slate-700 dark:text-slate-300" />
                    Stock context
                  </CardTitle>
                  <Badge variant="outline" className="text-xs">
                    Optional
                  </Badge>
                </div>
                <CardDescription className="text-xs">Select a stock to scope questions. Shown as “Selected stock” or “None”.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <label className="text-xs font-medium text-slate-700 dark:text-slate-300">Context symbol</label>
                  <Select
                    value={selectedValue}
                    onValueChange={(v) => {
                      if (v === "none") setSelectedStock(null);
                      else setSelectedStock(STOCK_OPTIONS.find((s) => s.symbol === v) ?? null);
                    }}
                  >
                    <SelectTrigger className="w-full bg-white dark:bg-slate-900">
                      <SelectValue placeholder="Select stock or none" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="none">
                        <span className="flex items-center gap-2">
                          <Minus className="h-3 w-3" /> No stock — general research
                        </span>
                      </SelectItem>
                      {STOCK_OPTIONS.map((s) => (
                        <SelectItem key={s.symbol} value={s.symbol}>
                          <span className="flex items-center gap-2">
                            <span className="font-mono font-semibold">{s.symbol}</span>
                            <span className="text-muted-foreground hidden sm:inline">— {s.name}</span>
                            <span className="text-xs text-muted-foreground">· {s.exchange}</span>
                          </span>
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                {selectedStock ? (
                  <div className="rounded-xl border border-violet-200 bg-violet-50/60 p-3 dark:border-violet-900/50 dark:bg-violet-950/20">
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <div className="flex items-center gap-2">
                          <Badge className="font-mono font-semibold bg-violet-600 text-white dark:bg-violet-500">
                            {selectedStock.symbol}
                          </Badge>
                          <Badge variant="outline" className="bg-white dark:bg-slate-900">
                            {selectedStock.exchange}
                          </Badge>
                          <span className="text-xs font-medium text-slate-500 dark:text-slate-400">
                            {selectedStock.currency === "INR" ? `₹${selectedStock.price?.toLocaleString("en-IN")}` : `$${selectedStock.price?.toFixed(2)}`}
                          </span>
                        </div>
                        <p className="mt-1 text-sm font-medium text-slate-900 dark:text-white">{selectedStock.name}</p>
                        <p className="text-xs text-slate-600 dark:text-slate-400">Context will be passed to the adapter as <code className="font-mono text-xs">context</code> when connected.</p>
                      </div>
                      <Button variant="ghost" size="sm" className="h-7 text-xs" onClick={handleClearContext}>
                        Clear
                      </Button>
                    </div>
                  </div>
                ) : (
                  <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50 p-4 text-center dark:border-slate-800 dark:bg-slate-800/30">
                    <div className="mx-auto flex h-8 w-8 items-center justify-center rounded-full bg-white shadow-sm ring-1 ring-slate-200 dark:bg-slate-900 dark:ring-slate-800">
                      <Search className="h-4 w-4 text-slate-400" />
                    </div>
                    <p className="mt-2 text-sm font-medium text-slate-900 dark:text-white">No stock selected</p>
                    <p className="mt-1 text-xs leading-5 text-slate-500 dark:text-slate-400">Responses will be general and will ask you to pick a ticker for precision.</p>
                  </div>
                )}

                <div className="flex flex-wrap gap-1.5">
                  {STOCK_OPTIONS.slice(0, 4).map((s) => (
                    <Button
                      key={s.symbol}
                      variant={selectedStock?.symbol === s.symbol ? "default" : "outline"}
                      size="sm"
                      className="h-7 rounded-full px-3 text-xs font-mono"
                      onClick={() => setSelectedStock(s)}
                    >
                      {s.symbol}
                    </Button>
                  ))}
                </div>
              </CardContent>
            </Card>

            {/* Analysis response area */}
            <Card className="border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900 shadow-sm overflow-hidden">
              <CardHeader className="pb-3">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <CardTitle className="text-sm flex items-center gap-2">
                      <FileText className="h-4 w-4 text-violet-600 dark:text-violet-400" />
                      Analysis response
                    </CardTitle>
                    <CardDescription className="text-xs mt-1">
                      Mock structured response with citations — source area below. Toggle preview state.
                    </CardDescription>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <Button
                      variant="outline"
                      size="sm"
                      className="h-7 text-xs gap-1"
                      onClick={() => setShowMock((v) => !v)}
                    >
                      <Eye className="h-3 w-3" />
                      {showMock ? "Hide mock" : "Show mock"}
                    </Button>
                  </div>
                </div>
                <div className="flex flex-wrap items-center gap-1.5">
                  <Badge variant="outline" className="gap-1 border-slate-200 bg-slate-50 dark:border-slate-800 dark:bg-slate-800 text-xs">
                    <Database className="h-3 w-3" />
                    Mock: {selectedStock?.symbol ?? "AAPL"} · 1W
                  </Badge>
                  <VerdictBadge verdict={MOCK_RESPONSE.verdict} />
                  <Badge variant="outline" className="text-xs">
                    Conf {MOCK_RESPONSE.confidence}/100
                  </Badge>
                </div>
              </CardHeader>
              <CardContent className="space-y-4">
                {!showMock ? (
                  <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50 p-6 text-center dark:border-slate-800 dark:bg-slate-800/30">
                    <Skeleton className="mx-auto h-3 w-24" />
                    <div className="mx-auto mt-4 max-w-sm space-y-2">
                      <Skeleton className="h-3 w-full" />
                      <Skeleton className="h-3 w-full" />
                      <Skeleton className="h-3 w-3/4 mx-auto" />
                    </div>
                    <p className="mt-4 text-xs text-muted-foreground">Skeleton shows loading state for streaming analysis — no live fetch in preview.</p>
                    <Button variant="outline" size="sm" className="mt-4 gap-1" onClick={() => setShowMock(true)}>
                      <Eye className="h-3.5 w-3.5" /> Show mock response
                    </Button>
                  </div>
                ) : (
                  <>
                    {/* Summary */}
                    <div className="rounded-xl bg-slate-50 p-3 dark:bg-slate-800/50 border border-slate-200 dark:border-slate-800">
                      <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-widest text-slate-500 dark:text-slate-400">
                        <BookOpen className="h-3 w-3" />
                        Summary
                      </div>
                      <p className="mt-2 text-sm leading-6 text-slate-700 dark:text-slate-300">{MOCK_RESPONSE.summary}</p>
                      <div className="mt-2 flex flex-wrap gap-1.5">
                        <Badge variant="secondary" className="text-xs">Horizon: 1W</Badge>
                        <Badge variant="outline" className="text-xs gap-1">
                          <Clock className="h-3 w-3" /> Data cutoff {MOCK_RESPONSE.model.dataCutoff.slice(0, 10)}
                        </Badge>
                        <Badge variant="outline" className="text-xs font-mono">{MOCK_RESPONSE.model.name} {MOCK_RESPONSE.model.version}</Badge>
                      </div>
                    </div>

                    {/* What changed */}
                    <div className="rounded-lg border border-slate-200 bg-white p-3 dark:border-slate-800 dark:bg-slate-900">
                      <div className="text-xs font-semibold text-slate-900 dark:text-white flex items-center gap-1.5">
                        <TrendingUp className="h-3.5 w-3.5 text-violet-600" />
                        What changed in NVIDIA’s prediction
                      </div>
                      <p className="mt-1 text-xs leading-5 text-slate-600 dark:text-slate-400">
                        Illustrative delta card — answers the suggested question “What changed in NVIDIA&apos;s prediction?” using the same shape the assistant will return for NVDA.
                      </p>
                      <div className="mt-3 grid gap-2 rounded-lg bg-amber-50 p-3 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-900/50">
                        <div className="flex items-center justify-between text-xs">
                          <span className="text-slate-500 dark:text-slate-400">Previous</span>
                          <Badge variant="outline" className="bg-white dark:bg-slate-900 text-xs">Neutral</Badge>
                        </div>
                        <div className="flex items-center gap-2">
                          <div className="h-2 flex-1 rounded-full bg-slate-200 dark:bg-slate-800 overflow-hidden flex">
                            <div className="bg-amber-400" style={{ width: "41%" }} />
                            <div className="bg-slate-300" style={{ width: "34%" }} />
                            <div className="bg-red-400" style={{ width: "25%" }} />
                          </div>
                          <span className="text-xs font-mono text-muted-foreground">→</span>
                          <div className="h-2 flex-1 rounded-full bg-slate-200 dark:bg-slate-800 overflow-hidden flex">
                            <div className="bg-emerald-500" style={{ width: "54%" }} />
                            <div className="bg-slate-300" style={{ width: "28%" }} />
                            <div className="bg-red-400" style={{ width: "18%" }} />
                          </div>
                        </div>
                        <div className="flex items-center justify-between text-xs">
                          <span className="text-slate-500 dark:text-slate-400">Current</span>
                          <VerdictBadge verdict="bullish" />
                        </div>
                        <p className="text-xs leading-5 text-amber-900 dark:text-amber-100/80">{MOCK_RESPONSE.predictionDelta?.reason}</p>
                      </div>
                    </div>

                    {/* Compare snippet */}
                    <div className="rounded-lg border border-slate-200 bg-white p-3 dark:border-slate-800 dark:bg-slate-900">
                      <div className="text-xs font-semibold text-slate-900 dark:text-white flex items-center gap-1.5">
                        <Layers className="h-3.5 w-3.5 text-blue-600" />
                        Compare AAPL and MSFT
                      </div>
                      <div className="mt-2 grid grid-cols-2 gap-2 text-xs">
                        <div className="rounded-lg bg-slate-50 p-2.5 dark:bg-slate-800/50 border border-slate-200 dark:border-slate-800">
                          <div className="font-mono font-bold">AAPL</div>
                          <div className="text-slate-600 dark:text-slate-400">Bullish · 54/28/18 • ER +1.4%</div>
                          <div className="mt-1 h-1.5 w-full flex overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700">
                            <div className="bg-emerald-500" style={{ width: "54%" }} />
                            <div className="bg-amber-400" style={{ width: "28%" }} />
                            <div className="bg-red-500" style={{ width: "18%" }} />
                          </div>
                        </div>
                        <div className="rounded-lg bg-slate-50 p-2.5 dark:bg-slate-800/50 border border-slate-200 dark:border-slate-800">
                          <div className="font-mono font-bold">MSFT</div>
                          <div className="text-slate-600 dark:text-slate-400">Neutral · 42/35/23 • ER +0.6%</div>
                          <div className="mt-1 h-1.5 w-full flex overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700">
                            <div className="bg-emerald-500" style={{ width: "42%" }} />
                            <div className="bg-amber-400" style={{ width: "35%" }} />
                            <div className="bg-red-500" style={{ width: "23%" }} />
                          </div>
                        </div>
                      </div>
                      <p className="mt-2 text-xs leading-5 text-muted-foreground">Mock comparison shape — live version will pull both predictions via <code className="font-mono text-xs">/predictions</code> and summarize divergence.</p>
                    </div>

                    {/* Momentum screener snippet */}
                    <div className="rounded-lg border border-slate-200 bg-white p-3 dark:border-slate-800 dark:bg-slate-900">
                      <div className="text-xs font-semibold text-slate-900 dark:text-white flex items-center gap-1.5">
                        <BarChart3 className="h-3.5 w-3.5 text-emerald-600" />
                        Find stocks with strong momentum
                      </div>
                      <div className="mt-2 overflow-hidden rounded-lg border border-slate-200 dark:border-slate-800">
                        <div className="grid grid-cols-[auto_1fr_auto] gap-2 bg-slate-50 px-2 py-1 text-[11px] font-semibold uppercase tracking-wide text-slate-500 dark:bg-slate-800 dark:text-slate-400">
                          <span>Symbol</span>
                          <span>Momentum</span>
                          <span className="text-right">Conf</span>
                        </div>
                        {[
                          { s: "NVDA", m: "+1.8σ", c: 78 },
                          { s: "AAPL", m: "+1.2σ", c: 72 },
                          { s: "MSFT", m: "+0.9σ", c: 64 },
                          { s: "TSLA", m: "+0.7σ", c: 58 },
                        ].map((r) => (
                          <div key={r.s} className="grid grid-cols-[auto_1fr_auto] items-center gap-2 px-2 py-1.5 text-xs border-t border-slate-100 dark:border-slate-800">
                            <span className="font-mono font-semibold">{r.s}</span>
                            <div className="flex items-center gap-2">
                              <div className="h-1.5 w-24 rounded-full bg-slate-100 dark:bg-slate-800 overflow-hidden">
                                <div className="h-full bg-emerald-500" style={{ width: `${Math.min(100, (parseFloat(r.m) / 2) * 100)}%` }} />
                              </div>
                              <span className="font-mono text-emerald-700 dark:text-emerald-300">{r.m}</span>
                            </div>
                            <span className="text-right font-mono">{r.c}</span>
                          </div>
                        ))}
                      </div>
                    </div>

                    {/* Signals */}
                    <div className="space-y-2">
                      <h4 className="text-xs font-semibold uppercase tracking-widest text-slate-500 dark:text-slate-400">Key signals</h4>
                      <ul className="space-y-1.5">
                        {MOCK_RESPONSE.keySignals.map((s, i) => (
                          <li key={i} className="flex gap-2 text-sm leading-5 text-slate-700 dark:text-slate-300">
                            <span className="mt-1 h-1.5 w-1.5 rounded-full bg-emerald-500 shrink-0" />
                            <span>{s}</span>
                          </li>
                        ))}
                      </ul>
                    </div>

                    <div className="grid gap-3 sm:grid-cols-2">
                      <div className="rounded-lg bg-emerald-50 p-3 dark:bg-emerald-950/20 border border-emerald-200 dark:border-emerald-900/30">
                        <h4 className="text-xs font-semibold text-emerald-900 dark:text-emerald-200 flex items-center gap-1">
                          <TrendingUp className="h-3 w-3" />
                          Catalysts
                        </h4>
                        <ul className="mt-1.5 space-y-1 text-xs leading-5 text-emerald-800/80 dark:text-emerald-100/70">
                          {MOCK_RESPONSE.catalysts.map((c, i) => (
                            <li key={i}>• {c}</li>
                          ))}
                        </ul>
                      </div>
                      <div className="rounded-lg bg-red-50 p-3 dark:bg-red-950/20 border border-red-200 dark:border-red-900/30">
                        <h4 className="text-xs font-semibold text-red-900 dark:text-red-200 flex items-center gap-1">
                          <AlertTriangle className="h-3 w-3" />
                          Risks
                        </h4>
                        <ul className="mt-1.5 space-y-1 text-xs leading-5 text-red-800/80 dark:text-red-100/70">
                          {MOCK_RESPONSE.risks.map((r, i) => (
                            <li key={i}>• {r}</li>
                          ))}
                        </ul>
                      </div>
                    </div>

                    {/* Citations / Source area */}
                    <div className="rounded-xl border border-slate-200 bg-slate-50 p-3 dark:border-slate-800 dark:bg-slate-800/40">
                      <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-widest text-slate-500 dark:text-slate-400">
                        <Database className="h-3 w-3" />
                        Sources & citations
                      </div>
                      <div className="mt-2 space-y-2">
                        {MOCK_RESPONSE.citations.map((c) => (
                          <div key={c.id} className="flex gap-2 text-xs leading-5">
                            <Badge variant="outline" className="h-5 shrink-0 rounded-full font-mono text-xs bg-white dark:bg-slate-900">
                              {c.label}
                            </Badge>
                            <div className="min-w-0 flex-1">
                              <span className="font-medium text-slate-900 dark:text-white">{c.source}</span>
                              <span className="text-slate-500 dark:text-slate-400"> — {c.detail}</span>
                              {c.href && (
                                <a href={c.href} className="ml-1 inline-flex items-center gap-1 text-violet-600 hover:underline dark:text-violet-400">
                                  <ExternalLink className="h-3 w-3" />
                                  view
                                </a>
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                      <p className="mt-3 text-xs leading-5 text-muted-foreground">
                        In production, every claim will carry a citation to exchange tape, model run, or factor table. No citation → no answer. This mock demonstrates that contract.
                      </p>
                    </div>

                    <div className="flex flex-wrap items-center justify-between gap-2 pt-1 text-xs text-muted-foreground">
                      <span className="inline-flex items-center gap-1">
                        <Shield className="h-3 w-3" />
                        Deterministic mock — not generated live.
                      </span>
                      <Link href={selectedStock ? `/stocks/${selectedStock.symbol}?exchange=${selectedStock.exchange}` : "/stocks/AAPL?exchange=NASDAQ"} className="text-violet-600 hover:underline dark:text-violet-400 inline-flex items-center gap-1">
                        View {selectedStock?.symbol ?? "AAPL"} detail <ExternalLink className="h-3 w-3" />
                      </Link>
                    </div>
                  </>
                )}
              </CardContent>
            </Card>

            {/* Model transparency */}
            <Card className="border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900 shadow-sm">
              <CardHeader className="pb-3">
                <CardTitle className="text-sm flex items-center gap-2">
                  <Shield className="h-4 w-4 text-slate-700 dark:text-slate-300" />
                  Model transparency
                </CardTitle>
                <CardDescription className="text-xs">How predictions work — and what this assistant will (and won’t) do.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-3">
                  <h4 className="text-xs font-semibold uppercase tracking-widest text-slate-500 dark:text-slate-400 flex items-center gap-1.5">
                    <Brain className="h-3 w-3" />
                    How predictions work
                  </h4>
                  <ul className="space-y-2 text-sm leading-5 text-slate-600 dark:text-slate-400">
                    <li className="flex gap-2">
                      <span className="mt-1 h-1.5 w-1.5 rounded-full bg-violet-500 shrink-0" />
                      <span>
                        <span className="font-medium text-slate-900 dark:text-white">Ensemble probabilistic model</span> — blend of momentum, mean-reversion, and volume factors; outputs <span className="font-mono text-xs">P(up / neutral / down)</span> + expected return & range per horizon (1D / 1W / 1M).
                      </span>
                    </li>
                    <li className="flex gap-2">
                      <span className="mt-1 h-1.5 w-1.5 rounded-full bg-violet-500 shrink-0" />
                      <span>
                        <span className="font-medium text-slate-900 dark:text-white">Daily inference</span> after close; data cutoff shown on every answer. No intraday re-runs to avoid look-ahead bias.
                      </span>
                    </li>
                    <li className="flex gap-2">
                      <span className="mt-1 h-1.5 w-1.5 rounded-full bg-violet-500 shrink-0" />
                      <span>
                        <span className="font-medium text-slate-900 dark:text-white">Factor-driven</span> — each direction is explained by 3–5 top factors (momentum, RSI, DMA, vol, flow) with citation to the tape or factor table.
                      </span>
                    </li>
                    <li className="flex gap-2">
                      <span className="mt-1 h-1.5 w-1.5 rounded-full bg-violet-500 shrink-0" />
                      <span>
                        <span className="font-medium text-slate-900 dark:text-white">Calibrated confidence</span> 0–100 reflects hit-rate on rolling 6-month backtest for that horizon, not subjective certainty.
                      </span>
                    </li>
                  </ul>
                </div>

                <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 dark:border-slate-800 dark:bg-slate-800/50 space-y-2">
                  <h4 className="text-xs font-semibold text-slate-900 dark:text-white flex items-center gap-1.5">
                    <Network className="h-3 w-3" />
                    Isolated interface
                  </h4>
                  <p className="text-xs leading-5 text-slate-600 dark:text-slate-400">
                    UI never imports an LLM client. A thin adapter satisfies the contract below and is injected server-side.
                  </p>
                  <div className="relative overflow-hidden rounded-lg bg-slate-900 p-3 dark:bg-slate-950">
                    <pre className="overflow-x-auto text-xs leading-5 text-slate-100">
                      <code>{`// lib/research/adapter.ts — future only
export interface ResearchLLMAdapter {
  readonly id: string;              // e.g. "mock" | "openai:gpt-4o"
  readonly isConnected: boolean;    // false in preview
  query(input: ResearchQuery): Promise<ResearchResponse>;
}
// page.tsx consumes only props + adapter via injection`}</code>
                    </pre>
                    <Button
                      variant="secondary"
                      size="sm"
                      className="absolute right-2 top-2 h-7 gap-1 bg-white text-slate-900 hover:bg-slate-100 dark:bg-slate-800 dark:text-white"
                      onClick={handleCopyInterface}
                    >
                      {copiedInterface ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
                      {copiedInterface ? "Copied" : "Copy"}
                    </Button>
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    <Badge variant="outline" className="gap-1 text-xs bg-white dark:bg-slate-900">
                      <FlaskConical className="h-3 w-3" /> No fetch in preview
                    </Badge>
                    <Badge variant="outline" className="gap-1 text-xs bg-white dark:bg-slate-900">
                      <ShieldAlert className="h-3 w-3" /> Deterministic mock
                    </Badge>
                  </div>
                </div>

                <Alert className="bg-amber-50 dark:bg-amber-950/20 border-amber-200 dark:border-amber-900 py-3">
                  <ShieldAlert className="h-4 w-4 text-amber-600 dark:text-amber-400" />
                  <AlertTitle className="text-amber-900 dark:text-amber-200 text-sm">Disclaimer — not investment advice</AlertTitle>
                  <AlertDescription className="text-amber-800/80 dark:text-amber-100/70 leading-5 text-xs">
                    Predictions are probabilistic and based on historical patterns; past performance does not guarantee future results.
                    The assistant will cite sources for every claim and will refuse personalized financial advice. Always consider risk, diversification, fees, taxes, and your objectives — consult a licensed professional before trading.
                    Model version and data cutoff are displayed on every response for auditability.
                  </AlertDescription>
                </Alert>

                <div className="flex flex-wrap items-center gap-2 text-xs">
                  <Link href="/predictions" className="inline-flex items-center gap-1 text-violet-600 hover:underline dark:text-violet-400">
                    <BarChart3 className="h-3 w-3" /> Predictions
                  </Link>
                  <span className="text-slate-300 dark:text-slate-700">•</span>
                  <Link href="/stocks/AAPL?exchange=NASDAQ" className="inline-flex items-center gap-1 text-violet-600 hover:underline dark:text-violet-400">
                    <Search className="h-3 w-3" /> Analyze AAPL
                  </Link>
                  <span className="text-slate-300 dark:text-slate-700">•</span>
                  <Link href="/screener" className="inline-flex items-center gap-1 text-violet-600 hover:underline dark:text-violet-400">
                    <Layers className="h-3 w-3" /> Screener
                  </Link>
                </div>
              </CardContent>
            </Card>
          </div>
        </div>

        {/* Footer meta */}
        <div className="rounded-xl border border-slate-200 bg-white px-4 py-3 text-xs leading-5 text-slate-600 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
          <span className="inline-flex items-center gap-1.5">
            <Info className="h-3 w-3" />
            Research preview — UI scaffold only. No LLM traffic.
          </span>
          <span className="text-muted-foreground">
            Contract: <code className="rounded bg-slate-100 px-1 py-0.5 font-mono text-xs dark:bg-slate-800">ResearchLLMAdapter</code> • Route: <code className="rounded bg-slate-100 px-1 py-0.5 font-mono text-xs dark:bg-slate-800">/research</code> • Client component • Tailwind + shadcn
          </span>
        </div>
      </div>
    </div>
  );
}

// Local helper for disabled state icon
function CircleOff({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}>
      <circle cx="12" cy="12" r="10" />
      <path d="m4.93 4.93 14.14 14.14" />
    </svg>
  );
}
