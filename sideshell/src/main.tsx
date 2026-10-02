import ReactDOM from "react-dom/client";
import App from "./App";
import "./styles.css";

// StrictMode is intentionally omitted: double-invoked effects would spawn
// duplicate PTY sessions in development. Strict-mode invariants are covered
// by tsc + integration tests instead.
ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <App />
);
