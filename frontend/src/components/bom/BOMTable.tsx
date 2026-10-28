import React from 'react';
import { useProjectStore } from '../../stores/projectStore';
import { fetchFreeCADScript } from '../../api/client';
import { FileSpreadsheet, Download, Code, ExternalLink, CheckCircle } from 'lucide-react';

export const BOMTable: React.FC = () => {
  const { cem, pdm, projectId, selectObject, setActiveTab, selectedObjectId } = useProjectStore();

  if (!cem || !cem.components) {
    return (
      <div className="p-12 text-center text-slate-500 font-mono text-sm">
        No BOM data loaded. Click "Generate Design" to build the bill of materials.
      </div>
    );
  }

  const handleDownloadScript = async () => {
    try {
      const res = await fetchFreeCADScript(projectId);
      const blob = new Blob([res.script], { type: 'text/plain;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `freecad_panel_${projectId}.py`;
      a.click();
    } catch (err) {
      console.error(err);
    }
  };

  const components = cem.components;
  const hardware=[...(pdm?.accessories||[]).map(a=>({id:a.id,code:a.catalog_id,name:a.name,detail:`${a.width} × ${a.height} × ${a.depth} mm`})),
    ...(pdm?.ducts||[]).map(d=>({id:d.id,code:d.catalog_id,name:d.label+' with cover',detail:`Cut ${d.orientation==='VERTICAL'?d.height:d.width} mm · ${d.capacity_pct}% fill`})),
    ...(pdm?.rails||[]).map(r=>({id:r.id,code:'DIN_RAIL_35',name:r.label,detail:`Cut ${r.length} mm`}))];

  return (
    <div className="max-w-6xl mx-auto p-6 space-y-6">
      {/* Header Bar */}
      <div className="flex items-center justify-between bg-slate-900 border border-slate-800 p-6 rounded-2xl shadow-xl">
        <div className="space-y-1">
          <div className="flex items-center space-x-2">
            <FileSpreadsheet className="w-5 h-5 text-blue-400" />
            <h2 className="text-xl font-bold text-slate-100">Bill of Materials & Engineering Traceability</h2>
          </div>
          <p className="text-xs text-slate-400">
            Canonical Engineering Model (CEM) structured BOM linked with physical CAD step definitions
          </p>
        </div>

        <button
          onClick={handleDownloadScript}
          className="flex items-center space-x-2 px-4 py-2 bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white font-semibold text-xs rounded-xl shadow-lg shadow-emerald-500/20 transition-all"
        >
          <Code className="w-4 h-4" />
          <span>Export FreeCAD Script</span>
        </button>
      </div>

      {/* BOM Table */}
      <div className="bg-slate-900 border border-slate-800 rounded-2xl overflow-hidden shadow-xl">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-950 text-slate-400 font-mono border-b border-slate-800 uppercase tracking-wider">
              <tr>
                <th className="p-4">Item ID</th>
                <th className="p-4">Catalog Part No.</th>
                <th className="p-4">Description</th>
                <th className="p-4">Category</th>
                <th className="p-4">Rating</th>
                <th className="p-4">Dimensions (WxHxD mm)</th>
                <th className="p-4">Heat Loss</th>
                <th className="p-4">Physical ID / Position (mm)</th>
                <th className="p-4 text-center">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800 text-slate-200 font-mono">
              {components.map((comp) => {
                const isSelected = selectedObjectId === comp.id;
                return (
                  <tr
                    key={comp.id}
                    onClick={() => selectObject(comp.id)}
                    className={`cursor-pointer transition-colors ${
                      isSelected ? 'bg-blue-600/20 text-white' : 'hover:bg-slate-800/50'
                    }`}
                  >
                    <td className="p-4 font-bold text-blue-400">{comp.id}</td>
                    <td className="p-4 font-semibold text-slate-300">{comp.catalog_id}</td>
                    <td className="p-4 font-sans font-medium text-slate-200">{comp.name}</td>
                    <td className="p-4">
                      <span className="px-2 py-0.5 bg-slate-800 border border-slate-700 rounded text-[10px] text-slate-300">
                        {comp.category}
                      </span>
                    </td>
                    <td className="p-4 text-emerald-400">{comp.current_rating}A</td>
                    <td className="p-4 text-slate-400">
                      {comp.width} x {comp.height} x {comp.depth}
                    </td>
                    <td className="p-4 text-amber-400">{comp.heat_loss} W</td>
                    <td className="p-4 text-slate-400">
                      {(() => {
                        const placed = pdm?.components.find((item) => item.cem_component_id === comp.id);
                        return placed ? `${placed.id} · (${placed.position.x}, ${placed.position.y}, ${placed.position.z})` : 'Not placed';
                      })()}
                    </td>
                    <td className="p-4 text-center">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          selectObject(comp.id);
                          setActiveTab('layout2d');
                        }}
                        className="px-2.5 py-1 bg-slate-800 hover:bg-slate-700 border border-slate-700 rounded text-[10px] text-slate-300 transition-colors"
                      >
                        Highlight
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
      {hardware.length>0&&<section className="rounded-xl border border-slate-800 bg-slate-900 p-4"><h3 className="mb-3 font-semibold text-slate-100">Enclosure, ducts and accessories</h3><table className="w-full text-left text-xs"><thead className="text-slate-400"><tr><th className="p-2">Part</th><th className="p-2">Catalog</th><th className="p-2">Quantity / dimensions</th></tr></thead><tbody>{hardware.map(a=><tr key={a.id} onClick={()=>{selectObject(a.id);setActiveTab('threeD');}} className="cursor-pointer border-t border-slate-800 hover:bg-slate-800"><td className="p-2">{a.name}</td><td className="p-2 font-mono text-blue-300">{a.code}</td><td className="p-2">1 · {a.detail}</td></tr>)}</tbody></table></section>}
    </div>
  );
};
