import { useEffect, useState } from "react";
import { waitForBackend } from "./api/backend";
import MainApp from "./MainApp";
import { LoadingPage } from "./components/loading/LoadingPage";
import { API_BASE } from "./api/config";

export const MINIMUM_LOADING_MS = 5000;

export default function App() {
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [attempt, setAttempt] = useState(0);
  const [error, setError] = useState('');

  useEffect(() => {
    setStatus("loading");
    setError('');
    const controller = new AbortController();
    let delayTimer: ReturnType<typeof setTimeout> | undefined;
    const minimumDisplay = new Promise<void>(resolve => {
      delayTimer = setTimeout(resolve, MINIMUM_LOADING_MS);
    });
    // The visual introduction and API readiness run concurrently.
    Promise.all([waitForBackend(30000, controller.signal), minimumDisplay])
      .then(() => { if (!controller.signal.aborted) setStatus("ready"); })
      .catch((error) => { if (!controller.signal.aborted) { setError(error.message); setStatus("error"); } });
    return () => {
      controller.abort();
      clearTimeout(delayTimer);
    };
  }, [attempt]);

  if (status !== "ready") return <LoadingPage
    error={status === "error" ? error : undefined}
    apiBase={API_BASE}
    onRetry={() => setAttempt(value => value + 1)}
  />;
  return <MainApp />;
}
