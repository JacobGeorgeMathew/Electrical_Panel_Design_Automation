"""Managed immutable files and the existing primitive CAD adapter's GLB exporter."""
import hashlib
import json
import os
import struct
import tempfile
from pathlib import Path


class AssetUnavailable(RuntimeError):
    pass


class AssetStore:
    def __init__(self, root: Path):
        self.root = root.resolve()

    def put(self, data: bytes, extension: str) -> dict:
        if extension not in {"glb", "json", "py", "step", "fcstd", "pdf"}:
            raise ValueError("Unsupported managed asset format.")
        digest = hashlib.sha256(data).hexdigest()
        key = f"sha256/{digest[:2]}/{digest[2:4]}/{digest}.{extension}"
        target = self.root / key
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            fd, temporary = tempfile.mkstemp(prefix=".pending-", dir=target.parent)
            try:
                with os.fdopen(fd, "wb") as stream:
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, target)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
        self.verified_path(key, digest, len(data))
        return {"storage_backend": "LOCAL", "storage_key": key, "sha256": digest, "byte_size": len(data)}

    def verified_path(self, key: str, digest: str, size: int | None = None) -> Path:
        if not key or not digest:
            raise AssetUnavailable("Asset metadata is incomplete.")
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root) or not path.is_file():
            raise AssetUnavailable("Asset file is unavailable.")
        if size is not None and path.stat().st_size != size:
            raise AssetUnavailable("Asset integrity check failed.")
        hasher = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                hasher.update(chunk)
        if hasher.hexdigest() != digest:
            raise AssetUnavailable("Asset integrity check failed.")
        return path

    def availability(self, row) -> str:
        try:
            self.verified_path(row.get("storage_key"), row.get("sha256"), row.get("byte_size"))
            return "READY"
        except AssetUnavailable:
            return "MISSING_OR_CORRUPT"


def canonical_json(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def content_hash(value) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def primitive_glb(primitives: list[dict]) -> bytes:
    """Tessellate existing BOX primitives; routes remain GLB line segments.

    CAD/PDM inputs are mm. glTF positions and translations are metres. Meshes are
    centred, with identity axes matching the existing right-handed PDM convention.
    This is a visualization export, not a solid or FreeCAD feature history.
    """
    binary = bytearray()
    doc = {"asset": {"version": "2.0", "generator": "panelstudio-primitives/1"},
           "scene": 0, "scenes": [{"nodes": []}], "nodes": [], "meshes": [],
           "materials": [], "buffers": [], "bufferViews": [], "accessors": []}

    def buffer(values, code, component_type, accessor_type, count, bounds=None):
        while len(binary) % 4:
            binary.append(0)
        start = len(binary)
        binary.extend(struct.pack("<" + code * len(values), *values))
        view = len(doc["bufferViews"])
        doc["bufferViews"].append({"buffer": 0, "byteOffset": start, "byteLength": len(binary)-start})
        accessor = {"bufferView": view, "componentType": component_type, "count": count, "type": accessor_type}
        if bounds:
            accessor.update({"min": bounds[0], "max": bounds[1]})
        doc["accessors"].append(accessor)
        return len(doc["accessors"])-1

    for item in primitives:
        kind = item["type"]
        position = item.get("position", {"x": 0, "y": 0, "z": 0})
        if kind == "BOX":
            dims = item["dimensions"]
            x, y, z = [float(dims[k])/2000 for k in ("width", "height", "depth")]
            if min(x, y, z) <= 0:
                raise ValueError("Preview box dimensions must be positive.")
            # Independent face vertices preserve hard edges and correct lighting.
            faces = [((0,0,1),[(-x,-y,z),(x,-y,z),(x,y,z),(-x,y,z)]),
                     ((0,0,-1),[(x,-y,-z),(-x,-y,-z),(-x,y,-z),(x,y,-z)]),
                     ((1,0,0),[(x,-y,z),(x,-y,-z),(x,y,-z),(x,y,z)]),
                     ((-1,0,0),[(-x,-y,-z),(-x,-y,z),(-x,y,z),(-x,y,-z)]),
                     ((0,1,0),[(-x,y,z),(x,y,z),(x,y,-z),(-x,y,-z)]),
                     ((0,-1,0),[(-x,-y,-z),(x,-y,-z),(x,-y,z),(-x,-y,z)])]
            verts = [c for _, points in faces for point in points for c in point]
            normals = [c for normal, points in faces for _ in points for c in normal]
            indices = [4*f+i for f in range(6) for i in (0,1,2,0,2,3)]
            attributes = {"POSITION": buffer(verts,"f",5126,"VEC3",24,([-x,-y,-z],[x,y,z])),
                          "NORMAL": buffer(normals,"f",5126,"VEC3",24)}
            index = buffer(indices,"H",5123,"SCALAR",36)
            mode = 4
        elif kind == "TUBE":
            points = item.get("points", [])
            if len(points) < 2:
                continue
            coords = [[float(p[k])/1000 for k in ("x","y","z")] for p in points]
            verts = [c for point in coords for c in point]
            attributes = {"POSITION": buffer(verts,"f",5126,"VEC3",len(coords),
                ([min(p[i] for p in coords) for i in range(3)], [max(p[i] for p in coords) for i in range(3)]))}
            index = buffer(list(range(len(coords))),"I",5125,"SCALAR",len(coords))
            mode = 3
        else:
            continue
        color = item.get("color", "#94a3b8").lstrip("#")
        rgb = [int(color[i:i+2],16)/255 for i in (0,2,4)]
        opacity = float(item.get("opacity",1))
        doc["materials"].append({"pbrMetallicRoughness": {"baseColorFactor":rgb+[opacity],"metallicFactor":0.2,"roughnessFactor":0.65},
                                 "alphaMode":"BLEND" if opacity < 1 else "OPAQUE", "doubleSided":True})
        doc["meshes"].append({"primitives":[{"attributes":attributes,"indices":index,"material":len(doc["materials"])-1,"mode":mode}]})
        node = {"name":item.get("name",item.get("id","part")),"mesh":len(doc["meshes"])-1,
                "translation":[float(position[k])/1000 for k in ("x","y","z")],
                "extras":{k:item[k] for k in ("id","pdm_component_id","cem_component_id","route_id","net_id") if k in item}}
        if item.get("rotation_xyzw"):
            node["rotation"] = item["rotation_xyzw"]
        doc["nodes"].append(node)
        doc["scenes"][0]["nodes"].append(len(doc["nodes"])-1)
    doc["buffers"]=[{"byteLength":len(binary)}]
    json_bytes=canonical_json(doc)
    json_bytes += b" " * (-len(json_bytes)%4)
    binary += b"\0" * (-len(binary)%4)
    return (struct.pack("<III",0x46546C67,2,12+8+len(json_bytes)+8+len(binary))+
            struct.pack("<II",len(json_bytes),0x4E4F534A)+json_bytes+
            struct.pack("<II",len(binary),0x004E4942)+binary)
