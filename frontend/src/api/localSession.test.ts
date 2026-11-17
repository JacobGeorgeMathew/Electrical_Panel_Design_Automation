import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const tauri = vi.hoisted(() => ({ invoke: vi.fn(), isTauri: vi.fn(() => false) }));
vi.mock('@tauri-apps/api/core', () => tauri);
const first = 'a'.repeat(64), second = 'b'.repeat(64), launch = 'c'.repeat(64);

beforeEach(() => { vi.resetModules(); tauri.isTauri.mockReturnValue(false); tauri.invoke.mockReset(); });
afterEach(() => { vi.unstubAllGlobals(); vi.unstubAllEnvs(); });

describe('local application session', () => {
  it('bootstraps dev requests, preserves headers and keeps credentials in memory', async () => {
    const fetch = vi.fn(async (url: string) => new Response(JSON.stringify(
      url.endsWith('/local-session') ? {token: first} : {saved: true}), {status: 200}));
    vi.stubGlobal('fetch', fetch);
    const storage = vi.spyOn(Storage.prototype, 'setItem');
    const { request } = await import('./client');
    await request('/projects', {method: 'POST', body: '{}', headers: {'Idempotency-Key': 'same-intent'}});
    await request('/projects', {method: 'PATCH', body: '{}'});
    expect(fetch.mock.calls.map(call => call[0]).filter(url => url.endsWith('/local-session'))).toHaveLength(1);
    const options = (fetch.mock.calls[1] as unknown as [string, RequestInit])[1];
    expect(new Headers(options.headers).get('X-Panel-Session')).toBe(first);
    expect(new Headers(options.headers).get('Idempotency-Key')).toBe('same-intent');
    expect(options.credentials).toBe('omit');
    expect(storage).not.toHaveBeenCalled();
    storage.mockRestore();
  });

  it('hands a desktop launch secret only to the bootstrap endpoint', async () => {
    tauri.isTauri.mockReturnValue(true); tauri.invoke.mockResolvedValue(launch);
    const fetch = vi.fn(async (url: string, _options?: RequestInit) => new Response(JSON.stringify(
      url.endsWith('/local-session') ? {token: first} : {})));
    vi.stubGlobal('fetch', fetch);
    const { request } = await import('./client');
    await request('/projects', {method: 'POST'});
    expect(tauri.invoke).toHaveBeenCalledWith('local_session');
    expect(new Headers(fetch.mock.calls[0][1]?.headers).get('X-Panel-Launch')).toBe(launch);
    expect(new Headers(fetch.mock.calls[1][1]?.headers).get('X-Panel-Launch')).toBeNull();
    expect(new Headers(fetch.mock.calls[1][1]?.headers).get('X-Panel-Session')).toBe(first);
    expect(fetch.mock.calls.every(([url]) => !url.includes(launch) && !url.includes(first))).toBe(true);
  });

  it('rotates credentials and sends the replacement on subsequent mutations', async () => {
    const fetch = vi.fn(async (url: string, _options?: RequestInit) => new Response(JSON.stringify(
      url.endsWith('/rotate') ? {token: second} : url.endsWith('/local-session') ? {token: first} : {})));
    vi.stubGlobal('fetch', fetch);
    const { rotateLocalSession } = await import('./localSession');
    await rotateLocalSession(new AbortController().signal);
    const { request } = await import('./client');
    await request('/projects', {method: 'DELETE'});
    expect(new Headers(fetch.mock.calls[1][1]?.headers).get('X-Panel-Session')).toBe(first);
    expect(new Headers(fetch.mock.calls[2][1]?.headers).get('X-Panel-Session')).toBe(second);
  });

  it('forgets rejected credentials, never replays a mutation and hides error bodies', async () => {
    const fetch = vi.fn(async (url: string) => new Response(JSON.stringify(
      url.endsWith('/local-session') ? {token: first} : {error: {message: launch, details: {token: first}}}),
      {status: url.endsWith('/local-session') ? 200 : 401}));
    vi.stubGlobal('fetch', fetch);
    const { request } = await import('./client');
    const error = await request('/projects', {method: 'POST'}).catch(error => error);
    expect(error).toMatchObject({code: 'LOCAL_AUTHORIZATION_FAILED', details: null});
    expect(JSON.stringify(error)).not.toContain(first);
    expect((error as Error).message).not.toContain(launch);
    expect(fetch).toHaveBeenCalledTimes(2);
    await request('/projects', {method: 'POST'}).catch(() => {});
    expect(fetch).toHaveBeenCalledTimes(4);
  });

  it('retains cancellation and refuses to send credentials to a hosted API', async () => {
    vi.stubEnv('VITE_API_BASE', 'https://hosted.example/api');
    const fetch = vi.fn(); vi.stubGlobal('fetch', fetch);
    const { request } = await import('./client');
    await expect(request('/projects', {method: 'POST'})).rejects.toMatchObject({code: 'NETWORK_ERROR'});
    expect(fetch).not.toHaveBeenCalled();
    vi.unstubAllEnvs(); vi.resetModules();
    vi.stubGlobal('fetch', vi.fn((_url, options) => new Promise((_resolve, reject) => {
      options.signal.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')));
    })));
    const { request: timeoutRequest } = await import('./client');
    await expect(timeoutRequest('/projects', {method: 'POST'}, 10)).rejects.toMatchObject({code: 'ABORTED'});
  });
});
