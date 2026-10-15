import React from 'react';
import { useProjectStore } from '../../stores/projectStore';
import { ShieldCheck, AlertOctagon, AlertTriangle, Info, Flame, Thermometer, CheckCircle2 } from 'lucide-react';

export const ValidationPanel: React.FC = () => {
  const { pdm, cem, selectObject, setActiveTab } = useProjectStore();

  if (!pdm) {
    return (
      <div className="p-12 text-center text-slate-500 font-mono text-sm">
        No validation report available. Click "Generate Design" to run the physical validation engine.
      </div>
    );
  }

  const violations = pdm.validation_results || [];
  const thermalIndex = pdm.thermal_density_index || 0;
  const totalHeat = pdm.total_heat_loss_watts || 0;

  const handleViolationClick = (objId: string) => {
    if (objId && objId !== 'ENCLOSURE') {
      selectObject(objId);
      setActiveTab('layout2d');
    }
  };

  return (
    <div className="max-w-5xl mx-auto p-6 space-y-6">
      {/* Header Summary Card */}
      <div className="flex items-center justify-between bg-slate-900 border border-slate-800 p-6 rounded-2xl shadow-xl">
        <div className="space-y-1">
          <div className="flex items-center space-x-2">
            <ShieldCheck className="w-5 h-5 text-emerald-400" />
            <h2 className="text-xl font-bold text-slate-100">Physical & Thermal Design Validation</h2>
          </div>
          <p className="text-xs text-slate-400">
            Simplified geometry, identity, and thermal-density checks for this prototype design
          </p>
        </div>

        <div className="flex items-center space-x-4">
          <div className="p-3 bg-slate-950 border border-slate-800 rounded-xl space-y-0.5 text-right">
            <div className="text-[10px] text-slate-400 font-mono">Heat Dissipation</div>
            <div className="text-base font-bold font-mono text-amber-400">{totalHeat} W</div>
          </div>
          <div className="p-3 bg-slate-950 border border-slate-800 rounded-xl space-y-0.5 text-right">
            <div className="text-[10px] text-slate-400 font-mono">Thermal Density</div>
            <div
              className={`text-base font-bold font-mono ${
                thermalIndex > 0.45 ? 'text-amber-400' : 'text-emerald-400'
              }`}
            >
              {thermalIndex} W/L
            </div>
          </div>
        </div>
      </div>

      {/* Validation Checks Table / List */}
      <div className="bg-slate-900 border border-slate-800 rounded-2xl overflow-hidden shadow-lg space-y-4 p-6">
        <h3 className="text-sm font-bold text-slate-200">Rule Violation Reports ({violations.length})</h3>

        {violations.length === 0 ? (
          <div className="p-8 bg-emerald-500/10 border border-emerald-500/20 rounded-xl flex items-center space-x-3 text-emerald-300">
            <CheckCircle2 className="w-6 h-6 flex-shrink-0" />
            <div>
              <div className="font-semibold text-sm">All Design Constraints Passed Cleanly!</div>
              <div className="text-xs text-emerald-400/80">
                No critical component overlap or boundary issues were reported by the implemented checks.
              </div>
            </div>
          </div>
        ) : (
          <div className="space-y-3">
            {violations.map((v: any, idx: number) => (
              <div
                key={idx}
                onClick={() => handleViolationClick(v.object_a)}
                className={`p-4 rounded-xl border flex items-center justify-between cursor-pointer transition-all hover:scale-[1.005] ${
                  v.severity === 'CRITICAL'
                    ? 'bg-rose-500/10 border-rose-500/30 text-rose-200'
                    : 'bg-amber-500/10 border-amber-500/30 text-amber-200'
                }`}
              >
                <div className="flex items-center space-x-3">
                  {v.severity === 'CRITICAL' ? (
                    <AlertOctagon className="w-5 h-5 text-rose-400 flex-shrink-0" />
                  ) : (
                    <AlertTriangle className="w-5 h-5 text-amber-400 flex-shrink-0" />
                  )}
                  <div>
                    <div className="font-semibold text-xs flex items-center space-x-2">
                      <span>[{v.type}]</span>
                      <span className="text-slate-100">{v.message}</span>
                    </div>
                    <div className="text-[10px] opacity-75 font-mono mt-0.5">
                      Required: {v.required_value}{v.unit} • Actual: {v.actual_value}{v.unit}
                    </div>
                  </div>
                </div>

                <button className="px-3 py-1 bg-slate-900 border border-slate-700 text-slate-300 rounded-lg text-xs font-mono hover:bg-slate-800">
                  Locate & Zoom
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
