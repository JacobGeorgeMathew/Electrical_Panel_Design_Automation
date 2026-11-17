import { invoke, isTauri } from '@tauri-apps/api/core';
import { API_BASE } from './config';

// Runtime memory only: never storage, URLs, VITE_* configuration or console logs.
let token: string | null = null;

export function localApiBase(): string {
  const url = new URL(API_BASE, window.location.href);
  if (!['127.0.0.1', 'localhost', '[::1]'].includes(url.hostname) ||
      !['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash) {
    throw new Error('Only the local application API is supported.');
  }
  return API_BASE.replace(/\/$/, '');
}

export function forgetLocalSession() { token = null; }

export function localCredential(signal: AbortSignal): string | Promise<string> {
  if (token) return token;
  return bootstrap(signal);
}

async function bootstrap(signal: AbortSignal): Promise<string> {
  const headers: Record<string, string> = { 'X-Panel-Bootstrap': '1' };
  if (isTauri()) {
    const launch = await invoke<string | null>('local_session');
    if (launch) headers['X-Panel-Launch'] = launch;
  }
  const response = await fetch(localApiBase() + '/local-session', {
    method: 'POST', headers, signal, credentials: 'omit', cache: 'no-store', redirect: 'error',
  });
  const data = await response.json().catch(() => null);
  if (!response.ok || typeof data?.token !== 'string' || !/^[0-9a-f]{64}$/.test(data.token)) {
    throw new Error('Local session could not be authorized.');
  }
  token = data.token;
  return token!;
}

export async function rotateLocalSession(signal: AbortSignal): Promise<void> {
  const credential = await localCredential(signal);
  const response = await fetch(localApiBase() + '/local-session/rotate', {
    method: 'POST', headers: { 'X-Panel-Session': credential }, signal,
    credentials: 'omit', cache: 'no-store', redirect: 'error',
  });
  token = null;
  const data = await response.json().catch(() => null);
  if (!response.ok || typeof data?.token !== 'string' || !/^[0-9a-f]{64}$/.test(data.token)) {
    throw new Error('Local session rotation failed.');
  }
  token = data.token;
}
