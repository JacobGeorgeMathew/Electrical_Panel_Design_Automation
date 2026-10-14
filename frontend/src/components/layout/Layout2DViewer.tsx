import React, { useState } from 'react';
import { useProjectStore } from '../../stores/projectStore';
import { Layers, Eye, ShieldAlert, Cpu } from 'lucide-react';

export const Layout2DViewer: React.FC = () => {
  const { pdm, selectedObjectId, selectObject, hoveredObjectId, hoverObject } = useProjectStore();
  const [showZones, setShowZones] = useState<boolean>(true);
  const [showRoutes, setShowRoutes] = useState<boolean>(true);

  if (!pdm) {
    return (
      <div className="p-12 text-center text-slate-500 font-mono text-sm">
        No PDM physical layout loaded. Click "Generate Design" to create the 2D layout.
      </div>
    );
  }

  const { enclosure_width, enclosure_height, zones, components, rails, routes } = pdm;

  return (
    <div className="flex flex-col h-full bg-slate-950 p-6 space-y-4">
      {/* 2D Toolbar */}
      <div className="flex items-center justify-between bg-slate-900 border border-slate-800 p-4 rounded-2xl">
        <div className="flex items-center space-x-3">
          <div className="p-2 bg-blue-500/10 text-blue-400 rounded-xl">
            <Layers className="w-5 h-5" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-slate-200">Interactive 2D Physical Panel Layout</h3>
            <p className="text-xs text-slate-400">
              Enclosure ({enclosure_width} x {enclosure_height} mm) • CP-SAT DIN Rail Placements
            </p>
          </div>
        </div>

        <div className="flex items-center space-x-3 text-xs">
          <label className="flex items-center space-x-2 text-slate-300 cursor-pointer bg-slate-950 px-3 py-1.5 rounded-xl border border-slate-800">
            <input
              type="checkbox"
              checked={showZones}
              onChange={(e) => setShowZones(e.target.checked)}
              className="text-blue-600 rounded"
            />
            <span>Show Functional Zones</span>
          </label>
          <label className="flex items-center space-x-2 text-slate-300 cursor-pointer bg-slate-950 px-3 py-1.5 rounded-xl border border-slate-800">
            <input
              type="checkbox"
              checked={showRoutes}
              onChange={(e) => setShowRoutes(e.target.checked)}
              className="text-blue-600 rounded"
            />
            <span>Show Wire Routes</span>
          </label>
        </div>
      </div>

      {/* SVG Layout Canvas */}
      <div className="flex-1 bg-slate-900/60 border border-slate-800 rounded-2xl overflow-auto p-6 flex justify-center items-center relative">
        <svg
          width={enclosure_width * 0.85}
          height={enclosure_height * 0.85}
          viewBox={`0 0 ${enclosure_width} ${enclosure_height}`}
          className="select-none"
        >
          {/* Enclosure Boundary Box */}
          <rect
            x={0}
            y={0}
            width={enclosure_width}
            height={enclosure_height}
            fill="#0B0F19"
            stroke="#334155"
            strokeWidth={4}
            rx={10}
          />

          {/* Mounting Backplate */}
          <rect
            x={30}
            y={30}
            width={enclosure_width - 60}
            height={enclosure_height - 60}
            fill="#1E293B"
            stroke="#475569"
            strokeWidth={2}
            rx={6}
          />

          {/* Render Functional Zones */}
          {showZones &&
            zones.map((zone, idx) => (
              <g key={zone.name}>
                <rect
                  x={zone.x_min}
                  y={enclosure_height - zone.y_max}
                  width={zone.x_max - zone.x_min}
                  height={zone.y_max - zone.y_min}
                  fill={`hsla(${idx * 60}, 70%, 50%, 0.08)`}
                  stroke={`hsla(${idx * 60}, 70%, 50%, 0.3)`}
                  strokeWidth={1.5}
                  strokeDasharray="5,5"
                />
                <text
                  x={zone.x_min + 10}
                  y={enclosure_height - zone.y_max + 18}
                  fill={`hsla(${idx * 60}, 70%, 60%, 0.9)`}
                  fontSize="10"
                  fontWeight="bold"
                  fontFamily="JetBrains Mono"
                >
                  ZONE: {zone.name}
                </text>
              </g>
            ))}

          {/* DIN Rails */}
          {rails.map((rail) => (
            <g key={rail.id}>
              <rect
                x={rail.x}
                y={enclosure_height - rail.y - 17.5}
                width={rail.length}
                height={35}
                fill="#475569"
                stroke="#64748B"
                strokeWidth={1}
                rx={2}
              />
              <text
                x={rail.x + 10}
                y={enclosure_height - rail.y - 3}
                fill="#94A3B8"
                fontSize="9"
                fontFamily="JetBrains Mono"
              >
                {rail.label}
              </text>
            </g>
          ))}

          {/* Wire Routes (JPS-Theta*) */}
          {showRoutes &&
            routes.map((route) => {
              if (route.waypoints.length < 2) return null;
              const points = route.waypoints
                .map((wp) => `${wp.x},${enclosure_height - wp.y}`)
                .join(' ');
              return (
                <polyline
                  key={route.id}
                  points={points}
                  fill="none"
                  stroke={route.color_hex}
                  strokeWidth={2.5}
                  strokeOpacity={0.7}
                  strokeDasharray={route.wire_class === 'NEUTRAL' ? '4,4' : 'none'}
                />
              );
            })}

          {/* Components */}
          {components.map((comp) => {
            const rawId = comp.cem_component_id;
            const isSelected = selectedObjectId === rawId || selectedObjectId === comp.id;
            const isHovered = hoveredObjectId === rawId || hoveredObjectId === comp.id;

            return (
              <g
                key={comp.id}
                transform={`translate(${comp.position.x}, ${enclosure_height - comp.position.y - comp.height})`}
                onClick={() => selectObject(rawId)}
                onMouseEnter={() => hoverObject(rawId)}
                onMouseLeave={() => hoverObject(null)}
                className="cursor-pointer"
              >
                <rect
                  width={comp.width}
                  height={comp.height}
                  rx={4}
                  fill={isSelected ? '#1E40AF' : isHovered ? '#1E293B' : comp.color_hex}
                  fillOpacity={isSelected ? 0.95 : 0.85}
                  stroke={isSelected ? '#60A5FA' : '#1E293B'}
                  strokeWidth={isSelected ? 3 : 1}
                  className="transition-all shadow-md"
                />
                <text
                  x={comp.width / 2}
                  y={comp.height / 2 + 3}
                  textAnchor="middle"
                  fill="#FFFFFF"
                  fontSize="10"
                  fontWeight="bold"
                  fontFamily="JetBrains Mono"
                >
                  {rawId}
                </text>
              </g>
            );
          })}
        </svg>
      </div>
    </div>
  );
};
