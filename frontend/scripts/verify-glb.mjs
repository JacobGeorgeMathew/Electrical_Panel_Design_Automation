// Verify a real backend-generated asset with the same Three.js loader as R3F.
import { readFile } from 'node:fs/promises';
import assert from 'node:assert/strict';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
const file=await readFile(process.argv[2]);
const data=file.buffer.slice(file.byteOffset,file.byteOffset+file.byteLength);
const gltf=await new GLTFLoader().parseAsync(data,'');
let meshes=0,linked=0;
gltf.scene.traverse(node=>{if(node.isMesh)meshes++;if(node.userData?.cem_component_id)linked++;});
assert(meshes>0,'GLB must contain renderable meshes');
assert(linked>0,'GLB must retain CEM identity metadata');
console.log(JSON.stringify({status:'VALID',meshes,linked_component_nodes:linked}));
