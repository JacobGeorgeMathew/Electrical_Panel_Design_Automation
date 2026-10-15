import React, { useEffect, useState } from 'react';
import { useProjectStore } from '../../stores/projectStore';
import { fetchQuestionnaire } from '../../api/client';
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
    createNewProject
  } = useProjectStore();

  const [questions, setQuestions] = useState<any[]>([]);
  const [projectName, setProjectName] = useState('New Distribution Board');

  useEffect(() => {
    fetchQuestionnaire(projectId).then(setQuestions).catch((error) => {
      setError(`Could not load DB requirements: ${error instanceof Error ? error.message : String(error)}`);
    });
  }, [projectId, setError]);

  // Evaluate visible questions
  const visibleQuestions = questions.filter((q) => {
    if (!q.depends_on || q.depends_on.length === 0) return true;
    return q.depends_on.every((dep: any) => dependencyMatches(dep, requirementValues[dep.field]));
  });

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

        <div className="flex items-center space-x-2">
          <button
            onClick={() => {
              setRequirementValue('incomer_rating', 250);
              setRequirementValue('num_feeders', 12);
              runDesignPipeline({ incomer_rating: 250, num_feeders: 12 });
            }}
            className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-mono rounded-lg border border-slate-700"
          >
            Preset: Standard DB (250A / 12 Feeder)
          </button>
          <button
            onClick={() => {
              setRequirementValue('incomer_rating', 400);
              setRequirementValue('num_feeders', 16);
              runDesignPipeline({ incomer_rating: 400, num_feeders: 16 });
            }}
            className="px-3 py-1.5 bg-blue-600/20 hover:bg-blue-600/30 text-blue-300 text-xs font-mono rounded-lg border border-blue-500/30"
          >
            Preset: Heavy DB (400A / 16 Feeder)
          </button>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3 bg-slate-900/70 border border-slate-800 p-4 rounded-xl">
        <input value={projectName} onChange={(e) => setProjectName(e.target.value)} aria-label="New project name"
          className="min-w-64 flex-1 bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm" />
        <button onClick={() => createNewProject(projectName)} disabled={isGenerating || !projectName.trim()}
          className="px-4 py-2 bg-slate-800 hover:bg-slate-700 disabled:opacity-50 border border-slate-700 rounded-lg text-xs font-semibold">
          Create DB Project
        </button>
        <button onClick={handleValidate} disabled={isGenerating}
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

      {/* Grid of Dynamic Questions */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {visibleQuestions.map((q) => {
          const val = requirementValues[q.id] ?? q.default;
          const isConfirmed = requirementValues[q.id] !== undefined;

          return (
            <div
              key={q.id}
              className="bg-slate-900/80 border border-slate-800 p-5 rounded-2xl space-y-3 hover:border-slate-700 transition-all shadow-md"
            >
              <div className="flex items-center justify-between">
                <label className="text-sm font-semibold text-slate-200">{q.label}</label>
                <div className="flex items-center space-x-1">
                  {isConfirmed ? (
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
              {q.type === 'number' && (
                <div className="flex items-center space-x-3">
                  <input
                    type="number"
                    value={val}
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

              {q.type === 'select' && (
                <select
                  value={val}
                  onChange={(e) => handleValueChange(q.id, e.target.value)}
                  className="w-full bg-slate-950 border border-slate-700 rounded-xl px-4 py-2 text-sm text-slate-100 focus:outline-none focus:border-blue-500 font-mono"
                >
                  {q.options?.map((opt: any) => (
                    <option key={opt} value={opt}>
                      {opt}
                    </option>
                  ))}
                </select>
              )}

              {q.type === 'boolean' && (
                <div className="flex items-center space-x-4 pt-1">
                  <label className="flex items-center space-x-2 text-xs text-slate-300 cursor-pointer">
                    <input
                      type="radio"
                      name={q.id}
                      checked={val === true}
                      onChange={() => handleValueChange(q.id, true)}
                      className="text-blue-600 focus:ring-blue-500"
                    />
                    <span>Yes</span>
                  </label>
                  <label className="flex items-center space-x-2 text-xs text-slate-300 cursor-pointer">
                    <input
                      type="radio"
                      name={q.id}
                      checked={val === false}
                      onChange={() => handleValueChange(q.id, false)}
                      className="text-blue-600 focus:ring-blue-500"
                    />
                    <span>No</span>
                  </label>
                </div>
              )}

              <div className="flex justify-end pt-1">
                <button onClick={() => handleApplyChange(q.id, val)} disabled={isGenerating || !cem}
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
