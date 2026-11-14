/** Actual headless Firefox SVG render timings, using installed Vite/React.
 * Run from frontend: node scripts/measure-design-baseline.mjs
 * No dependency installation, mock renderer or production behavior changes.
 */
import assert from 'node:assert/strict';
import { spawn, execFileSync } from 'node:child_process';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createServer } from 'vite';

const frontend = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
assert.equal(process.cwd(), frontend, 'Run from frontend/');
const backend = path.resolve(frontend, '../backend');
const harness = `
import React from 'react';
import {createRoot} from 'react-dom/client';
import {flushSync} from 'react-dom';
import {Layout2DViewer} from '/src/components/layout/Layout2DViewer.tsx';
import {useProjectStore} from '/src/stores/projectStore.ts';
import '/src/index.css';
window.measureBaseline = async (packageData) => {
  const pdm = packageData.pdm;
  useProjectStore.setState({pdm, pdmBaseline:pdm, cem:packageData.cem,
    editorTransforms:{}, selectedObjectId:null, hoveredObjectId:null, wireVisibility:true});
  const host = document.createElement('div');
  host.style.cssText='width:1280px;height:900px;display:flex';
  document.body.append(host);
  const root=createRoot(host);
  const started=performance.now();
  flushSync(()=>root.render(React.createElement(Layout2DViewer)));
  // Complete layout and cross two animation-frame callbacks, allowing a paint
  // opportunity. This is a frame-boundary metric, not GPU completion timing.
  host.getBoundingClientRect();
  await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));
  const elapsed=performance.now()-started;
  const ids=Array.from(host.querySelectorAll('[aria-label^="Move "]')).map(e=>e.getAttribute('aria-label').slice(5));
  const routes=Array.from(host.querySelectorAll('polyline title')).map(e=>e.textContent.split(' | ')[0]);
  const svg=host.querySelector('svg[viewBox="0 0 '+pdm.enclosure_width+' '+pdm.enclosure_height+'"]');
  const result={elapsed_ms:elapsed,component_ids:ids,conductor_ids:routes,
    viewbox:svg?.getAttribute('viewBox'),width:innerWidth,height:innerHeight,
    visibility:document.visibilityState};
  flushSync(()=>root.unmount());host.remove();return result;
};
`;

let browser, socket, server;
const profile = await mkdtemp(path.join(tmpdir(), 'panelflow-render-'));
let browserLog = '';
const pending = new Map();
const pageErrors = [];
let sequence = 0;
function request(method, params) {
  return new Promise((resolve, reject) => {
    const id = ++sequence;
    const timeout = setTimeout(()=>{pending.delete(id);reject(new Error(method+' timed out'));}, 30000);
    pending.set(id, {resolve:value=>{clearTimeout(timeout);resolve(value);}, reject:error=>{clearTimeout(timeout);reject(error);}});
    socket.send(JSON.stringify({id,method,params}));
  });
}
try {
  server = await createServer({
    configFile:path.join(frontend,'vite.config.ts'),
    server:{host:'127.0.0.1',port:0,open:false},
    plugins:[{name:'baseline-harness', configureServer(vite) {
      vite.middlewares.use('/baseline-measure.html', async (_req,res,next)=>{
        try {
          const html=await vite.transformIndexHtml('/baseline-measure.html',
            '<!doctype html><html><body><script type="module" src="/baseline-harness.js"></script></body></html>');
          res.setHeader('Content-Type','text/html');res.end(html);
        } catch(error) {next(error);}
      });
    }, resolveId(id) {if(id==='/baseline-harness.js')return '\0baseline-harness';},
       load(id) {if(id==='\0baseline-harness')return harness;}}],
  });
  await server.listen();
  // Use an ephemeral debugging port; Firefox announces its BiDi URL on stderr.
  browser=spawn('firefox',['--headless','--no-remote','--profile',profile,'--remote-debugging-port','0','--width','1280','--height','900'],{stdio:['ignore','pipe','pipe']});
  browser.on('error', error=>{browserLog+=error.message;});
  for(const stream of [browser.stdout,browser.stderr])stream.on('data',chunk=>{browserLog+=chunk.toString();});
  let endpoint;
  for(let i=0;i<300;i++) {
    endpoint=browserLog.match(/WebDriver BiDi listening on (ws:\/\/\S+)/)?.[1];
    if(endpoint)break;
    if(browser.exitCode!==null)throw new Error('Firefox exited: '+browserLog);
    await new Promise(r=>setTimeout(r,100));
  }
  assert.ok(endpoint,'Firefox BiDi endpoint unavailable: '+browserLog);
  socket=new WebSocket(endpoint.replace(/\/$/,'')+'/session');
  await new Promise((resolve,reject)=>{socket.addEventListener('open',resolve,{once:true});socket.addEventListener('error',reject,{once:true});});
  socket.addEventListener('message',event=>{
    const value=JSON.parse(event.data);const handler=pending.get(value.id);
    if(value.method==='log.entryAdded' && value.params.level==='error')pageErrors.push(value.params.text);
    if(handler){pending.delete(value.id);if(value.type==='error')handler.reject(new Error(JSON.stringify(value)));else handler.resolve(value.result);}
  });
  const session=await request('session.new',{capabilities:{alwaysMatch:{acceptInsecureCerts:false}}});
  await request('session.subscribe',{events:['log.entryAdded']});
  const {context}=await request('browsingContext.create',{type:'tab'});
  const port=server.httpServer.address().port;
  await request('browsingContext.navigate',{context,url:'http://127.0.0.1:'+port+'/baseline-measure.html',wait:'complete'});
  async function evaluate(expression) {
    const response=await request('script.evaluate',{expression,target:{context},awaitPromise:true});
    assert.equal(response.type,'success',JSON.stringify(response));
    return response.result;
  }
  for(let i=0;i<300;i++) {
    const ready=await evaluate('typeof window.measureBaseline === "function"');
    if(ready.value)break;
    if(pageErrors.length || i===299)throw new Error('Render harness failed to load: '+JSON.stringify(pageErrors));
    await new Promise(r=>setTimeout(r,100));
  }
  for(const id of ['db-12','db-16']) {
    const packageData=JSON.parse(execFileSync(path.join(backend,'.venv/bin/python'),
      ['-m','tests.design_baseline_support','package',id],{cwd:backend,maxBuffer:32*1024*1024}).toString());
    const rows=[];
    for(let i=0;i<6;i++) {
      // Return a JSON string to avoid BiDi-specific remote-value deserialization.
      const result=await evaluate('window.measureBaseline('+JSON.stringify(packageData)+').then(JSON.stringify)');
      const row=JSON.parse(result.value);
      assert.deepEqual(row.component_ids,packageData.pdm.components.map(c=>c.cem_component_id));
      assert.deepEqual(row.conductor_ids,packageData.pdm.routes.map(r=>r.conductor_id));
      assert.equal(row.visibility,'visible');rows.push(row);
    }
    const samples=rows.slice(1).map(r=>r.elapsed_ms);
    const sorted=[...samples].sort((a,b)=>a-b);
    console.log('BASELINE_RENDER '+JSON.stringify({case:id,browser:session.capabilities.browserName,
      browser_version:session.capabilities.browserVersion,mode:'headless Firefox, Vite development server',
      metric:'fresh React SVG mount through second animation-frame callback',
      host_css_px:[1280,900],viewport_css_px:[rows[0].width,rows[0].height],viewbox:rows[0].viewbox,
      components:rows[0].component_ids.length,routes:rows[0].conductor_ids.length,
      warmup_ms:rows[0].elapsed_ms,samples_ms:samples,median_ms:sorted[2],nearest_rank_p95_ms:sorted[4]}));
  }
  await request('session.end',{});
} finally {
  socket?.close();
  if(browser && browser.exitCode===null) {
    browser.kill('SIGTERM');
    await new Promise(resolve=>{const timer=setTimeout(()=>{browser.kill('SIGKILL');resolve();},5000);browser.once('exit',()=>{clearTimeout(timer);resolve();});});
  }
  await server?.close();
  await rm(profile,{recursive:true,force:true});
}
