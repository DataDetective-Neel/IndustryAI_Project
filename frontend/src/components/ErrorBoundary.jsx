import React from "react";

export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }
  static getDerivedStateFromError(error) { return { error }; }
  componentDidCatch(error, info) { console.error("AOI interface failure", error, info); }
  render() {
    if (!this.state.error) return this.props.children;
    return <main className="fatal-error" role="alert"><section><span>AOI console recovery</span>
      <h1>This workspace could not render.</h1><p>{this.state.error.message || "Unexpected interface error."}</p>
      <button onClick={() => window.location.reload()}>Reload workspace</button></section></main>;
  }
}
