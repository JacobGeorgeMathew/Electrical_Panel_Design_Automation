import {act} from 'react';
import {createRoot, type Root} from 'react-dom/client';
import {afterEach, beforeEach, expect, it, vi} from 'vitest';
const backend = vi.hoisted(() => ({wait: vi.fn()}));
vi.mock('./api/backend', () => ({waitForBackend: backend.wait}));
vi.mock('./MainApp', () => ({default: () => <div data-testid="workspace">Project dashboard</div>}));
import App, {MINIMUM_LOADING_MS} from './App';

(globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;
let host: HTMLDivElement, root: Root;
let resolve: () => void, reject: (error: Error) => void;
beforeEach(() => {
  vi.useFakeTimers();
  host = document.createElement('div'); document.body.append(host); root = createRoot(host);
  backend.wait.mockReset().mockImplementation(() => new Promise<void>((yes, no) => {resolve = yes; reject = no;}));
});
afterEach(() => {act(() => root.unmount()); host.remove(); vi.useRealTimers();});

it('keeps the background and bottom loading bar visible for three seconds even when the API is ready', async () => {
  act(() => root.render(<App />));
  const page = host.querySelector<HTMLElement>('.startup-page')!;
  expect(page.style.backgroundImage).toContain('electrical-loading.jpg');
  expect(host.querySelector('[role="status"]')?.textContent).toContain('Preparing your workspace');
  expect(host.querySelector('[data-testid="workspace"]')).toBeNull();
  expect(host.querySelector('[role="progressbar"]')?.getAttribute('aria-label')).toBe('Workspace startup');
  await act(async () => resolve());
  expect(host.querySelector('[data-testid="workspace"]')).toBeNull();
  await act(async () => { await vi.advanceTimersByTimeAsync(MINIMUM_LOADING_MS - 1); });
  expect(host.querySelector('[data-testid="workspace"]')).toBeNull();
  await act(async () => { await vi.advanceTimersByTimeAsync(1); });
  expect(host.querySelector('[data-testid="workspace"]')).not.toBeNull();
  expect(host.querySelector('.startup-page')).toBeNull();
});

it('retains connection errors and retries without entering the workspace prematurely', async () => {
  act(() => root.render(<App />));
  await act(async () => reject(new Error('PostgreSQL is unavailable.')));
  expect(host.querySelector('[role="alert"]')?.textContent).toContain('PostgreSQL is unavailable');
  expect(host.querySelector('.bolt-loader--animated')).toBeNull();
  expect(host.querySelector('[role="progressbar"]')).toBeNull();
  act(() => host.querySelector<HTMLButtonElement>('button')!.click());
  expect(backend.wait).toHaveBeenCalledTimes(2);
  expect(backend.wait.mock.calls[0][1].aborted).toBe(true);
  expect(host.querySelector('[role="alert"]')).toBeNull();
  await act(async () => resolve());
  expect(host.querySelector('[data-testid="workspace"]')).toBeNull();
  await act(async () => { await vi.advanceTimersByTimeAsync(MINIMUM_LOADING_MS); });
  expect(host.querySelector('[data-testid="workspace"]')).not.toBeNull();
});


it('continues showing the loading bar after three seconds if the API is still starting', async () => {
  act(() => root.render(<App />));
  await act(async () => { await vi.advanceTimersByTimeAsync(MINIMUM_LOADING_MS + 2000); });
  expect(host.querySelector('[data-testid="workspace"]')).toBeNull();
  expect(host.querySelector('[role="progressbar"]')).not.toBeNull();
  await act(async () => resolve());
  expect(host.querySelector('[data-testid="workspace"]')).not.toBeNull();
  expect(host.querySelector('[role="progressbar"]')).toBeNull();
});
