import React from 'react';
import { useProjectStore } from '../../stores/projectStore';
import { GitCompare, CheckCircle2, ArrowRight, X } from 'lucide-react';

export const ChangePropagationModal: React.FC = () => {
  const { diffReport, isDiffModalOpen, closeDiffModal } = useProjectStore();

  if (!isDiffModalOpen || !diffReport) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 backdrop-blur-sm p-4 animate-in fade-in duration-200">
      <div className="bg-slate-900 border border-slate-700 rounded-2xl max-w-2xl w-full p-6 shadow-2xl shadow-blue-500/10">
        <div className="flex items-center justify-between border-b border-slate-800 pb-4 mb-4">
          <div className="flex items-center space-x-3">
            <div className="p-2.5 bg-blue-500/10 text-blue-400 border border-blue-500/20 rounded-xl">
              <GitCompare className="w-6 h-6" />
            </div>
            <div>
              <h3 className="text-lg font-bold text-slate-100">Incremental Change Propagation Report</h3>
              <p className="text-xs text-slate-400">
                DAG dependency graph modified node output comparison
              </p>
            </div>
          </div>
          <button
            onClick={closeDiffModal}
            className="p-1.5 text-slate-400 hover:text-white rounded-lg hover:bg-slate-800 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="space-y-3 mb-6">
          {diffReport.diffs.map((item: any, idx: number) => (
            <div
              key={idx}
              className={`p-3.5 rounded-xl border flex items-center justify-between text-xs transition-all ${
                item.changed
                  ? 'bg-blue-500/10 border-blue-500/30 text-slate-200'
                  : 'bg-slate-950/60 border-slate-800 text-slate-400'
              }`}
            >
              <div className="font-medium text-slate-300 w-1/3">{item.property}</div>
              <div className="flex items-center space-x-3 w-2/3 justify-end">
                <span className="px-2.5 py-1 bg-slate-800 border border-slate-700 rounded-md font-mono text-slate-400">
                  {item.before}
                </span>
                <ArrowRight className="w-4 h-4 text-blue-400 flex-shrink-0" />
                <span className="px-2.5 py-1 bg-blue-600/20 text-blue-300 border border-blue-500/40 rounded-md font-mono font-semibold">
                  {item.after}
                </span>
              </div>
            </div>
          ))}
        </div>

        <div className="flex justify-end space-x-3 border-t border-slate-800 pt-4">
          <button
            onClick={closeDiffModal}
            className="flex items-center space-x-2 px-5 py-2.5 bg-blue-600 hover:bg-blue-500 text-white font-semibold text-xs rounded-xl shadow-lg shadow-blue-500/20 transition-all"
          >
            <CheckCircle2 className="w-4 h-4" />
            <span>Accept Regenerated Design</span>
          </button>
        </div>
      </div>
    </div>
  );
};
