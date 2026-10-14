import React, { useState } from 'react';
import { useProjectStore } from '../../stores/projectStore';
import { GitBranch, ZoomIn, ZoomOut, RotateCcw, Filter, Eye } from 'lucide-react';

export const SchematicViewer: React.FC = () => {
  const {
    schematicData,
    selectedObjectId,
    selectObject,
    hoveredObjectId,
    hoverObject
  } = useProjectStore();

  const [zoom, setZoom] = useState<number>(1);
  const [wireFilter, setWireFilter] = useState<'ALL' | 'POWER' | 'NEUTRAL' | 'PE'>('ALL');
  const [activeHoverNet, setActiveHoverNet] = useState<string | null>(null);

  if (!schematicData) {
    return (
      <div className="p-12 text-center text-slate-500 font-mono text-sm">
        No schematic data loaded. Click "Generate Design" to build the schematic diagram.
      </div>
    );
  }

  const { width, height, symbols, wires } = schematicData;

  const filteredWires = wires.filter((w: any) => {
    if (wireFilter === 'ALL') return true;
    return w.wire_class === wireFilter;
  });

  return (
    <div className="flex flex-col h-full bg-slate-950 p-6 space-y-4">
      {/* Schematic Toolbar */}
      <div className="flex items-center justify-between bg-slate-900 border border-slate-800 p-4 rounded-2xl">
        <div className="flex items-center space-x-3">
          <div className="p-2 bg-blue-500/10 text-blue-400 rounded-xl">
            <GitBranch className="w-5 h-5" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-slate-200">Interactive SVG Electrical Schematic</h3>
            <p className="text-xs text-slate-400">Sugiyama hierarchical layout & orthogonal wire net topology</p>
          </div>
        </div>

        <div className="flex items-center space-x-3">
          {/* Wire Class Filters */}
          <div className="flex items-center bg-slate-950 p-1 rounded-xl border border-slate-800 text-xs">
            {(['ALL', 'POWER', 'NEUTRAL', 'PE'] as const).map((filter) => (
              <button
                key={filter}
                onClick={() => setWireFilter(filter)}
                className={`px-3 py-1 rounded-lg transition-all ${
                  wireFilter === filter
                    ? 'bg-blue-600 text-white font-semibold'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                {filter}
              </button>
            ))}
          </div>

          {/* Zoom controls */}
          <div className="flex items-center space-x-1 bg-slate-950 p-1 rounded-xl border border-slate-800">
            <button
              onClick={() => setZoom((z) => Math.min(2, z + 0.15))}
              className="p-1.5 text-slate-400 hover:text-white rounded-lg hover:bg-slate-900"
            >
              <ZoomIn className="w-4 h-4" />
            </button>
            <span className="text-xs font-mono text-slate-300 px-2">{Math.round(zoom * 100)}%</span>
            <button
              onClick={() => setZoom((z) => Math.max(0.5, z - 0.15))}
              className="p-1.5 text-slate-400 hover:text-white rounded-lg hover:bg-slate-900"
            >
              <ZoomOut className="w-4 h-4" />
            </button>
            <button
              onClick={() => setZoom(1)}
              className="p-1.5 text-slate-400 hover:text-white rounded-lg hover:bg-slate-900"
            >
              <RotateCcw className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>

      {/* SVG Canvas Area */}
      <div className="flex-1 bg-slate-900/60 border border-slate-800 rounded-2xl overflow-auto p-6 flex justify-center items-center relative">
        <div style={{ transform: `scale(${zoom})`, transformOrigin: 'top center', transition: 'transform 0.15s ease-out' }}>
          <svg
            width={width}
            height={height}
            viewBox={`0 0 ${width} ${height}`}
            className="select-none font-sans"
          >
            {/* Grid Pattern background */}
            <defs>
              <pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse">
                <path d="M 40 0 L 0 0 0 40" fill="none" stroke="rgba(51, 65, 85, 0.2)" strokeWidth="1" />
              </pattern>
            </defs>
            <rect width={width} height={height} fill="url(#grid)" />

            {/* Render Wires */}
            {filteredWires.map((w: any) => {
              const isSelected = selectedObjectId === w.from || selectedObjectId === w.to;
              const isHovered = activeHoverNet === w.net_id || hoveredObjectId === w.from || hoveredObjectId === w.to;

              return (
                <g key={w.id}>
                  <path
                    d={w.svg_path}
                    fill="none"
                    stroke={isHovered || isSelected ? '#38BDF8' : w.color}
                    strokeWidth={isHovered || isSelected ? 3.5 : 2}
                    strokeDasharray={w.wire_class === 'NEUTRAL' ? '6,3' : 'none'}
                    className="transition-all duration-150 cursor-pointer"
                    onMouseEnter={() => setActiveHoverNet(w.net_id)}
                    onMouseLeave={() => setActiveHoverNet(null)}
                  />
                  {/* Connection Node Dots */}
                  <circle
                    cx={Number(w.svg_path.split(' ')[1])}
                    cy={Number(w.svg_path.split(' ')[2])}
                    r={3}
                    fill={w.color}
                  />
                </g>
              );
            })}

            {/* Render Component Symbols */}
            {symbols.map((sym: any) => {
              const isSelected = selectedObjectId === sym.id;
              const isHovered = hoveredObjectId === sym.id;

              return (
                <g
                  key={sym.id}
                  transform={`translate(${sym.x}, ${sym.y})`}
                  onClick={() => selectObject(sym.id)}
                  onMouseEnter={() => hoverObject(sym.id)}
                  onMouseLeave={() => hoverObject(null)}
                  className="cursor-pointer group"
                >
                  <rect
                    width={sym.width}
                    height={sym.height}
                    rx={6}
                    fill={isSelected ? '#1E3A8A' : isHovered ? '#1E293B' : '#0F172A'}
                    stroke={isSelected ? '#3B82F6' : isHovered ? '#60A5FA' : '#334155'}
                    strokeWidth={isSelected ? 2.5 : 1.5}
                    className="transition-all shadow-lg"
                  />
                  <text
                    x={sym.width / 2}
                    y={sym.height / 2 + 4}
                    textAnchor="middle"
                    fill={isSelected ? '#60A5FA' : '#F8FAFC'}
                    fontSize="11"
                    fontWeight="600"
                    fontFamily="JetBrains Mono"
                  >
                    {sym.label.split('\n')[0]}
                  </text>
                  {sym.label.split('\n')[1] && (
                    <text
                      x={sym.width / 2}
                      y={sym.height / 2 + 18}
                      textAnchor="middle"
                      fill="#94A3B8"
                      fontSize="9"
                      fontFamily="JetBrains Mono"
                    >
                      {sym.label.split('\n')[1]}
                    </text>
                  )}

                  {/* Terminal Pin Connectors */}
                  {sym.terminals?.map((t: any) => (
                    <circle
                      key={t.id}
                      cx={t.x - sym.x}
                      cy={t.y - sym.y}
                      r={3.5}
                      fill="#3B82F6"
                      stroke="#1E293B"
                      strokeWidth={1}
                    />
                  ))}
                </g>
              );
            })}
          </svg>
        </div>
      </div>
    </div>
  );
};
