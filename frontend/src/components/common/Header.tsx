import React from 'react';
import { useProjectStore, ViewTab } from '../../stores/projectStore';
import {
  Zap,
  Sliders,
  GitBranch,
  Layers,
  Box,
  ShieldCheck,
  FileSpreadsheet,
  Play,
  RotateCcw
} from 'lucide-react';

export const Header: React.FC = () => {
  const {
    projectName,
    archetype,
    activeTab,
    setActiveTab,
    isGenerating,
    runDesignPipeline,
    cem,
    selectedObjectId, projectId, isSaving, isLoadingProject
  } = useProjectStore();

  const tabs: { id: ViewTab; label: string; icon: React.ReactNode }[] = [
    { id: 'requirements', label: 'Requirements', icon: <Sliders className="w-4 h-4" /> },
    { id: 'schematic', label: 'Schematic (SVG)', icon: <GitBranch className="w-4 h-4" /> },
    { id: 'layout2d', label: '2D Layout', icon: <Layers className="w-4 h-4" /> },
    { id: 'threeD', label: '3D Panel (R3F)', icon: <Box className="w-4 h-4" /> },
    { id: 'validation', label: 'Validation', icon: <ShieldCheck className="w-4 h-4" /> },
    { id: 'bom', label: 'BOM & Traceability', icon: <FileSpreadsheet className="w-4 h-4" /> },
    { id: 'catalog', label: 'Catalog', icon: <Box className="w-4 h-4" /> },
  ];

  return (
    <header className="bg-slate-900/90 backdrop-blur border-b border-slate-800 sticky top-0 z-50 px-6 py-3">
      <div className="max-w-7xl mx-auto flex flex-wrap gap-3 items-center justify-between">
        {/* Left branding */}
        <div className="flex items-center space-x-4">
          <div className="p-2 bg-gradient-to-tr from-blue-600 to-cyan-500 rounded-xl shadow-lg shadow-blue-500/20 text-white">
            <Zap className="w-6 h-6" />
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <h1 className="font-bold text-lg text-slate-100 tracking-tight">{projectName}</h1>
              <span className="px-2 py-0.5 text-xs font-semibold bg-blue-500/10 text-blue-400 border border-blue-500/20 rounded-full">
                Archetype: {archetype}
              </span>
              {cem?.state && (
                <span className="px-2 py-0.5 text-xs font-mono bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 rounded-full">
                  {cem.state}
                </span>
              )}
            </div>
            <p className="text-xs text-slate-400 font-mono mt-0.5">
              CEM: Canonical Engineering Model • PDM: Physical Design Model
            </p>
          </div>
        </div>

        {/* Center Tab Navigation */}
        <nav className="flex flex-wrap items-center gap-1 bg-slate-950 p-1.5 rounded-xl border border-slate-800">
          {tabs.map((t) => (
            <button
              key={t.id}
              onClick={() => setActiveTab(t.id)}
              className={`flex items-center space-x-2 px-3.5 py-1.5 rounded-lg text-xs font-medium transition-all ${
                activeTab === t.id
                  ? 'bg-blue-600 text-white shadow-md shadow-blue-500/25 font-semibold'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900'
              }`}
            >
              {t.icon}
              <span>{t.label}</span>
            </button>
          ))}
        </nav>

        {/* Right Actions */}
        <div className="flex items-center space-x-3">
          {selectedObjectId && (
            <span className="text-xs px-2.5 py-1 bg-cyan-500/10 text-cyan-300 border border-cyan-500/30 rounded-lg font-mono">
              Selected: <strong className="text-white">{selectedObjectId}</strong>
            </span>
          )}
          <button
            onClick={() => runDesignPipeline()}
            disabled={isGenerating || !projectId || isSaving || isLoadingProject}
            className="flex items-center space-x-2 px-4 py-2 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white text-xs font-semibold rounded-xl shadow-lg shadow-blue-600/30 transition-all disabled:opacity-50"
          >
            {isGenerating ? (
              <RotateCcw className="w-4 h-4 animate-spin" />
            ) : (
              <Play className="w-4 h-4 fill-current" />
            )}
            <span>{isGenerating ? 'Orchestrating...' : 'Generate Design'}</span>
          </button>
        </div>
      </div>
    </header>
  );
};
