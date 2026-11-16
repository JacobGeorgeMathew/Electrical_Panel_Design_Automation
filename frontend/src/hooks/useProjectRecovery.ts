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
      const localVersion=JSON.stringify([fingerprint,state.recoveryVersion]);
      clearTimeout(timer);
      if(!state.projectId||!state.hasUnsavedChanges||state.pendingRecovery)return;
      if(localFingerprint!==localVersion){
        try{writeRecovery(state.projectId,{schema_version:2,recovery_sequence:state.recoveryVersion,base_version:state.lockVersion,saved_at:new Date().toISOString(),document:recoveryDocument(state)});localFingerprint=localVersion;}
        catch{localFingerprint=localVersion;useProjectStore.setState({autosaveStatus:'Local recovery storage is unavailable. Save your project before leaving.'});return;}
      }
      if(!state.isSaving&&!state.isGenerating&&sentFingerprint!==fingerprint){
        clearTimeout(timer);
        timer=setTimeout(()=>{sentFingerprint=fingerprint;void useProjectStore.getState().autosave();},1500);
      }
    };
    const unsubscribe=useProjectStore.subscribe(checkpoint);
    checkpoint();
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
