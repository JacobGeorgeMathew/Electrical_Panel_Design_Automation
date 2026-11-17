import {useJobStore, jobActive} from '../../stores/jobStore';
import {useProjectStore} from '../../stores/projectStore';
import {useCommandStore} from '../../stores/commandStore';
import {recomputeAvailability} from '../../stores/documentStore';

const stageName = (stage: string) => ({requirements: 'Requirements', calculations: 'Calculations',
  selection: 'Catalog selection', connectivity: 'Electrical connectivity', schematic: 'Schematic',
  enclosure: 'Enclosure selection', zoning: 'Zoning', placement: 'Placement', ducts: 'Ducts',
  routes: 'Duct routing', physical_validation: 'Physical validation', bom: 'BOM', cad: 'CAD'}[stage] || stage);

export function JobProgress() {
  const state = useProjectStore(), store = useJobStore(), command = useCommandStore();
  const projectId = state.projectId, job = store.jobs[projectId], intent = store.tracking[projectId];
  const active = jobActive(job), pending = store.pending[projectId];
  const availability = recomputeAvailability(state);
  const blocked = pending || availability.unavailable || command.pending || !!command.proposal;
  const response = job?.result?.response;
  return <section aria-label="Recompute job">
    <div className="console-row">
      <button disabled={blocked || active || (!!intent && !job)} title={availability.reason || undefined}
        onClick={() => void store.submit(!!job)}>Recompute saved document</button>
      {availability.reason && <span>{availability.reason}</span>}
      {!job && intent && <span role="status">Checking retained job submission…</span>}
      {!job && !intent && <span>Explicit execution updates a review proposal. Apply updates the working draft; publication remains separate.</span>}
    </div>
    {job && <>
      <div className="console-row" role="status" aria-live="polite">
        {active && <progress aria-label="Recompute progress"/>}
        <span>Recompute · {job.state} · base sequence {job.base_sequence} · attempt {job.attempts}/{job.max_attempts}
          {job.result?.current_stage ? ` · ${stageName(job.result.current_stage)}` : ''}</span>
        {active && <button disabled={pending} onClick={() => void store.cancel(projectId)}>Cancel job</button>}
        {!active && <button disabled={blocked} onClick={() => void store.submit(true)}>Retry recompute from saved base</button>}
      </div>
      {job.error && <div className="console-row error" role="alert"><b>{job.error.code}</b> {job.error.message}</div>}
      {job.state === 'CANCELLED' && <div className="console-row">Job cancelled. The working document is unchanged.</div>}
      {!!job.result?.stage_executions?.length && <details open><summary>Stage execution records</summary>
        <ul>{job.result.stage_executions.map((stage, i) => <li key={i}>
          {stageName(stage.stage_id)} ({stage.adapter}): {stage.status} · {Math.round(stage.elapsed_ms)} ms
          {stage.failure_code && ` · ${stage.failure_code}`}
        </li>)}</ul>
      </details>}
      {response && <>
        {response.conflicts.map((conflict, i) => <div className="console-row error" key={i}>{conflict.target}: {conflict.reason}</div>)}
        {response.batch && <details><summary>Review recompute effects</summary>
          <p>{response.preview?.changes.length || 0} model changes · scheduled: {response.scheduled_stages.map(stageName).join(', ') || 'none'}.</p>
          <ul>{response.preview?.changes.map((change, i) => <li key={i}>{change.model} · {change.target_id} · {change.changed_fields.join(', ')}</li>)}</ul>
        </details>}
        {response.batch && <div className="console-row">
          <button disabled={blocked || !!intent?.applied} onClick={() => void store.apply(projectId)}>Apply recompute proposal</button>
          <span>{intent?.applied ? 'Applied to the working draft. No revision published.' : 'Review the effects before applying. Newer drafts are protected.'}</span>
        </div>}
      </>}
    </>}
    {store.errors[projectId] && <div className="console-row error" role="alert">{store.errors[projectId]}
      {!job && <button disabled={pending} onClick={() => void store.refresh(projectId)}>Check retained submission</button>}
    </div>}
    {store.statusErrors[projectId] && <div className="console-row error" role="alert">
      <span>{store.statusErrors[projectId]}</span>
      <button disabled={pending} onClick={() => void store.refresh(projectId)}>Retry job status</button>
    </div>}
  </section>;
}
