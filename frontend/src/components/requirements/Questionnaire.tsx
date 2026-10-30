import React, { useEffect, useState } from 'react';
import { useProjectStore } from '../../stores/projectStore';
import { fetchQuestionnaire, fetchArchetype, fetchRequirementSuggestions } from '../../api/client';
import type { Question, RequirementSuggestions } from '../../types/api';
import { EnclosureConfigurator } from '../projects/EnclosureConfigurator';
import { Sliders, CheckCircle2, AlertTriangle, Zap, ArrowUpRight, Cpu } from 'lucide-react';

const dependencyMatches = (dep: any, value: any) => {
  switch (dep.operator) {
    case 'equals': return value === dep.value;
    case 'greater_than': return value !== undefined && value !== null && value > dep.value;
    case 'less_than': return value !== undefined && value !== null && value < dep.value;
    case 'in': return Array.isArray(dep.value) && dep.value.includes(value);
    default: return false;
  }
};

export const Questionnaire: React.FC = () => {
  const {
    projectId,
    requirementValues,
    setRequirementValue,
    runDesignPipeline,
    applyChangePropagation,
    cem,
    isGenerating,
    errorMessage,
    validationErrors,
    validationWarnings,
    setError,
    validateCurrentRequirements,
    createNewProject, archetypes, isSaving, isLoadingProject
  } = useProjectStore();

  const [suggestions,setSuggestions]=useState<RequirementSuggestions|null>(null);
  const [suggestionError,setSuggestionError]=useState(false);
  const [questions, setQuestions] = useState<Question[]>([]);
  const [loadingQuestions, setLoadingQuestions] = useState(true);
  const [questionAttempt, setQuestionAttempt] = useState(0);
  const [selectedArchetype, setSelectedArchetype] = useState('DB');
  const busy = isGenerating || isSaving || isLoadingProject;
  const [projectName, setProjectName] = useState('New Distribution Board');

  useEffect(() => {
    const abort = new AbortController();
    setLoadingQuestions(true);
    const pending = projectId ? fetchQuestionnaire(projectId, abort.signal) :
      fetchArchetype(selectedArchetype, abort.signal).then(t => t.questions);
    pending.then(rows => { if (!abort.signal.aborted) { setQuestions(rows); setLoadingQuestions(false); } })
      .catch(error => { if (!abort.signal.aborted) { setLoadingQuestions(false); setError(error.message); } });
    return () => abort.abort();
  }, [projectId, selectedArchetype, setError, questionAttempt]);

  const effectiveValues = { ...Object.fromEntries(questions.map(q => [q.id, q.default])), ...requirementValues };
  const visibleQuestions = questions.filter(q => q.depends_on.every(dep => dependencyMatches(dep, effectiveValues[dep.field])));

  const suggestionValues=JSON.stringify({num_feeders:effectiveValues.num_feeders,phases:effectiveValues.phases,spare_capacity_pct:effectiveValues.spare_capacity_pct});
  useEffect(()=>{
    if(!questions.length)return;
    const abort=new AbortController();setSuggestions(null);setSuggestionError(false);
    const timer=setTimeout(()=>fetchRequirementSuggestions(projectId,selectedArchetype,JSON.parse(suggestionValues),abort.signal)
      .then(result=>{if(!abort.signal.aborted&&result?.suggestions)setSuggestions(result);})
      .catch(()=>{if(!abort.signal.aborted)setSuggestionError(true);}),200);
    return()=>{clearTimeout(timer);abort.abort();};
  },[projectId,selectedArchetype,suggestionValues,questions]);

  const handleValueChange = (id: string, val: any) => {
    setRequirementValue(id, val);
  };

  const handleApplyChange = (id: string, val: any) => {
    applyChangePropagation(id, val);
  };

  const handleValidate = async () => {
    if (await validateCurrentRequirements()) await runDesignPipeline();
  };

  return (
    <div className="flex-1 min-h-0 overflow-y-auto max-w-5xl w-full mx-auto p-6 space-y-6">
      <div className="flex items-center justify-between bg-slate-900 border border-slate-800 p-6 rounded-2xl shadow-xl">
        <div className="space-y-1">
          <div className="flex items-center space-x-2">
            <Sliders className="w-5 h-5 text-blue-400" />
            <h2 className="text-xl font-bold text-slate-100">Guided Electrical Panel Requirements</h2>
          </div>
          <p className="text-xs text-slate-400">
            Configure Distribution Board (DB) electrical specifications to populate the Canonical Engineering Model (CEM).
          </p>
        </div>

        <label className="text-xs text-slate-400">New project archetype
          <select aria-label="New project archetype" value={selectedArchetype} disabled={busy}
            onChange={e=>setSelectedArchetype(e.target.value)} className="ml-2 rounded border border-slate-700 bg-slate-950 p-2">
            {archetypes.map(a=><option key={a.version_id} value={a.code} disabled={!a.supported}>{a.name} · v{a.version_no}{!a.supported?' (reference only)':''}</option>)}
          </select>
        </label>
      </div>

      <div className="flex flex-wrap items-center gap-3 bg-slate-900/70 border border-slate-800 p-4 rounded-xl">
        <input value={projectName} onChange={(e) => setProjectName(e.target.value)} aria-label="New project name"
          className="min-w-64 flex-1 bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm" />
        <button onClick={() => createNewProject(projectName, selectedArchetype, archetypes.find(a=>a.code===selectedArchetype)?.version_id)} disabled={busy || !projectName.trim() || !archetypes.some(a=>a.code===selectedArchetype&&a.supported)}
          className="px-4 py-2 bg-slate-800 hover:bg-slate-700 disabled:opacity-50 border border-slate-700 rounded-lg text-xs font-semibold">
          Create DB Project
        </button>
        <button onClick={handleValidate} disabled={busy || !projectId}
          className="px-4 py-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 rounded-lg text-xs font-semibold">
          Validate & Generate
        </button>
      </div>

      {(errorMessage || validationErrors.length > 0) && (
        <div role="alert" className="bg-red-950/50 border border-red-800 rounded-xl p-4 text-sm text-red-200 space-y-1">
          {errorMessage && <p>{errorMessage}</p>}
          {validationErrors.map((error, index) => <p key={index}>• {error}</p>)}
        </div>
      )}
      {validationWarnings.length > 0 && (
        <div role="status" className="bg-amber-950/40 border border-amber-800 rounded-xl p-4 text-sm text-amber-200 space-y-1">
          {validationWarnings.map((warning, index) => <p key={index}>• {warning}</p>)}
        </div>
      )}

      <EnclosureConfigurator />
      {suggestions&&<section aria-label="Feeder-based planning estimates" className="rounded-xl border border-blue-900 bg-blue-950/20 p-4 text-xs text-slate-300">
        <h3 className="mb-2 font-semibold">Suggestions for {effectiveValues.num_feeders} feeders</h3>
        {suggestions.estimates.estimated_max_phase_demand_a!==undefined&&<p>Estimated maximum phase demand: {suggestions.estimates.estimated_max_phase_demand_a} A · Spare feeder spaces for planning: {suggestions.estimates.spare_feeder_spaces}</p>}
        <p className="mt-1 text-slate-400">{suggestions.message}</p>
        {suggestions.estimates.estimated_max_phase_demand_a!==undefined&&effectiveValues.incomer_rating<suggestions.estimates.estimated_max_phase_demand_a&&<p className="mt-2 text-amber-300">Your selected incomer is below this planning estimate. Review the actual connected loads before proceeding.</p>}
        <details className="mt-2 text-slate-400"><summary>Calculation assumptions</summary>{suggestions.assumptions?.map(a=><p key={a}>{a}</p>)}</details>
      </section>}
      {suggestionError&&<p role="status" className="text-xs text-amber-300">Suggestions are unavailable. You can still choose supported values.</p>}
      {loadingQuestions && <p role="status" className="text-sm text-slate-400">Loading questionnaire…</p>}
      {!loadingQuestions && !questions.length && <p className="text-sm text-slate-400">Questionnaire unavailable. <button className="underline" onClick={()=>setQuestionAttempt(v=>v+1)}>Retry</button></p>}
      {/* Grid of Dynamic Questions */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {visibleQuestions.map((q) => {
          const val = effectiveValues[q.id];
          const choices=Array.isArray(q.options)?q.options:null;
          const invalidChoice=choices!==null&&!choices.some(option=>option===val);
          const isConfirmed = requirementValues[q.id] !== undefined&&!invalidChoice;
          const suggestion=suggestions?.suggestions[q.id];

          return (
            <div
              key={q.id}
              className="bg-slate-900/80 border border-slate-800 p-5 rounded-2xl space-y-3 hover:border-slate-700 transition-all shadow-md"
            >
              <div className="flex items-center justify-between">
                <label className="text-sm font-semibold text-slate-200">{q.label}</label>
                <div className="flex items-center space-x-1">
                  {invalidChoice ? <span className="text-xs text-red-300">Choose a supported value</span> : isConfirmed ? (
                    <span className="flex items-center space-x-1 px-2 py-0.5 text-[10px] font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 rounded-full">
                      <CheckCircle2 className="w-3 h-3" />
                      <span>Confirmed</span>
                    </span>
                  ) : (
                    <span className="flex items-center space-x-1 px-2 py-0.5 text-[10px] font-semibold bg-amber-500/10 text-amber-400 border border-amber-500/20 rounded-full">
                      <AlertTriangle className="w-3 h-3" />
                      <span>Assumed</span>
                    </span>
                  )}
                </div>
              </div>

              {/* Input Render logic */}
              {q.type === 'number' && choices===null && (
                <div className="flex items-center space-x-3">
                  <input
                    type="number"
                    value={val ?? ''} disabled={busy} min={q.validation.min} max={q.validation.max} aria-label={q.label}
                    onChange={(e) => handleValueChange(q.id, Number(e.target.value))}
                    className="w-full bg-slate-950 border border-slate-700 rounded-xl px-4 py-2 text-sm text-slate-100 focus:outline-none focus:border-blue-500 font-mono"
                  />
                  {q.unit && (
                    <span className="text-xs font-mono px-3 py-2 bg-slate-800 border border-slate-700 text-slate-400 rounded-xl">
                      {q.unit}
                    </span>
                  )}
                </div>
              )}

              {(q.type === 'select'||q.type==='number'&&choices!==null) && (
                <select
                  value={invalidChoice?'':String(val ?? '')} disabled={busy||choices?.length===0} aria-label={q.label} aria-invalid={invalidChoice}
                  onChange={(e) => handleValueChange(q.id, q.options?.find(o=>String(o)===e.target.value) ?? e.target.value)}
                  className="w-full bg-slate-950 border border-slate-700 rounded-xl px-4 py-2 text-sm text-slate-100 focus:outline-none focus:border-blue-500 font-mono"
                >
                  {invalidChoice&&<option value="" disabled>{choices?.length?'Choose a supported value':'No supported choices'}{val!==undefined&&val!==null?` (saved: ${val})`:''}</option>}
                  {q.options?.map((opt: any) => (
                    <option key={opt} value={opt}>
                      {opt}{q.unit?` ${q.unit}`:''}
                    </option>
                  ))}
                </select>
              )}

              {q.type === 'boolean' && (
                <div className="flex items-center space-x-4 pt-1">
                  <label className="flex items-center space-x-2 text-xs text-slate-300 cursor-pointer">
                    <input
                      type="radio"
                      name={q.id} disabled={busy}
                      checked={val === true}
                      onChange={() => handleValueChange(q.id, true)}
                      className="text-blue-600 focus:ring-blue-500"
                    />
                    <span>Yes</span>
                  </label>
                  <label className="flex items-center space-x-2 text-xs text-slate-300 cursor-pointer">
                    <input
                      type="radio"
                      name={q.id} disabled={busy}
                      checked={val === false}
                      onChange={() => handleValueChange(q.id, false)}
                      className="text-blue-600 focus:ring-blue-500"
                    />
                    <span>No</span>
                  </label>
                </div>
              )}

              {q.type === 'text' && <input aria-label={q.label} value={val ?? ''} disabled={busy} onChange={e=>handleValueChange(q.id,e.target.value)} className="w-full rounded border border-slate-700 bg-slate-950 p-2 text-sm"/>}
              {q.type === 'multi_select' && <select multiple aria-label={q.label} disabled={busy} value={(val || []).map(String)}
                onChange={e=>handleValueChange(q.id,Array.from(e.target.selectedOptions,o=>q.options?.find(v=>String(v)===o.value)??o.value))}
                className="w-full rounded border border-slate-700 bg-slate-950 p-2 text-sm">{q.options?.map(o=><option key={String(o)} value={String(o)}>{String(o)}</option>)}</select>}
              {q.type === 'object' && <ObjectAnswer value={val} disabled={busy} onChange={v=>handleValueChange(q.id,v)} onError={setError}/>}
              {q.help_text&&<p className="text-xs text-slate-400">{q.help_text}</p>}
              {suggestion&&<div className="rounded-lg border border-blue-900 bg-blue-950/30 p-3 text-xs text-blue-200">
                <p>Suggested: {suggestion.value} {q.unit} — {suggestion.reason}</p>
                <button type="button" disabled={busy||val===suggestion.value} onClick={()=>handleValueChange(q.id,suggestion.value)} className="mt-2 rounded bg-blue-700 px-3 py-1.5 disabled:opacity-50" aria-label={`Use suggested ${q.label}`}>{val===suggestion.value?'Suggestion selected':'Use suggestion'}</button>
                <p className="mt-1 text-slate-400">You can choose any supported option above.</p>
              </div>}
              <div className="flex justify-end pt-1">
                <button onClick={() => handleApplyChange(q.id, val)} disabled={busy || !cem || invalidChoice}
                  className="px-3 py-1.5 bg-blue-600/80 hover:bg-blue-500 disabled:opacity-40 text-white text-[11px] font-semibold rounded-lg">
                  Review & Apply Change
                </button>
              </div>
            </div>
          );
        })}
      </div>

      {/* Display Output Calculations Summary if CEM exists */}
      {cem?.calculations && (
        <div className="bg-slate-900 border border-slate-800 p-6 rounded-2xl space-y-4">
          <div className="flex items-center space-x-2">
            <Cpu className="w-5 h-5 text-emerald-400" />
            <h3 className="text-sm font-bold text-slate-200">Simplified Engineering Estimates</h3>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {cem.calculations.map((calc) => (
              <div key={calc.id} className="p-3 bg-slate-950 border border-slate-800 rounded-xl space-y-1">
                <div className="text-[11px] text-slate-400">{calc.label}</div>
                <div className="text-base font-bold font-mono text-emerald-400">
                  {calc.value} <span className="text-xs text-slate-400">{calc.unit}</span>
                </div>
                <div className="text-[9px] font-mono text-slate-500 truncate">{calc.formula_used}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

function ObjectAnswer({value,disabled,onChange,onError}:{value:any;disabled:boolean;onChange:(v:any)=>void;onError:(message:string)=>void}){
  const [text,setText]=useState(JSON.stringify(value??{},null,2));
  useEffect(()=>setText(JSON.stringify(value??{},null,2)),[value]);
  return <textarea aria-label="Structured answer" value={text} disabled={disabled} onChange={e=>setText(e.target.value)}
    onBlur={()=>{try{onChange(JSON.parse(text));}catch{onError('Structured answer must contain valid JSON. Your local text is retained.');}}}
    className="w-full rounded border border-slate-700 bg-slate-950 p-2 font-mono text-xs"/>;
}
