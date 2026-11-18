import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ThemeProvider } from "@/components/providers/theme-provider";
import { Header } from "@/components/layout/Header";
import { ErrorBoundary } from "@/components/error-boundary";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });

export const metadata: Metadata = {
  title: "StockAI - Probabilistic Stock Intelligence",
  description: "Professional AI-powered stock market analysis and probabilistic prediction platform",
  keywords: ["stocks", "trading", "predictions", "AI", "machine learning", "backtesting", "screener"],
  authors: [{ name: "StockAI" }],
  openGraph: {
    title: "StockAI - Probabilistic Stock Intelligence",
    description: "Professional AI-powered stock market analysis platform",
    type: "website",
  },
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "white" },
    { media: "(prefers-color-scheme: dark)", color: "#0f172a" },
  ],
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={`${inter.variable} font-sans antialiased bg-white dark:bg-slate-950 text-slate-900 dark:text-slate-100`}>
        <ThemeProvider
          attribute="class"
          defaultTheme="system"
          enableSystem
          disableTransitionOnChange
        >
          <TooltipProvider>
            <Header />
            <main className="min-h-screen">
              <ErrorBoundary>{children}</ErrorBoundary>
            </main>
          </TooltipProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}