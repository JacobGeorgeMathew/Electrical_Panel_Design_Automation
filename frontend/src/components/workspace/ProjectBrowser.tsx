import {Box,ChevronDown,FileText,GitBranch,Layers,Package,Sliders,BookOpen,Eye,EyeOff} from 'lucide-react';
import {useProjectStore,type ViewTab} from '../../stores/projectStore';

export function ProjectBrowser(){
  const {projectName,activeTab,setActiveTab,cem,pdm,selectedObjectId,selectObject,editorHiddenComponentIds,toggleComponentVisibility}=useProjectStore();
  const item=(view:ViewTab,label:string,Icon:typeof Box)=><button className={`browser-item ${activeTab===view?'active':''}`} onClick={()=>setActiveTab(view)}><Icon size={14}/>{label}</button>;
  return <nav aria-label="Project browser" className="project-browser">
    <div className="panel-heading">PROJECT BROWSER</div>
    <div className="browser-project" title={projectName}><Box size={15}/><strong>{projectName}</strong></div>
    {item('requirements','Requirements',Sliders)}
    <details open><summary><ChevronDown size={12}/><GitBranch size={14}/>Electrical design</summary><div className="browser-branch">
      {item('schematic','Electrical schematic',GitBranch)}
      <details open><summary><ChevronDown size={12}/><Package size={14}/>Components <span className="count">{cem?.components.length||0}</span></summary>
        {(cem?.components||[]).map(component=><div key={component.id} className={`browser-component ${selectedObjectId===component.id?'selected':''}`}>
          <button aria-label={`Select ${component.id}`} aria-pressed={selectedObjectId===component.id} title={component.name} onClick={()=>selectObject(component.id)}><span className="object-dot"/><span><b>{component.id}</b><small>{component.name}</small></span></button>
          <button aria-label={`${editorHiddenComponentIds.includes(component.id)?'Show':'Hide'} ${component.id}`} onClick={()=>toggleComponentVisibility(component.id)}>{editorHiddenComponentIds.includes(component.id)?<EyeOff size={12}/>:<Eye size={12}/>}</button>
        </div>)}
        {!cem&&<p className="browser-empty">No generated components</p>}
      </details>
    </div></details>
    <details open><summary><ChevronDown size={12}/><Layers size={14}/>Physical design</summary><div className="browser-branch">
      {item('layout2d','2D physical layout',Layers)}{item('threeD','3D assembly',Box)}
      <details><summary><ChevronDown size={12}/>Rails & ducts <span className="count">{(pdm?.rails.length||0)+(pdm?.ducts?.length||0)}</span></summary>
        {[...(pdm?.rails||[]),...(pdm?.ducts||[])].map(part=><button key={part.id} className={`browser-item ${selectedObjectId===part.id?'selected':''}`} onClick={()=>selectObject(part.id)}>{part.label}</button>)}
      </details>
      <details><summary><ChevronDown size={12}/>Cabinet & accessories</summary>{(pdm?.accessories||[]).map(part=><button key={part.id} className={`browser-item ${selectedObjectId===part.id?'selected':''}`} onClick={()=>selectObject(part.id)}>{part.name}</button>)}</details>
    </div></details>
    {item('bom','Bill of materials',FileText)}{item('documentation','Documentation',BookOpen)}{item('catalog','Component library',Package)}
  </nav>;
}
