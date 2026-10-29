"""Circular corner sampling for physical wire previews; no unconstrained splines.

Polyline remains authoritative. Sampling error is bounded by chord sagitta and
included in the tube clearance envelope. Unknown manufacturer bend limits remain
UNRESOLVED rather than being invented from an estimated insulation diameter.
"""
import math
from app.models.pdm import WireGeometry, Waypoint3D


def length(points): return sum(math.dist(a,b) for a,b in zip(points,points[1:]))
def sub(a,b):return tuple(x-y for x,y in zip(a,b))
def add(a,b):return tuple(x+y for x,y in zip(a,b))
def mul(a,t):return tuple(x*t for x in a)
def unit(a):return mul(a,1/math.sqrt(sum(x*x for x in a)))
def dot(a,b):return sum(x*y for x,y in zip(a,b))


def circular_centerline(points, minimum_radius=None, preview_radius=6):
    clean=[]
    for p in points:
        p=tuple(p)
        if len(p)!=3 or not all(math.isfinite(v) for v in p):raise ValueError('Wire coordinates must be finite 3D millimetres.')
        if not clean or math.dist(p,clean[-1])>1e-7:clean.append(p)
    if len(clean)<2:raise ValueError('A wire needs two distinct points.')
    output=[clean[0]];radii=[]
    for a,b,c in zip(clean,clean[1:],clean[2:]):
        u=unit(sub(a,b));v=unit(sub(c,b));cos=max(-1,min(1,dot(u,v)))
        angle=math.acos(cos)
        if angle>math.pi-1e-6:continue
        if angle<1e-6:raise ValueError('A wire reverses direction at a corner.')
        tangent=math.tan(angle/2)
        available=.45*min(math.dist(a,b),math.dist(b,c))*tangent
        radius=minimum_radius if minimum_radius is not None else min(preview_radius,available)
        if radius>available+1e-6:raise ValueError(f'Minimum bend radius {radius:g} mm cannot fit; available {available:g} mm.')
        trim=radius/tangent;entry=add(b,mul(u,trim));exit=add(b,mul(v,trim))
        center=add(b,mul(unit(add(u,v)),radius/math.sin(angle/2)))
        e=unit(sub(entry,center));f=unit(sub(exit,center));sweep=math.acos(max(-1,min(1,dot(e,f))))
        axis=unit(sub(f,mul(e,math.cos(sweep))))
        output.append(entry)
        steps=max(2,math.ceil(sweep/(math.pi/24)))
        for k in range(1,steps+1):
            t=sweep*k/steps;output.append(add(center,mul(add(mul(e,math.cos(t)),mul(axis,math.sin(t))),radius)))
        radii.append(radius)
    output.append(clean[-1]);return output,radii


def segment_hits_box(a,b,lo,hi):
    t0,t1=0.,1.
    for k in range(3):
        delta=b[k]-a[k]
        if abs(delta)<1e-12:
            if a[k]<lo[k] or a[k]>hi[k]:return False
        else:
            near,far=sorted(((lo[k]-a[k])/delta,(hi[k]-a[k])/delta))
            t0=max(t0,near);t1=min(t1,far)
            if t0>t1:return False
    return True


def build_wire_geometry(route,pdm):
    original=[(p.x,p.y,p.z) for p in route.waypoints]
    if route.wire_diameter_mm<=0 or not math.isfinite(route.wire_diameter_mm):raise ValueError('Invalid wire diameter.')
    centerline,radii=circular_centerline(original,route.minimum_bend_radius_mm)
    # Validate a swept envelope in 3D, including sampled-arc error (< 0.02 mm here).
    radius=max(route.wire_diameter_mm/2,pdm.validation_policy.wire_clearance_mm)+.03
    for a,b in zip(centerline,centerline[1:]):
        if any(not radius<=p[k]<=bound-radius for p in (a,b) for k,bound in enumerate((pdm.enclosure_width,pdm.enclosure_height,pdm.enclosure_depth))):
            raise ValueError('Wire surface leaves the enclosure cavity.')
        for c in pdm.components:
            # Terminal entry is explicitly allowed only in the endpoint device's
            # original straight lead envelope, not anywhere in its body.
            lo=(c.position.x-radius,c.position.y-radius,c.position.z-radius)
            hi=(c.position.x+c.width+radius,c.position.y+c.height+radius,c.position.z+c.depth+radius)
            if not segment_hits_box(a,b,lo,hi):continue
            endpoint=0 if c.cem_component_id==route.from_component else -1 if c.cem_component_id==route.to_component else None
            if endpoint is not None:
                lead=(original[0],original[1]) if endpoint==0 else (original[-2],original[-1])
                # Includes the local circular transition at the lead exit.
                def near_lead(p):
                    d=sub(lead[1],lead[0]);t=max(0,min(1,dot(sub(p,lead[0]),d)/max(dot(d,d),1e-12)))
                    return math.dist(p,add(lead[0],mul(d,t)))<=max(radii or [0])+radius
                if near_lead(a) and near_lead(b):continue
            raise ValueError('Swept wire intersects component '+c.cem_component_id)
    geometry_entry=geometry_exit=None
    if pdm.ducts and route.duct_entry_index is not None and route.duct_exit_index is not None:
        from shapely.geometry import LineString, Point, box
        from shapely.ops import unary_union
        entry,exit=(min(range(len(centerline)),key=lambda k:math.dist(centerline[k],original[index]))
            for index in (route.duct_entry_index,route.duct_exit_index))
        tube_radius=route.wire_diameter_mm/2+.03
        interior=unary_union([box(d.x,d.y,d.x+d.width,d.y+d.height) for d in pdm.ducts]).buffer(-max(d.wall_mm for d in pdm.ducts))
        def fully_inside(p):
            return interior.buffer(.01).covers(Point(*p[:2]).buffer(tube_radius)) and any(
                d.z+d.wall_mm+tube_radius<=p[2]<=d.z+d.depth-d.wall_mm-tube_radius for d in pdm.ducts)
        # A rounded approach enters the trough after the original polyline
        # corner. Classify this transition as a lead, and retain explicit bounds
        # for the fully contained swept trunk rather than guessing its indices.
        while entry<=exit and not fully_inside(centerline[entry]):entry+=1
        while exit>=entry and not fully_inside(centerline[exit]):exit-=1
        geometry_entry,geometry_exit=entry,exit
        trunk=centerline[entry:exit+1]
        if not trunk:raise ValueError('Rounded duct trunk is discontinuous.')
        path=LineString([(p[0],p[1]) for p in trunk]) if len(trunk)>1 else Point(*trunk[0][:2])
        if path.length<1e-9:path=Point(*trunk[0][:2])
        if not interior.buffer(.01).covers(path.buffer(tube_radius)):
            raise ValueError('Rounded wire surface leaves the duct interior.')
        if any(not any(d.z+d.wall_mm+tube_radius<=p[2]<=d.z+d.depth-d.wall_mm-tube_radius
            for d in pdm.ducts) for p in trunk):
            raise ValueError('Rounded wire surface leaves the duct depth envelope.')
    checks=[dict(id=route.id+':ENVELOPE',type='SWEPT_COMPONENT_BOUNDARY',status='PASS',message='Sampled 3D tube envelope checked against component AABBs and enclosure.'),
        dict(id=route.id+':BEND',type='MANUFACTURER_BEND_RADIUS',status='PASS' if route.minimum_bend_radius_mm else 'UNRESOLVED',message='Declared bend limit enforced.' if route.minimum_bend_radius_mm else 'Catalog has no minimum bend radius; rounded preview only.'),
        dict(id=route.id+':SEGREGATION',type='WIRE_SEPARATION',status='UNRESOLVED',message='Bundle terminal fan-out and insulation segregation require additional engineering data.')]
    checks.append(dict(id=route.id+':DIMENSIONS',type='CONDUCTOR_DIMENSIONS',status='PASS' if route.dimension_source=='catalog' else 'UNRESOLVED',message='Catalog insulation diameter.' if route.dimension_source=='catalog' else 'Generic preview diameter; conductor material, insulation and ampacity sizing require catalog data.'))
    if 'PANEL_ROOT' in {route.from_component,route.to_component}:
        checks.append(dict(id=route.id+':EARTH_ANCHOR',type='CABINET_EARTH_TERMINAL',status='UNRESOLVED',message='Legacy virtual panel-earth anchor; cabinet stud coordinates and termination capacity require engineering data.'))
    return WireGeometry(id='GEOM-'+route.id,route_id=route.id,cad_object_id='CAD-'+route.id,
        centerline=[Waypoint3D(x=x,y=y,z=z) for x,y,z in centerline],diameter_mm=route.wire_diameter_mm,
        centerline_length_mm=length(centerline),duct_entry_index=geometry_entry,duct_exit_index=geometry_exit,
        bend_radii_mm=radii,status='PASS',checks=checks)
