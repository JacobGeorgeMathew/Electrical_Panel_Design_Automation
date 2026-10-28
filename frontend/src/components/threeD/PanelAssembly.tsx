import React, {useEffect,useMemo} from 'react';
import * as THREE from 'three';
import { PhysicalDesignModel, PanelPrimitive, WireRoute } from '../../types/pdm';

export function WireMesh({route,draft,highlighted,dimmed}:{route:WireRoute;draft:boolean;highlighted:boolean;dimmed:boolean}){
  const geometry=useMemo(()=>{
    if(route.waypoints.length<2)return null;
    const path=new THREE.CurvePath<THREE.Vector3>();
    for(let i=1;i<route.waypoints.length;i++){
      const a=route.waypoints[i-1],b=route.waypoints[i];
      path.add(new THREE.LineCurve3(new THREE.Vector3(a.x*.01,a.y*.01,a.z*.01),new THREE.Vector3(b.x*.01,b.y*.01,b.z*.01)));
    }
    return new THREE.TubeGeometry(path,Math.max(16,route.waypoints.length*3),(route.wire_diameter_mm||3)*.005,8,false);
  },[route.waypoints,route.wire_diameter_mm]);
  useEffect(()=>()=>geometry?.dispose(),[geometry]);
  return geometry?<mesh geometry={geometry}><meshStandardMaterial color={draft?'#F59E0B':highlighted?'#60A5FA':route.color_hex}
    roughness={.65} transparent={draft||dimmed} opacity={draft ? 0.35 : dimmed ? 0.18 : 1}/></mesh>:null;
}

export function PrimitiveMesh({primitive:p,selected=false,onSelect}:{primitive:PanelPrimitive;selected?:boolean;onSelect?:(id:string)=>void}){
  const s=.01;
  if(p.type!=='BOX'&&p.type!=='CYLINDER')return null;
  return <group position={[p.position.x*s,p.position.y*s,p.position.z*s]} quaternion={p.rotation_xyzw}>
    <mesh rotation={p.type==='CYLINDER'?[Math.PI/2,0,0]:[0,0,0]} onClick={event=>{if(onSelect&&p.object_id){event.stopPropagation();onSelect(p.object_id);}}}>
      {p.type==='CYLINDER'?<cylinderGeometry args={[(p.radius||1)*s,(p.radius||1)*s,(p.height||1)*s,12]}/>:<boxGeometry args={[p.dimensions!.width*s,p.dimensions!.height*s,p.dimensions!.depth*s]}/>}
      <meshStandardMaterial color={selected?'#60A5FA':p.color} metalness={.35} roughness={.55}/>
    </mesh>
  </group>;
}

export function PanelAssembly({pdm,primitives,doorOpen,showCovers,showBody,selectedId,onSelect}:{
  pdm:PhysicalDesignModel;primitives:PanelPrimitive[];doorOpen:boolean;showCovers:boolean;showBody:boolean;
  selectedId:string|null;onSelect:(id:string)=>void;
}){
  const s=.01;
  const door=pdm.accessories?.find(a=>a.category==='DOOR');
  const pivot:[number,number,number]=[(door?.position.x||0)*s,0,(door?.position.z||pdm.enclosure_depth)*s];
  const mechanical=primitives.filter(p=>p.assembly_group&&p.assembly_group!=='DOOR'&&
    (showCovers||p.assembly_group!=='DUCT_COVER')&&(showBody||p.assembly_group!=='ENCLOSURE'));
  return <>
    {mechanical.map(p=><PrimitiveMesh key={p.id} primitive={p} selected={p.object_id===selectedId} onSelect={onSelect}/>)}
    <group position={pivot} rotation={[0,doorOpen?-Math.PI*105/180:0,0]}>
      <group position={[-pivot[0],-pivot[1],-pivot[2]]}>
        {primitives.filter(p=>p.assembly_group==='DOOR').map(p=><PrimitiveMesh key={p.id} primitive={p} selected={p.object_id===selectedId} onSelect={onSelect}/>)}
      </group>
    </group>
  </>;
}
