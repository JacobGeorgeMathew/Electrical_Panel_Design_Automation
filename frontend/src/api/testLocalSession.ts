// Consumer tests establish a real bootstrap before installing workload-specific mocks.
import { vi } from 'vitest';
import { forgetLocalSession, localCredential } from './localSession';

export async function authorizeTestSession() {
  forgetLocalSession();
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({token: 'a'.repeat(64)}))));
  await localCredential(new AbortController().signal);
  vi.unstubAllGlobals();
}
