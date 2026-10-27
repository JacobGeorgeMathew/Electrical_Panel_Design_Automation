import React,{Suspense} from 'react';
import { Clone,Html,useGLTF } from '@react-three/drei';

class AssetBoundary extends React.Component<{children:React.ReactNode;fallback:React.ReactNode},{failed:boolean}>{
  state={failed:false};
  static getDerivedStateFromError(){return {failed:true};}
  render(){return this.state.failed?<>{this.props.fallback}<Html center><span className="rounded bg-red-950/90 px-2 text-[10px] text-red-200">3D asset unavailable</span></Html></>:this.props.children;}
}

function LoadedAsset({url,scale}:{url:string;scale:number}){
  const {scene}=useGLTF(url);
  // Clone scene nodes while retaining cached geometry; do not mutate the cached source.
  return <Clone object={scene} scale={scale}/>;
}

export function AssetObject({url,scale=1,fallback=null}:{url:string;scale?:number;fallback?:React.ReactNode}){
  return <AssetBoundary key={url} fallback={fallback}><Suspense fallback={fallback}><LoadedAsset url={url} scale={scale}/></Suspense></AssetBoundary>;
}
