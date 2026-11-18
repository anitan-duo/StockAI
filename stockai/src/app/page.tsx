import type { Metadata } from "next";
import Link from "next/link";
import {
  ArrowRight,
  ArrowUpRight,
  BarChart3,
  Binary,
  Blocks,
  BrainCircuit,
  ChevronRight,
  Database,
  Eye,
  FlaskConical,
  Layers,
  LineChart,
  Scale,
  ShieldCheck,
  Target,
  Timer,
  TrendingUp,
  Activity,
  Search,
  BookOpen,
  AlertTriangle,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";

export const metadata: Metadata = {
  title: "StockAI — Probabilistic Stock Intelligence",
  description:
    "StockAI analyzes market data and provides calibrated probabilistic forecasts across global markets. Not predictions of certainty — transparent, explainable, and tracked over time.",
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function MarketCoverageCard({
  region,
  code,
  exchanges,
  description,
}: {
  region: string;
  code: string;
  exchanges: string[];
  description: string;
}) {
  return (
    <Card className="bg-card border-border/60 hover:border-border transition-colors">
      <CardHeader className="pb-3">
        <div className="flex items-center gap-3">
          <span className="rounded-md border border-border bg-muted px-2 py-1 font-mono text-xs font-bold" aria-hidden>
            {code}
          </span>
          <CardTitle className="text-[15px] font-semibold tracking-tight">{region}</CardTitle>
        </div>
        <CardDescription className="text-[13px] leading-relaxed pt-1">{description}</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="flex flex-wrap gap-1.5">
          {exchanges.map((ex) => (
            <span
              key={ex}
              className="inline-flex items-center rounded-md border border-border bg-muted/50 px-2 py-1 text-xs font-medium tracking-wide text-muted-foreground"
            >
              {ex}
            </span>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

function FeatureCard({
  icon: Icon,
  title,
  description,
}: {
  icon: React.ElementType;
  title: string;
  description: string;
}) {
  return (
    <Card className="group border-border/60 bg-card hover:bg-muted/20 transition-colors">
      <CardHeader className="pb-3">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg border border-border bg-muted/50 text-muted-foreground group-hover:text-foreground group-hover:border-border transition-colors">
          <Icon className="h-[18px] w-[18px]" />
        </div>
        <CardTitle className="text-[15px] font-semibold tracking-tight pt-3">{title}</CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-[13.5px] leading-6 text-muted-foreground">{description}</p>
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function Home() {
  return (
    <div className="flex flex-col bg-white dark:bg-slate-950">
      {/* ===================== HERO ===================== */}
      <section className="relative overflow-hidden border-b border-slate-200 dark:border-slate-800">
        {/* subtle grid + gradient */}
        <div className="absolute inset-0 bg-[linear-gradient(to_right,#8080800a_1px,transparent_1px),linear-gradient(to_bottom,#8080800a_1px,transparent_1px)] bg-[size:32px_32px]" />
        <div className="absolute inset-0 bg-gradient-to-b from-white via-transparent to-white dark:from-slate-950 dark:via-transparent dark:to-slate-950" />
        <div className="absolute -top-24 right-0 h-[420px] w-[600px] rounded-full bg-blue-500/5 blur-3xl dark:bg-blue-500/10" />
        <div className="absolute -bottom-24 left-0 h-[360px] w-[520px] rounded-full bg-slate-200/60 blur-3xl dark:bg-slate-800/40" />

        <div className="relative mx-auto max-w-[1160px] px-6 lg:px-8">
          <div className="grid gap-10 py-12 md:py-16 lg:grid-cols-[1.15fr_0.95fr] lg:items-center lg:py-20">
            {/* Left */}
            <div className="flex flex-col">
              <div className="inline-flex items-center gap-2 self-start rounded-full border border-slate-200 bg-white px-3 py-1 text-xs font-medium text-slate-600 shadow-sm dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300">
                <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" aria-hidden />
                Live market coverage — NSE • NASDAQ • XETRA
                <ChevronRight className="h-3 w-3 text-slate-400" />
              </div>

              <h1 className="mt-6 text-[34px] font-semibold tracking-[-0.03em] leading-[1.05] text-slate-900 dark:text-white sm:text-[42px] lg:text-[48px]">
                Probabilistic
                <br />
                <span className="text-slate-900 dark:text-white">stock intelligence.</span>
              </h1>

              <p className="mt-5 max-w-[560px] text-[15.5px] leading-7 text-slate-600 dark:text-slate-300">
                StockAI analyzes market data and provides
                <span className="font-medium text-slate-900 dark:text-white"> probabilistic forecasts</span> — not
                certainties. Calibrated probabilities, model explanations, and auditable outcome tracking in one
                professional workspace.
              </p>

              <div className="mt-8 flex flex-col gap-3 sm:flex-row">
                <Button asChild size="lg" className="h-11 px-6 text-[14px] font-medium shadow-sm">
                  <Link href="/markets">
                    Explore markets
                    <ArrowRight className="h-4 w-4" />
                  </Link>
                </Button>
                <Button
                  asChild
                  variant="outline"
                  size="lg"
                  className="h-11 px-6 text-[14px] font-medium bg-white dark:bg-slate-900"
                >
                  <Link href="/predictions">
                    View predictions
                    <LineChart className="h-4 w-4" />
                  </Link>
                </Button>
              </div>

              <div className="mt-6 flex flex-wrap items-center gap-x-4 gap-y-2 text-xs leading-5 text-slate-500 dark:text-slate-400">
                <span className="inline-flex items-center gap-1.5">
                  <ShieldCheck className="h-3.5 w-3.5" />
                  No accuracy guarantees
                </span>
                <span className="hidden h-3 w-px bg-slate-200 dark:bg-slate-700 sm:block" />
                <span className="inline-flex items-center gap-1.5">
                  <Scale className="h-3.5 w-3.5" />
                  Past performance ≠ future results
                </span>
                <span className="hidden h-3 w-px bg-slate-200 dark:bg-slate-700 sm:block" />
                <span className="inline-flex items-center gap-1.5">
                  <Eye className="h-3.5 w-3.5" />
                  Explainable forecasts
                </span>
              </div>

              <p className="mt-4 max-w-[560px] text-xs leading-5 text-slate-500 dark:text-slate-400">
                For informational purposes only. Not investment advice.{" "}
                <Link href="/research" className="underline underline-offset-4 hover:text-slate-700 dark:hover:text-slate-200">
                  Read our methodology
                </Link>
                .
              </p>
            </div>

            {/* Right — Example prediction preview */}
            <div className="relative lg:pl-6">
              {/* decorative accent */}
              <div className="absolute -inset-3 rounded-[20px] bg-gradient-to-br from-slate-100 to-slate-50 dark:from-slate-900 dark:to-slate-800/50 -z-10 hidden lg:block" />
              <Card className="overflow-hidden border-slate-200 bg-white shadow-[0_8px_40px_-16px_rgba(0,0,0,0.12)] dark:border-slate-800 dark:bg-slate-900 dark:shadow-none">
                <CardHeader className="pb-3">
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <Badge variant="secondary" className="rounded-md bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950/40 dark:text-amber-300 dark:border-amber-900 text-[11px] font-semibold tracking-wide">
                        EXAMPLE
                      </Badge>
                      <span className="text-xs text-muted-foreground">Illustrative format — not live data</span>
                    </div>
                    <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
                      <Timer className="h-3.5 w-3.5" />
                      5D horizon
                    </span>
                  </div>

                  <div className="mt-4 flex items-start justify-between gap-4">
                    <div>
                      <div className="flex items-center gap-2">
                        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-slate-900 text-white text-sm font-bold dark:bg-white dark:text-slate-900">
                          A
                        </div>
                        <div>
                          <div className="flex items-baseline gap-1.5">
                            <span className="text-[15px] font-semibold tracking-tight">AAPL</span>
                            <span className="text-xs text-muted-foreground">• Apple Inc.</span>
                          </div>
                          <div className="text-xs text-muted-foreground">NASDAQ • USD • 15 min delay</div>
                        </div>
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-semibold text-emerald-700 ring-1 ring-emerald-200 dark:bg-emerald-950/30 dark:text-emerald-300 dark:ring-emerald-900">
                        <TrendingUp className="h-3.5 w-3.5" />
                        UP 64%
                      </div>
                      <div className="mt-1 text-xs text-muted-foreground tabular-nums">P(neutral) 18% • P(down) 18%</div>
                    </div>
                  </div>
                </CardHeader>

                <CardContent className="space-y-4">
                  {/* Probability bars */}
                  <div className="space-y-3 rounded-lg border border-slate-100 bg-slate-50/70 p-3 dark:border-slate-800 dark:bg-slate-800/40">
                    {[
                      { label: "UP", value: 64, color: "bg-emerald-500", text: "text-emerald-600 dark:text-emerald-400" },
                      { label: "NEUTRAL", value: 18, color: "bg-amber-500", text: "text-amber-600 dark:text-amber-400" },
                      { label: "DOWN", value: 18, color: "bg-red-500", text: "text-red-600 dark:text-red-400" },
                    ].map((row) => (
                      <div key={row.label} className="space-y-1.5">
                        <div className="flex items-center justify-between text-xs">
                          <span className="font-medium text-slate-700 dark:text-slate-300">{row.label}</span>
                          <span className={`font-semibold tabular-nums ${row.text}`}>{row.value}%</span>
                        </div>
                        <div className="h-1.5 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700">
                          <div
                            className={`h-full rounded-full ${row.color}`}
                            style={{ width: `${row.value}%` }}
                          />
                        </div>
                      </div>
                    ))}
                    <div className="flex items-center justify-between pt-1 text-[11px] text-muted-foreground">
                      <span>Calibrated probabilities • sum = 100%</span>
                      <span className="tabular-nums">Conf: medium</span>
                    </div>
                  </div>

                  <div className="grid grid-cols-3 gap-3 text-center">
                    <div className="rounded-lg border border-slate-200 bg-white px-2 py-2.5 dark:border-slate-800 dark:bg-slate-900">
                      <div className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">Expected return</div>
                      <div className="mt-0.5 text-sm font-semibold tabular-nums text-emerald-600 dark:text-emerald-400">+1.2%</div>
                    </div>
                    <div className="rounded-lg border border-slate-200 bg-white px-2 py-2.5 dark:border-slate-800 dark:bg-slate-900">
                      <div className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">Horizon</div>
                      <div className="mt-0.5 text-sm font-semibold tabular-nums">5 days</div>
                    </div>
                    <div className="rounded-lg border border-slate-200 bg-white px-2 py-2.5 dark:border-slate-800 dark:bg-slate-900">
                      <div className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">Updated</div>
                      <div className="mt-0.5 text-sm font-semibold tabular-nums">Today 09:15</div>
                    </div>
                  </div>

                  <div className="rounded-lg bg-slate-900 px-3 py-2.5 text-xs leading-5 text-slate-300 dark:bg-slate-800">
                    <span className="font-medium text-white">Why this view:</span> momentum + volatility compression and
                    positive breadth.{" "}
                    <span className="text-slate-400">Explanation is illustrative — see live explanation for details.</span>
                  </div>

                  <div className="flex items-center justify-between pt-1">
                    <Link
                      href="/predictions"
                      className="inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline underline-offset-4"
                    >
                      View live predictions
                      <ArrowUpRight className="h-3.5 w-3.5" />
                    </Link>
                    <span className="text-xs text-muted-foreground">Not investment advice</span>
                  </div>
                </CardContent>
              </Card>

              <div className="mt-3 flex items-center justify-center gap-2 text-xs text-slate-500 dark:text-slate-400">
                <AlertTriangle className="h-3.5 w-3.5" />
                Example only. Real forecasts update with market data.
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ===================== TRUST BAR ===================== */}
      <section className="border-b border-slate-200 bg-slate-50/60 dark:border-slate-800 dark:bg-slate-900/40">
        <div className="mx-auto max-w-[1160px] px-6 lg:px-8">
          <div className="flex flex-col gap-4 py-6 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-xs font-medium uppercase tracking-widest text-slate-500 dark:text-slate-400">
              Built for disciplined analysis
            </p>
            <div className="flex flex-wrap items-center gap-6 text-sm text-slate-600 dark:text-slate-300">
              <span className="inline-flex items-center gap-2">
                <span className="h-1.5 w-1.5 rounded-full bg-slate-400" />
                No hype • No “99% accuracy” claims
              </span>
              <span className="inline-flex items-center gap-2">
                <span className="h-1.5 w-1.5 rounded-full bg-slate-400" />
                Versioned models
              </span>
              <span className="inline-flex items-center gap-2">
                <span className="h-1.5 w-1.5 rounded-full bg-slate-400" />
                Audited outcomes
              </span>
            </div>
          </div>
        </div>
      </section>

      {/* ===================== FEATURES ===================== */}
      <section className="mx-auto w-full max-w-[1160px] px-6 py-14 lg:px-8 lg:py-20">
        <div className="mx-auto max-w-2xl text-center">
          <Badge variant="outline" className="rounded-full border-slate-200 bg-white text-slate-600 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300">
            Platform overview
          </Badge>
          <h2 className="mt-3 text-2xl font-semibold tracking-tight text-slate-900 dark:text-white sm:text-3xl">
            Everything around the forecast — not just a number.
          </h2>
          <p className="mt-3 text-sm leading-6 text-muted-foreground">
            Forecasts are useful only with context. StockAI pairs every probability with data lineage, drivers, and
            subsequent outcomes.
          </p>
        </div>

        <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <FeatureCard
            icon={Database}
            title="Market Data"
            description="Clean OHLCV, corporate actions, and market state from primary exchanges — with delays disclosed and lineage preserved."
          />
          <FeatureCard
            icon={Binary}
            title="Feature Engineering"
            description="Momentum, volatility, volume, and breadth transforms computed deterministically and versioned for reproducibility."
          />
          <FeatureCard
            icon={Layers}
            title="Ensemble Models"
            description="Diverse models combined — no single model dominates. Aggregation reduces variance versus any individual learner."
          />
          <FeatureCard
            icon={Target}
            title="Calibrated Probabilities"
            description="Raw scores mapped to calibrated P(UP) / P(NEUTRAL) / P(DOWN). Probabilities sum to 100% and reflect uncertainty."
          />
          <FeatureCard
            icon={Eye}
            title="Explainability"
            description="Every prediction links to top drivers and recent context — so you can interrogate why, not just what."
          />
          <FeatureCard
            icon={Activity}
            title="Outcome Tracking"
            description="Forecasts are scored against realized outcomes. No silent disappearances — write-once, evaluate openly."
          />
        </div>
      </section>

      {/* ===================== HOW IT WORKS ===================== */}
      <section className="border-y border-slate-200 bg-slate-50/60 dark:border-slate-800 dark:bg-slate-900/30">
        <div className="mx-auto max-w-[1160px] px-6 py-14 lg:px-8 lg:py-16">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <h2 className="text-2xl font-semibold tracking-tight text-slate-900 dark:text-white">How it works</h2>
              <p className="mt-2 max-w-[560px] text-sm leading-6 text-muted-foreground">
                A transparent, end-to-end pipeline. Each step is observable, versioned, and auditable — from tick to
                tracked outcome.
              </p>
            </div>
            <Link href="/research" className="inline-flex items-center gap-1 text-sm font-medium text-primary hover:underline underline-offset-4">
              Methodology & limitations
              <ArrowRight className="h-4 w-4" />
            </Link>
          </div>

          {/* Desktop: horizontal flow. Mobile: vertical */}
          <div className="mt-10">
            {/* Desktop */}
            <div className="hidden lg:block">
              <div className="relative">
                {/* connecting line */}
                <div className="absolute left-0 right-0 top-[30px] h-px bg-slate-200 dark:bg-slate-800" aria-hidden />
                <div className="grid grid-cols-8 gap-2">
                  {[
                    { icon: Database, label: "Market Data", sub: "OHLCV + state" },
                    { icon: Binary, label: "Features", sub: "Transforms" },
                    { icon: BrainCircuit, label: "Models", sub: "Diverse learners" },
                    { icon: Blocks, label: "Ensemble", sub: "Aggregation" },
                    { icon: Scale, label: "Calibration", sub: "Platt / isotonic" },
                    { icon: Target, label: "Prediction", sub: "P(UP/DOWN)" },
                    { icon: Eye, label: "Explanation", sub: "Drivers + context" },
                    { icon: Activity, label: "Outcome", sub: "Realized vs forecast" },
                  ].map((step) => (
                    <div key={step.label} className="relative flex flex-col items-center text-center">
                      <div className="flex h-[60px] w-[60px] items-center justify-center rounded-xl border border-slate-200 bg-white text-slate-700 shadow-sm dark:border-slate-800 dark:bg-slate-900 dark:text-slate-200">
                        <step.icon className="h-5 w-5" />
                      </div>
                      <div className="mt-3 text-[13px] font-semibold tracking-tight text-slate-900 dark:text-white">
                        {step.label}
                      </div>
                      <div className="text-xs text-muted-foreground">{step.sub}</div>
                    </div>
                  ))}
                </div>
              </div>
              <p className="mt-8 text-center text-xs leading-5 text-slate-500 dark:text-slate-400">
                Data → features → models → ensemble → calibration → prediction → explanation → outcome tracking.
                Every run is logged and reproducible.
              </p>
            </div>

            {/* Mobile / Tablet */}
            <div className="grid gap-3 lg:hidden">
              {[
                { icon: Database, label: "Market Data", desc: "Exchange-sourced OHLCV, corporate actions, and market status with disclosed delays." },
                { icon: Binary, label: "Features", desc: "Deterministic transforms for momentum, volatility, volume and breadth." },
                { icon: BrainCircuit, label: "Models", desc: "Multiple model families — no single point of failure." },
                { icon: Blocks, label: "Ensemble", desc: "Weighted aggregation to reduce variance and overconfidence." },
                { icon: Scale, label: "Calibration", desc: "Probability calibration so 60% means ~60% over many trials." },
                { icon: Target, label: "Prediction", desc: "P(UP) / P(NEUTRAL) / P(DOWN) with expected return and confidence tier." },
                { icon: Eye, label: "Explanation", desc: "Top drivers, context, and recent regime — not a black box." },
                { icon: Activity, label: "Outcome Tracking", desc: "Forecasts tracked vs realized outcomes — successes and failures visible." },
              ].map((step, i) => (
                <div key={step.label} className="flex gap-4 rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
                  <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-slate-900 text-white dark:bg-white dark:text-slate-900">
                    <step.icon className="h-5 w-5" />
                  </div>
                  <div className="min-w-0">
                    <div className="flex items-baseline gap-2">
                      <span className="text-sm font-semibold">{step.label}</span>
                      <span className="text-xs text-muted-foreground">Step {i + 1}</span>
                    </div>
                    <p className="mt-1 text-sm leading-5 text-muted-foreground">{step.desc}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* ===================== MARKET COVERAGE ===================== */}
      <section className="mx-auto w-full max-w-[1160px] px-6 py-14 lg:px-8 lg:py-20">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h2 className="text-2xl font-semibold tracking-tight text-slate-900 dark:text-white">Market coverage</h2>
            <p className="mt-2 max-w-[560px] text-sm leading-6 text-muted-foreground">
              One model framework, applied consistently. Coverage starts with the most liquid venues — expansion is
              explicit, not assumed.
            </p>
          </div>
          <Button asChild variant="outline" className="self-start sm:self-auto">
            <Link href="/markets">
              <Search className="h-4 w-4" />
              Browse all markets
            </Link>
          </Button>
        </div>

        <div className="mt-8 grid gap-4 md:grid-cols-3">
          <MarketCoverageCard
            region="India"
            code="IN"
            exchanges={["NSE", "BSE"]}
            description="Large- and mid-cap coverage from NSE and BSE. Corporate actions adjusted. Data in IST."
          />
          <MarketCoverageCard
            region="United States"
            code="US"
            exchanges={["NYSE", "NASDAQ"]}
            description="US equities across NYSE and NASDAQ. Primary source with disclosed delay tiers."
          />
          <MarketCoverageCard
            region="Europe"
            code="EU"
            exchanges={["XETRA", "LSE", "Euronext"]}
            description="Core European venues: XETRA, London Stock Exchange, and Euronext (Paris/Amsterdam)."
          />
        </div>

        <div className="mt-6 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-xs leading-5 text-slate-600 dark:border-slate-800 dark:bg-slate-900/50 dark:text-slate-300">
          <span className="font-medium text-slate-900 dark:text-white">Data note:</span> Prices may be delayed per
          exchange policy. Market status (open / closed) is shown in-context. We disclose source and timestamp on every
          prediction.
        </div>
      </section>

      {/* ===================== BACKTESTING ===================== */}
      <section className="border-y border-slate-200 bg-slate-950 text-slate-100 dark:border-slate-800 dark:bg-slate-900">
        <div className="mx-auto max-w-[1160px] px-6 py-14 lg:px-8 lg:py-16">
          <div className="grid gap-10 lg:grid-cols-[1.1fr_0.9fr] lg:items-center">
            <div>
              <div className="inline-flex items-center gap-2 rounded-full border border-slate-800 bg-slate-900 px-3 py-1 text-xs font-medium text-slate-300">
                <FlaskConical className="h-3.5 w-3.5" />
                Evaluation, not marketing
              </div>
              <h2 className="mt-4 text-2xl font-semibold tracking-tight sm:text-3xl">Backtested with walk-forward discipline.</h2>
              <p className="mt-3 text-sm leading-6 text-slate-400">
                We use walk-forward validation: models are trained only on data available before each forecast point —
                then tested on strictly out-of-sample data. No look-ahead. No peeking.
              </p>

              <ul className="mt-6 space-y-3 text-sm leading-6 text-slate-300">
                <li className="flex gap-3">
                  <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-slate-500" />
                  <span>
                    <span className="font-medium text-white">Walk-forward splits</span> — expanding windows that mirror
                    how the model would have run historically.
                  </span>
                </li>
                <li className="flex gap-3">
                  <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-slate-500" />
                  <span>
                    <span className="font-medium text-white">Transaction costs considered</span> — evaluation can include
                    costs and slippage, disclosed per run.
                  </span>
                </li>
                <li className="flex gap-3">
                  <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-slate-500" />
                  <span>
                    <span className="font-medium text-white">Out-of-sample only</span> — in-sample fit is never reported as
                    performance.
                  </span>
                </li>
              </ul>

              <div className="mt-6 rounded-lg border border-amber-900/50 bg-amber-950/30 px-4 py-3">
                <p className="text-xs font-semibold uppercase tracking-wide text-amber-300">No guarantees</p>
                <p className="mt-1 text-sm leading-5 text-amber-100/80">
                  Backtests are historical simulations. They do not predict future returns. Markets change — past
                  performance is not indicative of future results.
                </p>
              </div>

              <div className="mt-6">
                <Button asChild variant="secondary" className="bg-white text-slate-900 hover:bg-slate-100">
                  <Link href="/backtesting">
                    Explore backtests
                    <ArrowRight className="h-4 w-4" />
                  </Link>
                </Button>
              </div>
            </div>

            <Card className="border-slate-800 bg-slate-900/60 backdrop-blur">
              <CardHeader>
                <CardTitle className="text-sm font-semibold text-white">What walk-forward looks like</CardTitle>
                <CardDescription className="text-slate-400 text-xs leading-5">
                  Illustrative schematic — not a performance chart.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-5">
                {/* schematic */}
                <div className="space-y-3">
                  {[
                    { label: "Fold 1", train: "Train [— — —]", test: "Test [—]" },
                    { label: "Fold 2", train: "Train [— — — —]", test: "Test [—]" },
                    { label: "Fold 3", train: "Train [— — — — —]", test: "Test [—]" },
                    { label: "Fold 4", train: "Train [— — — — — —]", test: "Test [—]" },
                  ].map((fold) => (
                    <div key={fold.label} className="flex items-center gap-3 text-xs">
                      <span className="w-12 shrink-0 font-medium text-slate-400">{fold.label}</span>
                      <div className="flex flex-1 items-center gap-1.5">
                        <div className="flex-1 rounded bg-slate-800 px-2 py-1.5 text-center font-mono text-[11px] tracking-wide text-slate-300">
                          {fold.train}
                        </div>
                        <ChevronRight className="h-3.5 w-3.5 shrink-0 text-slate-600" />
                        <div className="w-[72px] shrink-0 rounded bg-blue-600 px-2 py-1.5 text-center font-mono text-[11px] font-medium tracking-wide text-white">
                          {fold.test}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
                <Separator className="bg-slate-800" />
                <div className="grid grid-cols-3 gap-3 text-center">
                  <div className="rounded-lg border border-slate-800 bg-slate-900 px-3 py-3">
                    <div className="text-xs text-slate-400">Folds</div>
                    <div className="mt-1 text-sm font-semibold text-white">Rolling</div>
                  </div>
                  <div className="rounded-lg border border-slate-800 bg-slate-900 px-3 py-3">
                    <div className="text-xs text-slate-400">Leakage</div>
                    <div className="mt-1 text-sm font-semibold text-emerald-300">None</div>
                  </div>
                  <div className="rounded-lg border border-slate-800 bg-slate-900 px-3 py-3">
                    <div className="text-xs text-slate-400">Costs</div>
                    <div className="mt-1 text-sm font-semibold text-white">Disclosed</div>
                  </div>
                </div>
                <p className="text-xs leading-5 text-slate-500">
                  Every backtest run logs train / test boundaries, parameters, and universe — reproducible from the
                  research workspace.
                </p>
              </CardContent>
            </Card>
          </div>
        </div>
      </section>

      {/* ===================== TRANSPARENCY ===================== */}
      <section className="mx-auto w-full max-w-[1160px] px-6 py-14 lg:px-8 lg:py-16">
        <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-800 dark:bg-slate-900 sm:p-8">
          <div className="grid gap-8 lg:grid-cols-[1.15fr_0.85fr] lg:items-center">
            <div>
              <div className="inline-flex items-center gap-2 rounded-full bg-slate-900 px-3 py-1 text-xs font-medium text-white dark:bg-white dark:text-slate-900">
                <BookOpen className="h-3.5 w-3.5" />
                Transparency promise
              </div>
              <h2 className="mt-4 text-2xl font-semibold tracking-tight text-slate-900 dark:text-white">
                Predictions can be wrong. We show it.
              </h2>
              <p className="mt-3 text-sm leading-6 text-muted-foreground">
                A probabilistic forecast is a statement of uncertainty — not a guarantee of direction. StockAI keeps
                every forecast, scores it against reality, and makes the distribution of outcomes inspectable.
              </p>
              <ul className="mt-5 space-y-2 text-sm leading-6 text-slate-700 dark:text-slate-300">
                <li className="flex gap-2">
                  <span className="text-slate-400">—</span> Probabilities are calibrated, not certainties. A 64% UP still
                  means ~36% not-UP.
                </li>
                <li className="flex gap-2">
                  <span className="text-slate-400">—</span> Past performance does not guarantee future results.
                </li>
                <li className="flex gap-2">
                  <span className="text-slate-400">—</span> This platform is for research and education, not investment
                  advice.
                </li>
              </ul>
            </div>

            <Card className="border-slate-200 bg-slate-50 dark:border-slate-800 dark:bg-slate-800/50">
              <CardHeader className="pb-3">
                <CardTitle className="text-sm">How to interpret a forecast</CardTitle>
                <CardDescription className="text-xs leading-5">Read probabilities as frequencies, not promises.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="rounded-lg border border-slate-200 bg-white p-3 dark:border-slate-700 dark:bg-slate-900">
                  <div className="text-xs font-medium text-slate-700 dark:text-slate-300">If many forecasts say “UP 64%”</div>
                  <div className="mt-1 text-sm leading-5 text-muted-foreground">
                    In a well-calibrated system, roughly 64 out of 100 such forecasts should see an upward move — and
                    about 36 should not. Single outcomes prove little; distributions matter.
                  </div>
                </div>
                <div className="flex flex-col gap-2">
                  <Button asChild className="w-full">
                    <Link href="/research">
                      <BookOpen className="h-4 w-4" />
                      Read research & disclosures
                    </Link>
                  </Button>
                  <Button asChild variant="outline" className="w-full bg-white dark:bg-slate-900">
                    <Link href="/predictions">View outcome-tracked predictions</Link>
                  </Button>
                </div>
                <p className="text-xs leading-5 text-slate-500 dark:text-slate-400">
                  Questions? See <Link href="/research" className="underline underline-offset-4">/research</Link> for
                  methodology, limitations, and data sources.
                </p>
              </CardContent>
            </Card>
          </div>
        </div>
      </section>

      {/* ===================== FINAL CTA ===================== */}
      <section className="border-t border-slate-200 bg-slate-50/60 dark:border-slate-800 dark:bg-slate-900/30">
        <div className="mx-auto max-w-[1160px] px-6 py-12 lg:px-8 lg:py-14">
          <div className="rounded-2xl bg-slate-900 px-6 py-8 text-white shadow-lg dark:bg-white dark:text-slate-900 sm:px-10 sm:py-10">
            <div className="flex flex-col gap-6 lg:flex-row lg:items-center lg:justify-between">
              <div className="max-w-[560px]">
                <h2 className="text-2xl font-semibold tracking-tight sm:text-3xl">Start with the dashboard.</h2>
                <p className="mt-2 text-sm leading-6 text-slate-300 dark:text-slate-600">
                  Market overview, top probabilistic forecasts, and quick access to screener, watchlist, and backtests —
                  one workspace for disciplined analysis.
                </p>
              </div>
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
                <Button
                  asChild
                  size="lg"
                  className="h-11 bg-white px-6 text-slate-900 hover:bg-slate-100 dark:bg-slate-900 dark:text-white dark:hover:bg-slate-800"
                >
                  <Link href="/dashboard">
                    Explore dashboard
                    <ArrowRight className="h-4 w-4" />
                  </Link>
                </Button>
                <span className="text-center text-xs text-slate-400 dark:text-slate-500 sm:text-left">
                  Takes you to live data.
                  <br />
                  No signup required to browse.
                </span>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ===================== FOOTER ===================== */}
      <footer className="border-t border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-950">
        <div className="mx-auto max-w-[1160px] px-6 py-10 lg:px-8">
          <div className="grid gap-10 sm:grid-cols-2 lg:grid-cols-[1.4fr_0.9fr_0.9fr_0.9fr]">
            <div>
              <Link href="/dashboard" className="inline-flex items-center gap-2 font-bold text-[16px] tracking-tight text-slate-900 dark:text-white">
                <span className="flex h-6 w-6 items-center justify-center rounded bg-slate-900 text-white dark:bg-white dark:text-slate-900">
                  <BarChart3 className="h-3.5 w-3.5" />
                </span>
                StockAI
              </Link>
              <p className="mt-3 max-w-[360px] text-sm leading-6 text-slate-600 dark:text-slate-400">
                Probabilistic stock intelligence for research and education. Calibrated, explainable, and tracked over
                time.
              </p>
              <p className="mt-4 text-xs leading-5 text-slate-500 dark:text-slate-400">
                © {new Date().getFullYear()} StockAI. All rights reserved.
              </p>
            </div>

            <div>
              <h3 className="text-xs font-semibold uppercase tracking-widest text-slate-900 dark:text-white">Platform</h3>
              <ul className="mt-3 space-y-2 text-sm">
                <li>
                  <Link href="/markets" className="text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white">
                    Markets
                  </Link>
                </li>
                <li>
                  <Link href="/predictions" className="text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white">
                    Predictions
                  </Link>
                </li>
                <li>
                  <Link href="/screener" className="text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white">
                    Screener
                  </Link>
                </li>
                <li>
                  <Link href="/watchlist" className="text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white">
                    Watchlist
                  </Link>
                </li>
                <li>
                  <Link href="/backtesting" className="text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white">
                    Backtesting
                  </Link>
                </li>
                <li>
                  <Link href="/dashboard" className="text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white">
                    Dashboard
                  </Link>
                </li>
              </ul>
            </div>

            <div>
              <h3 className="text-xs font-semibold uppercase tracking-widest text-slate-900 dark:text-white">Research</h3>
              <ul className="mt-3 space-y-2 text-sm">
                <li>
                  <Link href="/research" className="text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white">
                    Methodology
                  </Link>
                </li>
                <li>
                  <Link href="/research" className="text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white">
                    Disclosures
                  </Link>
                </li>
                <li>
                  <Link href="/research" className="text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white">
                    Data sources
                  </Link>
                </li>
                <li>
                  <Link href="/research" className="text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white">
                    Limitations
                  </Link>
                </li>
              </ul>
            </div>

            <div>
              <h3 className="text-xs font-semibold uppercase tracking-widest text-slate-900 dark:text-white">Support</h3>
              <ul className="mt-3 space-y-2 text-sm">
                <li>
                  <Link href="/login" className="text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white">
                    Sign in
                  </Link>
                </li>
                <li>
                  <Link href="/signup" className="text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white">
                    Create account
                  </Link>
                </li>
                <li>
                  <Link href="/settings" className="text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white">
                    Settings
                  </Link>
                </li>
              </ul>
            </div>
          </div>

          <Separator className="my-8" />

          <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-4 dark:border-amber-900/50 dark:bg-amber-950/20">
            <p className="text-xs font-semibold uppercase tracking-wide text-amber-800 dark:text-amber-300">Disclaimer</p>
            <p className="mt-1 text-xs leading-5 text-amber-900/80 dark:text-amber-100/70">
              StockAI provides probabilistic forecasts and analytical tools for informational and educational purposes only.
              Nothing on this platform constitutes investment advice, financial advice, trading advice, or a recommendation
              to buy, sell, or hold any security. All investments carry risk of loss. Predictions can be wrong. Past
              performance, backtested results, or historical accuracy do not guarantee future results. You should conduct
              your own research and consult a qualified financial advisor before making investment decisions. Market data
              may be delayed and should be verified with your broker or primary exchange source before trading.
            </p>
          </div>

          <p className="mt-6 text-center text-xs text-slate-500 dark:text-slate-400">
            Built with discipline. No “get-rich-quick” claims. No fake performance marketing.
          </p>
        </div>
      </footer>
    </div>
  );
}
