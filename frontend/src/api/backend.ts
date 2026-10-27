import { API_BASE } from './config';

export async function waitForBackend(timeoutMs=30000,signal?:AbortSignal) {
  const start=Date.now();
  const healthBase=API_BASE.replace(/\/api\/?$/,'');
  let reachedBackend=false;
  while(Date.now()-start<timeoutMs){
    if(signal?.aborted)throw new Error('Connection cancelled.');
    const controller=new AbortController();
    const abort=()=>controller.abort();
    signal?.addEventListener('abort',abort,{once:true});
    const timer=setTimeout(abort,1500);
    try{
      const response=await fetch(healthBase+'/ready',{signal:controller.signal});
      reachedBackend=true;
      if(response.ok)return;
    }catch{}finally{clearTimeout(timer);signal?.removeEventListener('abort',abort);}
    await new Promise(resolve=>setTimeout(resolve,300));
  }
  throw new Error(reachedBackend?'The API is running, but PostgreSQL is unavailable or application migrations are required.':'The design API did not become available.');
}
