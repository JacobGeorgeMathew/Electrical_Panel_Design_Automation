import React,{act} from 'react';
import {createRoot,Root} from 'react-dom/client';
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {useProjectStore} from '../stores/projectStore';
import {readRecovery} from '../stores/projectRecovery';
import {useProjectRecovery} from './useProjectRecovery';
(globalThis as any).IS_REACT_ACT_ENVIRONMENT=true;
let host:HTMLDivElement,root:Root;
function Harness(){useProjectRecovery();return null;}
beforeEach(()=>{vi.useFakeTimers();localStorage.clear();host=document.createElement('div');root=createRoot(host);useProjectStore.setState({projectId:'p',lockVersion:2,currentRevisionId:null,requirementValues:{},projectConfiguration:{},editorTransforms:{},schematicData:null,hasUnsavedChanges:false,pendingRecovery:null,isSaving:false,isGenerating:false,editSequence:0});});
afterEach(()=>{act(()=>root.unmount());vi.useRealTimers();});
it('checkpoints edits immediately and debounces server autosave',async()=>{
  const autosave=vi.fn(async()=>{});useProjectStore.setState({autosave});
  act(()=>root.render(<Harness/>));
  act(()=>useProjectStore.getState().setRequirementValue('num_feeders',16));
  expect(readRecovery('p')?.document.requirements.num_feeders).toBe(16);
  act(()=>useProjectStore.getState().setRequirementValue('num_feeders',20));
  await act(async()=>{await vi.advanceTimersByTimeAsync(1600);});
  expect(autosave).toHaveBeenCalledTimes(1);
  expect(readRecovery('p')?.document.requirements.num_feeders).toBe(20);
});
