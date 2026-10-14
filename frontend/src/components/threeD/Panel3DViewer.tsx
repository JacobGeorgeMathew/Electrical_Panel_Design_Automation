import React, { useRef } from 'react';
import { Canvas } from '@react-three/fiber';
import { OrbitControls, Text, Html } from '@react-three/drei';
import { useProjectStore } from '../../stores/projectStore';
import { Box, Layers, Maximize2, Sparkles } from 'lucide-react';
import * as THREE from 'three';

const ComponentMesh: React.FC<{
  comp: any;
  isSelected: boolean;
  isHovered: boolean;
  exploded: boolean;
  onSelect: (id: string) => void;
  onHover: (id: string | null) => void;
  encHeight: number;
}> = ({ comp, isSelected, isHovered, exploded, onSelect, onHover, encHeight }) => {
  const meshRef = useRef<THREE.Mesh>(null);

  // Convert mm to 3D Scene scale (1 unit = 100mm)
  const scale = 0.01;
  const w = comp.width * scale;
  const h = comp.height * scale;
  const d = comp.depth * scale;

  // Center coordinate mapping
  const posX = (comp.position.x + comp.width / 2) * scale;
  const posY = (comp.position.y + comp.height / 2) * scale;
  // Exploded displacement along Z-axis
  const explodedZOffset = exploded ? (comp.category === 'MCCB' ? 1.5 : 0.8) : 0;
  const posZ = (comp.position.z + comp.depth / 2) * scale + explodedZOffset;

  const rawId = comp.cem_component_id;

  return (
    <group position={[posX, posY, posZ]}>
      <mesh
        ref={meshRef}
        onClick={(e) => {
          e.stopPropagation();
          onSelect(rawId);
        }}
        onPointerOver={(e) => {
          e.stopPropagation();
          onHover(rawId);
        }}
        onPointerOut={() => onHover(null)}
      >
        <boxGeometry args={[w, h, d]} />
        <meshStandardMaterial
          color={isSelected ? '#3B82F6' : isHovered ? '#60A5FA' : comp.color_hex}
          metalness={0.4}
          roughness={0.3}
          emissive={isSelected ? '#1D4ED8' : '#000000'}
          emissiveIntensity={isSelected ? 0.4 : 0}
        />
      </mesh>

      {/* Text Label on Front Face of Component */}
      <Text
        position={[0, 0, d / 2 + 0.01]}
        fontSize={Math.min(w * 0.25, 0.12)}
        color="#FFFFFF"
        anchorX="center"
        anchorY="middle"
      >
        {rawId}
      </Text>
    </group>
  );
};

export const Panel3DViewer: React.FC = () => {
  const {
    pdm,
    selectedObjectId,
    selectObject,
    hoveredObjectId,
    hoverObject,
    explodedView,
    toggleExplodedView,
    wireVisibility,
    toggleWireVisibility
  } = useProjectStore();

  if (!pdm) {
    return (
      <div className="p-12 text-center text-slate-500 font-mono text-sm">
        No 3D panel model loaded. Click "Generate Design" to create the 3D panel.
      </div>
    );
  }

  const scale = 0.01;
  const encW = pdm.enclosure_width * scale;
  const encH = pdm.enclosure_height * scale;
  const encD = pdm.enclosure_depth * scale;

  return (
    <div className="flex flex-col h-full bg-slate-950 p-6 space-y-4">
      {/* 3D Control Bar */}
      <div className="flex items-center justify-between bg-slate-900 border border-slate-800 p-4 rounded-2xl">
        <div className="flex items-center space-x-3">
          <div className="p-2 bg-blue-500/10 text-blue-400 rounded-xl">
            <Box className="w-5 h-5" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-slate-200">Interactive Parametric 3D Panel View</h3>
            <p className="text-xs text-slate-400">
              React Three Fiber (Three.js) • Orbit, Zoom, Exploded Assembly & Component Selection
            </p>
          </div>
        </div>

        <div className="flex items-center space-x-3 text-xs">
          <button
            onClick={toggleExplodedView}
            className={`flex items-center space-x-2 px-3 py-1.5 rounded-xl border transition-all ${
              explodedView
                ? 'bg-blue-600 text-white font-semibold border-blue-500 shadow-md'
                : 'bg-slate-950 text-slate-300 border-slate-800 hover:bg-slate-900'
            }`}
          >
            <Sparkles className="w-3.5 h-3.5" />
            <span>Exploded Assembly View</span>
          </button>
          <button
            onClick={toggleWireVisibility}
            className={`flex items-center space-x-2 px-3 py-1.5 rounded-xl border transition-all ${
              wireVisibility
                ? 'bg-blue-600 text-white font-semibold border-blue-500 shadow-md'
                : 'bg-slate-950 text-slate-300 border-slate-800 hover:bg-slate-900'
            }`}
          >
            <Layers className="w-3.5 h-3.5" />
            <span>3D Wire Routes</span>
          </button>
        </div>
      </div>

      {/* 3D Canvas Area */}
      <div className="flex-1 bg-slate-900/60 border border-slate-800 rounded-2xl overflow-hidden relative">
        <Canvas
          camera={{ position: [encW * 1.5, encH * 1.2, encD * 4], fov: 45 }}
          className="w-full h-full"
        >
          <ambientLight intensity={0.7} />
          <directionalLight position={[10, 10, 10]} intensity={1.2} />
          <pointLight position={[-10, -10, 5]} intensity={0.5} />

          <OrbitControls makeDefault target={[encW / 2, encH / 2, encD / 2]} />

          {/* Enclosure Frame */}
          <mesh position={[encW / 2, encH / 2, encD / 2]}>
            <boxGeometry args={[encW, encH, encD]} />
            <meshStandardMaterial color="#1E293B" wireframe transparent opacity={0.3} />
          </mesh>

          {/* Backplate */}
          <mesh position={[encW / 2, encH / 2, 0.05]}>
            <boxGeometry args={[encW - 0.4, encH - 0.4, 0.03]} />
            <meshStandardMaterial color="#64748B" metalness={0.8} roughness={0.2} />
          </mesh>

          {/* DIN Rails */}
          {pdm.rails.map((rail) => (
            <mesh
              key={rail.id}
              position={[(rail.x + rail.length / 2) * scale, rail.y * scale, rail.z * scale]}
            >
              <boxGeometry args={[rail.length * scale, 0.35, 0.08]} />
              <meshStandardMaterial color="#94A3B8" metalness={0.9} roughness={0.1} />
            </mesh>
          ))}

          {/* Component Meshes */}
          {pdm.components.map((comp) => (
            <ComponentMesh
              key={comp.id}
              comp={comp}
              isSelected={selectedObjectId === comp.cem_component_id || selectedObjectId === comp.id}
              isHovered={hoveredObjectId === comp.cem_component_id || hoveredObjectId === comp.id}
              exploded={explodedView}
              onSelect={selectObject}
              onHover={hoverObject}
              encHeight={pdm.enclosure_height}
            />
          ))}
        </Canvas>
      </div>
    </div>
  );
};
