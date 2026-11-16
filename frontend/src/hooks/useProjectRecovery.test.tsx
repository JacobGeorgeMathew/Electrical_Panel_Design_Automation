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

it('cancels a scheduled checkpoint when switching to a clean project',async()=>{
  const autosave=vi.fn(async()=>{});useProjectStore.setState({autosave});
  act(()=>root.render(<Harness/>));
  act(()=>useProjectStore.getState().setRequirementValue('num_feeders',16));
  act(()=>useProjectStore.setState({projectId:'other',hasUnsavedChanges:false}));
  await act(async()=>{await vi.advanceTimersByTimeAsync(1600);});
  expect(autosave).not.toHaveBeenCalled();
});

it('checkpoints edits during a server write and sends them after the response without a save loop',async()=>{
  const autosave=vi.fn(async()=>{
    useProjectStore.setState({isSaving:true});
  });
  useProjectStore.setState({autosave,recoveryVersion:0});
  act(()=>root.render(<Harness/>));
  act(()=>useProjectStore.getState().setRequirementValue('num_feeders',16));
  await act(async()=>{await vi.advanceTimersByTimeAsync(1600);});
  act(()=>useProjectStore.getState().setRequirementValue('num_feeders',20));
  expect(readRecovery('p')?.document.requirements.num_feeders).toBe(20);
  act(()=>useProjectStore.setState({isSaving:false,recoveryVersion:1}));
  await act(async()=>{await vi.advanceTimersByTimeAsync(1600);});
  expect(autosave).toHaveBeenCalledTimes(2);
  act(()=>useProjectStore.setState({isSaving:false,recoveryVersion:2}));
  await act(async()=>{await vi.advanceTimersByTimeAsync(5000);});
  expect(autosave).toHaveBeenCalledTimes(2);
  expect(readRecovery('p')?.recovery_sequence).toBe(2);
});
