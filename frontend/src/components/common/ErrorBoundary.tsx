import { Component, type ErrorInfo, type ReactNode } from "react";

import ErrorScreen from "@/components/common/ErrorScreen";

interface Props {
  children: ReactNode;
  /** Custom fallback (default: the full-screen ErrorScreen). */
  fallback?: (error: Error, retry: () => void) => ReactNode;
}

interface State {
  error: Error | null;
}

export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Unhandled render error:", error, info.componentStack);
  }

  render() {
    if (this.state.error) {
      if (this.props.fallback) return this.props.fallback(this.state.error, () => this.setState({ error: null }));
      return (
        <ErrorScreen
          message={this.state.error.message || "Произошла непредвиденная ошибка"}
          onRetry={() => this.setState({ error: null })}
        />
      );
    }
    return this.props.children;
  }
}
