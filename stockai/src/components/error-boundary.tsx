'use client';

import { Component, type ErrorInfo, type ReactNode } from 'react';

type ErrorBoundaryProps = {
  children: ReactNode;
};

type ErrorBoundaryState = {
  error: Error | null;
};

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('[ErrorBoundary] render failed', error, info);
  }

  handleReset = () => {
    this.setState({ error: null });
  };

  render() {
    const { error } = this.state;
    if (error) {
      return (
        <div className="mx-auto flex max-w-[640px] flex-col items-center p-12 text-center">
          <h1 className="text-2xl font-bold">Something failed to render</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            {error.message || 'Unexpected client error.'} No financial data was fabricated — retry to reload live state.
          </p>
          <button
            onClick={this.handleReset}
            className="mt-6 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground"
          >
            Try again
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
