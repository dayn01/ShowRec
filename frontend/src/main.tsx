import React, { useEffect, useState } from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { WatchedProvider } from "./WatchedContext";
import App from "./App";
import Setup from "./pages/Setup";
import { api } from "./api";
import "./index.css";

const queryClient = new QueryClient();

function Root() {
  const [phase, setPhase] = useState<"loading" | "setup" | "ready">("loading");

  useEffect(() => {
    api.getSetupStatus()
      .then(s => setPhase(s.configured ? "ready" : "setup"))
      // If the status check fails (e.g. older backend), don't lock the user out.
      .catch(() => setPhase("ready"));
  }, []);

  if (phase === "loading") {
    return (
      <div style={{
        minHeight: "100vh", display: "flex", alignItems: "center",
        justifyContent: "center", color: "var(--muted)",
      }}>Loading…</div>
    );
  }

  if (phase === "setup") {
    return <Setup onDone={() => setPhase("ready")} />;
  }

  return (
    <QueryClientProvider client={queryClient}>
      <WatchedProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/*" element={<App />} />
          </Routes>
        </BrowserRouter>
      </WatchedProvider>
    </QueryClientProvider>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <Root />
  </React.StrictMode>
);
