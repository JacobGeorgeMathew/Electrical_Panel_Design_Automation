import { useEffect, useState } from "react";
import { waitForBackend } from "./api/backend";
import MainApp from "./MainApp"; // your current App content, renamed

export default function App() {
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");

  useEffect(() => {
    waitForBackend()
      .then(() => setStatus("ready"))
      .catch(() => setStatus("error"));
  }, []);

  if (status === "loading") return <div>Starting engine…</div>;
  if (status === "error") return <div>Could not start the backend engine.</div>;
  return <MainApp />;
}