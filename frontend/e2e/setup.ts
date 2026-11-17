import {spawn} from 'node:child_process';
import {access} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {createInterface} from 'node:readline';
import {createServer, type ProxyOptions} from 'vite';
import react from '@vitejs/plugin-react';

/** Own both servers for one run. No fixed ports, existing-server reuse or state
 * files. EOF also stops Python if the Playwright parent disappears. */
export default async function setup() {
  const frontend = fileURLToPath(new URL('../', import.meta.url));
  const backend = fileURLToPath(new URL('../../backend/', import.meta.url));
  const python = backend + '.venv/bin/python';
  await access(python); // Never silently use the orchestrator interpreter.
  const retarget: Array<(target: string) => void> = [];
  const proxy: ProxyOptions = {target: 'http://127.0.0.1:1', configure(server) {
    const live = server as typeof server & {options: {target: string}};
    retarget.push(target => {live.options.target = target;});
  }};
  const vite = await createServer({
    configFile: false, root: frontend, plugins: [react()],
    resolve: {alias: {'@': frontend + 'src'}},
    define: {'import.meta.env.VITE_API_BASE': JSON.stringify('/api')},
    server: {host: '127.0.0.1', port: 0, strictPort: true,
      proxy: {'/api': {...proxy}, '/__e2e__': {...proxy}}},
  });
  await vite.listen();
  const address = vite.httpServer!.address();
  if (!address || typeof address === 'string') {await vite.close(); throw new Error('Missing E2E frontend address.');}
  const origin = `http://127.0.0.1:${address.port}`;
  process.env.PANEL_E2E_BASE_URL = origin;
  const child = spawn(python, ['-u', '../frontend/e2e/backend.py'], {
    cwd: backend, stdio: ['pipe', 'pipe', 'inherit'],
    env: {...process.env, PYTHONPATH: backend, PANEL_E2E_ORIGIN: origin},
  });
  const closed = new Promise<number | null>(resolve => child.once('close', resolve));
  const stop = async () => {
    try {
      await vite.close();
    } finally {
      child.stdin.end();
      const timer = setTimeout(() => child.kill('SIGTERM'), 15_000);
      const hardStop = setTimeout(() => child.kill('SIGKILL'), 25_000);
      try {
        const code = await closed;
        if (code !== 0) throw new Error('E2E backend failed; inspect startup and disposable database cleanup output.');
      } finally {clearTimeout(timer); clearTimeout(hardStop);}
    }
  };
  try {
    const port = await new Promise<number>((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error('E2E backend startup timed out.')), 120_000);
      const lines = createInterface({input: child.stdout});
      lines.on('line', line => {
        if (line.startsWith('E2E_READY ')) {
          clearTimeout(timer);
          resolve(JSON.parse(line.slice(10)).port);
        } else console.log(line);
      });
      child.once('error', error => {clearTimeout(timer); reject(error);});
      child.once('close', () => {clearTimeout(timer); reject(new Error('E2E backend exited before startup.'));});
    });
    for (const setTarget of retarget) setTarget(`http://127.0.0.1:${port}`);
    // Ready is checked against the owned process, never the developer backend.
    const ready = await fetch(`http://127.0.0.1:${port}/ready`);
    if (!ready.ok) throw new Error('Isolated E2E database is not ready.');
    return stop;
  } catch (error) {await stop(); throw error;}
}
