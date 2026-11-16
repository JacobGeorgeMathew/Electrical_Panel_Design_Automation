import {useCommandStore} from '../../stores/commandStore';
import {useProjectStore} from '../../stores/projectStore';

/** Shared, non-modal feedback for transient gestures and retained proposals. */
export function OperationPreview() {
  const command = useCommandStore(), state = useProjectStore();
  if (!state.document || state.viewedRevisionId) return null;
  const stages = state.document.document.dirty_stages;
  const operation=command.proposal?.kind==='operations'?command.proposal.request.operations[0]:null;
  const closure=operation?.type==='RemoveComponent'?command.preview?.consequences[operation.operation_id]:null;
  const confirmRemoval=()=>{
    if(!closure||command.proposal?.kind!=='operations')return;
    const proposal=structuredClone(command.proposal);
    const op=proposal.request.operations[0];
    if(op.type!=='RemoveComponent')return;
    op.parameters.confirmed_cascade=closure;
    proposal.key=crypto.randomUUID();
    command.propose(proposal);
    void useCommandStore.getState().commitProposal();
  };
  return <section aria-label="Operation preview" className="border border-amber-700/40 bg-slate-950 p-2 text-xs text-amber-100">
    <p role="status">{command.pending ? 'Applying operation…' : Object.keys(state.editorTransforms).length
      ? 'Transient placement preview · release or apply to commit' : 'Working document saved'}
      {stages.length > 0 && ` · Recompute required: ${stages.join(', ')}`}</p>
    {command.proposal && <p>{command.proposal.kind === 'operations'
      ? command.proposal.request.operations.map(o => o.type).join(', ') : command.proposal.request.action} · proposal retained</p>}
    {command.error && <p role="alert">{command.error.code}: {command.error.message}</p>}
    {closure&&<div aria-label="Removal dependencies"><p>Review removal of {operation?.type==='RemoveComponent'&&operation.target.cem_component_id} and every dependency:</p>
      <ul>{Object.entries(closure.dependencies).filter(([,ids])=>ids.length).map(([kind,ids])=><li key={kind}>{kind}: {ids.join(', ')}</li>)}</ul>
      <button disabled={command.pending} className="editor-tool" onClick={confirmRemoval}>Confirm removal and listed dependencies</button>
    </div>}
    {command.proposal && <div className="flex gap-2">
      <button disabled={command.pending||operation?.type==='RemoveComponent'||operation?.type==='ModifyElectricalConnection'||operation?.type==='AddComponent'} onClick={()=>void command.commitProposal()} className="editor-tool">Retry operation</button>
      <button disabled={command.pending} onClick={()=>{command.clear();state.resetEditorDraft();}} className="editor-tool">Discard proposal</button>
    </div>}
    <p>Save preserves the working draft. Routes, validation and CAD stay dirty until explicit recompute.</p>
  </section>;
}
