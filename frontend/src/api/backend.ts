// src/api/backend.ts
import { API_BASE } from "./config";

export async function waitForBackend(timeoutMs = 30000) {
  const start = Date.now();
  const healthBase = API_BASE.replace(/\/api\/?$/, "");
  while (Date.now() - start < timeoutMs) {
    try {
      const r = await fetch(`${healthBase}/health`);
      if (r.ok) return;
    } catch {}
    await new Promise((r) => setTimeout(r, 300));
  }
  throw new Error("Backend did not start");
}
