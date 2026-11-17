import {test, expect, openHarness} from './fixtures';

test('browser session bootstrap, rotation and hostile-origin rejection use the real API', async ({page, projectId, playwright, baseURL}) => {
  await openHarness(page, projectId);
  const anonymous = await playwright.request.newContext({baseURL});
  try {
    const missing = await anonymous.post('/api/projects', {data: {name: 'unauthorized'}});
    expect(missing.status()).toBe(401);
    const hostile = await anonymous.post('/api/local-session', {headers: {
      Origin: 'https://untrusted.example', 'X-Panel-Bootstrap': '1',
    }});
    expect(hostile.status()).toBe(403);
    const result = await page.evaluate(async id => {
      // Match Vite's canonical module URLs so rotation updates the same in-memory
      // singleton used by the application, rather than an extensionless duplicate.
      const {request} = await import('../src/api/client.ts');
      const {rotateLocalSession} = await import('../src/api/localSession.ts');
      await request(`/projects/${id}/open`, {method: 'POST', body: '{}'});
      await rotateLocalSession(new AbortController().signal);
      await request(`/projects/${id}/open`, {method: 'POST', body: '{}'});
      return {authorized: true, storedCredentials: Object.keys(localStorage).some(key => /session|token|credential/i.test(key))};
    }, projectId);
    expect(result).toEqual({authorized: true, storedCredentials: false});
  } finally {await anonymous.dispose();}
});
