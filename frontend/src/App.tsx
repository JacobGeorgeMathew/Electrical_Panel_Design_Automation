import { useEffect, useState } from "react";
import { waitForBackend } from "./api/backend";
import MainApp from "./MainApp"; // your current App content, renamed
import { API_BASE } from "./api/config";

export default function App() {
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [attempt, setAttempt] = useState(0);
  const [error, setError] = useState('');

  useEffect(() => {
    setStatus("loading");
    const controller = new AbortController();
    waitForBackend(30000, controller.signal)
      .then(() => setStatus("ready"))
      .catch((error) => { if (!controller.signal.aborted) { setError(error.message); setStatus("error"); } });
    return () => controller.abort();
  }, [attempt]);

  if (status === "loading") return <div className="flex h-dvh items-center justify-center bg-slate-950 text-slate-200">Connecting to the design API…</div>;
  if (status === "error") return (
    <div className="flex h-dvh flex-col items-center justify-center gap-3 bg-slate-950 px-6 text-center text-slate-200">
      <h1 className="text-lg font-semibold">Could not reach the design API</h1>
      <p className="max-w-xl text-sm text-slate-400">{error} Start the required service or apply migrations, then retry. The frontend is configured for <code className="text-slate-300">{API_BASE}</code>.</p>
      <button className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold hover:bg-blue-500" onClick={() => setAttempt((value) => value + 1)}>Retry connection</button>
    </div>
  );
  return <MainApp />;
}
