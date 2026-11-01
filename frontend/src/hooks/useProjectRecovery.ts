import {useEffect} from 'react';
import {useProjectStore,recoveryDocument} from '../stores/projectStore';
import {writeRecovery} from '../stores/projectRecovery';

export function useProjectRecovery(){
  useEffect(()=>{
    let timer:ReturnType<typeof setTimeout>|undefined;
    let localFingerprint='', sentFingerprint='';
    const checkpoint=()=>{
      const state=useProjectStore.getState();
      const fingerprint=JSON.stringify([state.projectId,state.editSequence,state.lockVersion]);
      if(!state.projectId||!state.hasUnsavedChanges||state.pendingRecovery)return;
      if(localFingerprint!==fingerprint){
        try{writeRecovery(state.projectId,{base_version:state.lockVersion,saved_at:new Date().toISOString(),document:recoveryDocument(state)});localFingerprint=fingerprint;}
        catch{localFingerprint=fingerprint;useProjectStore.setState({autosaveStatus:'Local recovery storage is unavailable. Save your project before leaving.'});return;}
      }
      if(!state.isSaving&&!state.isGenerating&&sentFingerprint!==fingerprint){
        clearTimeout(timer);
        timer=setTimeout(()=>{sentFingerprint=fingerprint;void useProjectStore.getState().autosave();},1500);
      }
    };
    const unsubscribe=useProjectStore.subscribe(checkpoint);
    const beforeUnload=(event:BeforeUnloadEvent)=>{
      const state=useProjectStore.getState();
      if(state.hasUnsavedChanges){checkpoint();event.preventDefault();event.returnValue='';}
    };
    const online=()=>{sentFingerprint='';checkpoint();};
    window.addEventListener('beforeunload',beforeUnload);
    window.addEventListener('online',online);
    return()=>{unsubscribe();clearTimeout(timer);window.removeEventListener('beforeunload',beforeUnload);window.removeEventListener('online',online);};
  },[]);
}
