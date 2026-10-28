"""Shared parametric preview geometry. No external manufacturer meshes required."""
import math


def solid(key, name, xyz, dims, color, **extra):
    return dict(id=key,name=name,type='BOX',position=dict(zip(('x','y','z'),xyz)),
        dimensions=dict(zip(('width','height','depth'),dims)),color=color,opacity=1,**extra)


def screw(key, xyz, radius, depth=1.5, **extra):
    return dict(id=key,name='Terminal screw',type='CYLINDER',position=dict(zip(('x','y','z'),xyz)),
        radius=radius,height=depth,color='#9DA7AF',opacity=1,**extra)


def component_geometry(comp):
    """Local lower-corner geometry stays within the catalog mounting envelope."""
    w,h,d=comp.width,comp.height,comp.depth
    key=comp.id
    parts=[]
    def add(suffix,xyz,dims,color):
        parts.append(solid(f'{key}-{suffix}',comp.name,xyz,dims,color))
    if comp.category in {'MCB','MCCB','SPD'}:
        case='#313C47' if comp.category=='MCCB' else '#D5D9DC'
        add('CASE',(w/2,h/2,d*.36),(w,h,d*.72),case)
        add('FRONT',(w/2,h*.5,d*.79),(w*.9,h*.58,d*.18),'#E1E4E5' if comp.category!='MCCB' else '#49535C')
        poles=max(1,round(w/18)) if comp.category!='MCCB' else 3
        for p in range(min(poles,4)):
            x=(p+.5)*w/min(poles,4)
            add(f'TOGGLE-{p}',(x,h*.52,d*.94),(w/min(poles,4)*.65,h*.16,d*.12),
                '#CF4242' if comp.category=='SPD' else '#222B34')
        add('LABEL',(w/2,h*.73,d*.895),(w*.68,h*.09,.4),'#F0F0E8')
    elif comp.category=='TERMINAL':
        add('FOOT',(w/2,h/2,3),(w,h,6),'#4B5966')
        poles=3 if any(t.get('id')=='L3_LEFT' for t in comp.terminals) else 1
        pitch=w/poles
        for pole in range(poles):
            xx=(pole+.5)*pitch
            add(f'INSULATOR-{pole}',(xx,h/2,d*.47),(pitch*.94,h,d*.75),'#D5A844')
            add(f'BRIDGE-{pole}',(xx,h/2,d*.87),(pitch*.8,h*.35,d*.20),'#ADB4B8')
            add(f'MARKER-{pole}',(xx,h*.5,d*.985),(pitch*.85,h*.11,d*.03),'#F4F2DE')
            for i,y in enumerate((h*.22,h*.78)):
                parts.append(screw(f'{key}-SCREW-{pole}-{i}',(xx,y,d*.94),min(pitch*.29,3),d*.08))
    elif comp.category in {'BUSBAR','NEUTRAL_BAR','EARTH_BAR'}:
        for i,x in enumerate((w*.12,w*.88)):
            add(f'SUPPORT-{i}',(x,h/2,d*.18),(min(w*.13,22),h,d*.36),'#282E35')
        n=4 if comp.category=='BUSBAR' else 1
        for i in range(n):
            y=(i+.5)*h/n
            add(f'COPPER-{i}',(w/2,y,d*.65),(w,h/n*.7,d*.2),'#BF873E')
            for j in range(8):
                parts.append(screw(f'{key}-BOLT-{i}-{j}',((j+.5)*w/8,y,d*.79),min(3,h/n*.2),d*.08))
    else:
        add('BODY',(w/2,h/2,d/2),(w,h,d),comp.color_hex)
    return parts


def placed_component_geometry(comp):
    parts=comp.geometry or component_geometry(comp)
    angle=math.radians(comp.rotation_deg); co,si=math.cos(angle),math.sin(angle)
    result=[]
    for p in parts:
        q={**p}; pos=p['position']; x,y=pos['x']-comp.width/2,pos['y']-comp.height/2
        q['position']={'x':comp.position.x+comp.width/2+x*co-y*si,
            'y':comp.position.y+comp.height/2+x*si+y*co,'z':comp.position.z+pos['z']}
        q.update(pdm_component_id=comp.id,cem_component_id=comp.cem_component_id,category=comp.category,
            rotation_xyzw=[0,0,math.sin(angle/2),math.cos(angle/2)])
        result.append(q)
    return result


def assembly_geometry(pdm):
    parts=[]
    t=float(pdm.construction.get('sheet_mm',1.5)); W,H,D=pdm.enclosure_width,pdm.enclosure_height,pdm.enclosure_depth
    def add(key,name,xyz,dims,color,group='ENCLOSURE',**extra):
        parts.append(solid(key,name,xyz,dims,color,assembly_group=group,**extra))
    body='#BAC4CD'
    for key,xyz,dims in [
        ('REAR',(W/2,H/2,t/2),(W,H,t)),
        ('LEFT',(t/2,H/2,D/2),(t,H,D)),('RIGHT',(W-t/2,H/2,D/2),(t,H,D)),
        ('TOP',(W/2,H-t/2,D/2),(W,t,D)),('BOTTOM',(W/2,t/2,D/2),(W,t,D))]:
        add('CABINET-'+key,'Enclosure '+key.lower(),xyz,dims,body)
    for x in (9,W-9): add(f'CABINET-RETURN-{x}','Folded front return',(x,H/2,D-8),(16,H,2),body)
    pw=pdm.mounting_plate_width or W-60; ph=pdm.mounting_plate_height or H-60
    add('CAD-BACKPLATE','Mounting backplate',(pdm.mounting_plate_x+pw/2,pdm.mounting_plate_y+ph/2,pdm.mounting_plate_z+1.5),(pw,ph,3),'#A3AFBA',group='BACKPLATE')
    for rail in pdm.rails:
        # Top-hat section: foot flanges, upright webs and central crown.
        for suffix,y,z,hh,dd in [('CROWN',17.5,7,12,1),('WEB-A',11,3.5,1,7),('WEB-B',24,3.5,1,7),('FOOT-A',5,0.5,10,1),('FOOT-B',30,0.5,10,1)]:
            add(f'{rail.id}-{suffix}',rail.label,(rail.x+rail.length/2,rail.y+y,rail.z+z),(rail.length,hh,dd),'#A8B5BF',group='RAIL',object_id=rail.id)
    vertical=[d for d in pdm.ducts if d.orientation=='VERTICAL']
    for duct in pdm.ducts:
        x,y,z=duct.x,duct.y,duct.z; w,h,d=duct.width,duct.height,duct.depth; wall=duct.wall_mm
        add(duct.id+'-BASE',duct.label,(x+w/2,y+h/2,z+wall/2),(w,h,wall),'#9EABB5',group='DUCT',object_id=duct.id)
        length=h if duct.orientation=='VERTICAL' else w
        for side in (0,1):
            for j in range(int(length/12)):
                offset=j*12+3.5
                # Leave T-junctions open; fingers never form an end wall across a trough.
                if duct.orientation=='HORIZONTAL' and any(v.x-1<=x+offset<=v.x+v.width+1 for v in vertical): continue
                if duct.orientation=='VERTICAL' and any(q.orientation=='HORIZONTAL' and q.y-1<=y+offset<=q.y+q.height+1 and
                    ((side==1 and abs(q.x-(x+w))<1) or (side==0 and abs(q.x+q.width-x)<1)) for q in pdm.ducts): continue
                xyz=(x+wall/2+side*(w-wall),y+offset,z+d/2) if duct.orientation=='VERTICAL' else (x+offset,y+wall/2+side*(h-wall),z+d/2)
                dims=(wall,7,d-wall) if duct.orientation=='VERTICAL' else (7,wall,d-wall)
                add(f'{duct.id}-FINGER-{side}-{j}',duct.label+' slotted wall',xyz,dims,'#AAB5BE',group='DUCT',object_id=duct.id)
        add(duct.id+'-COVER',duct.label+' removable cover',(x+w/2,y+h/2,z+d),(w,h,2),'#AAB5BE',group='DUCT_COVER',object_id=duct.id)
    for a in pdm.accessories:
        x,y,z=a.position.x,a.position.y,a.position.z; w,h,d=a.width,a.height,a.depth
        group='DOOR' if a.parent_id=='DOOR' or a.category=='DOOR' else 'HARDWARE'
        if a.category=='ENCLOSURE_BODY': continue
        if a.category=='DOOR':
            add(a.id+'-SHEET',a.name,(x+w/2,y+h/2,z+d-0.75),(w,h,1.5),a.color_hex,group=group,object_id=a.id)
            for i,(xx,yy,ww,hh) in enumerate([(x+1,y+h/2,2,h),(x+w-1,y+h/2,2,h),(x+w/2,y+1,w,2),(x+w/2,y+h-1,w,2)]):
                add(a.id+f'-RETURN-{i}',a.name,(xx,yy,z+d/2),(ww,hh,d),a.color_hex,group=group,object_id=a.id)
        elif a.category=='GASKET':
            for i,(xx,yy,ww,hh) in enumerate([(x+2.5,y+h/2,5,h),(x+w-2.5,y+h/2,5,h),(x+w/2,y+2.5,w,5),(x+w/2,y+h-2.5,w,5)]):
                add(a.id+str(i),a.name,(xx,yy,z+d/2),(ww,hh,d),a.color_hex,group=group,object_id=a.id)
        elif a.category=='HANDLE':
            add(a.id+'-GRIP',a.name,(x+w/2,y+h/2,z+d*.8),(w*.55,h,d*.4),a.color_hex,group=group,object_id=a.id)
            for yy in (y+10,y+h-10): add(a.id+str(yy),a.name,(x+w/2,yy,z+d*.4),(w,20,d*.8),a.color_hex,group=group,object_id=a.id)
        else:
            add(a.id,a.name,(x+w/2,y+h/2,z+d/2),(w,h,d),a.color_hex,group=group,object_id=a.id)
    return parts
