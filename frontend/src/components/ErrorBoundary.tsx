import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
}
interface State {
  error: Error | null;
}

/**
 * Top-level safety net. A render error anywhere in the tree would otherwise
 * unmount the whole app to a blank white screen (React has no built-in
 * recovery). This catches it and shows an inline, recoverable message instead.
 */
export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // Surface it for debugging; the inline UI shows the message to the user.
    console.error("Uncaught render error:", error, info.componentStack);
  }

  render() {
    if (this.state.error) {
      return (
        <div style={{ padding: "32px 40px", fontFamily: "system-ui, sans-serif", maxWidth: 760 }}>
          <h2 style={{ marginBottom: 8 }}>Something went wrong displaying this view.</h2>
          <p style={{ color: "#555", marginTop: 0 }}>
            The rest of the app is fine — this panel hit an unexpected error.
          </p>
          <pre
            style={{
              whiteSpace: "pre-wrap", background: "#faf3f1", border: "1px solid #e3b9af",
              color: "#b3261e", padding: "10px 12px", borderRadius: 4, fontSize: 13,
            }}
          >
            {this.state.error.message}
          </pre>
          <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
            <button onClick={() => this.setState({ error: null })}>Try again</button>
            <button onClick={() => window.location.reload()}>Reload app</button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
