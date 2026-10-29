"""DB template layout and port-based orthogonal routes, independent of PDM geometry."""
from dataclasses import dataclass
from shapely.geometry import LineString
from app.algorithms.schematic_routing import orthogonal_route, simplify
from app.services.design_errors import DesignError


@dataclass(frozen=True)
class SchematicConfig:
    column_pitch: int = 180
    row_pitch: int = 240
    symbol_width: int = 110
    symbol_height: int = 72
    port_stub: int = 24


class SchematicEngine:
    def __init__(self, config=None): self.cfg=config or SchematicConfig()

    def generate_schematic_data(self,cem):
        cfg=self.cfg
        feeders=sorted((c for c in cem.components if c.category=='MCB'),key=lambda c:c.id)
        terminals=sorted((c for c in cem.components if c.category=='TERMINAL'),key=lambda c:c.id)
        others=sorted((c for c in cem.components if c.category not in {'MCB','TERMINAL'}),key=lambda c:({'MCCB':0,'BUSBAR':1,'SPD':2,'NEUTRAL_BAR':3,'EARTH_BAR':4}.get(c.category,5),c.id))
        # DB functional columns preserve feeder order; paired terminal blocks align below.
        width=max(1200,(max(len(feeders),len(others))+2)*cfg.column_pitch)
        symbols=[]
        for group,row in ((others,0),(feeders,1),(terminals,2)):
            for index,c in enumerate(group):
                x=100+index*cfg.column_pitch;y=100+row*cfg.row_pitch
                ports=[]
                top=[t for t in c.terminals if 'OUT' not in t['id'] and 'RIGHT' not in t['id']]
                bottom=[t for t in c.terminals if t not in top]
                for side,items in (('TOP',top),('BOTTOM',bottom)):
                    for k,t in enumerate(items):
                        ports.append(dict(id=t['id'],port_id=c.id+':'+t['id'],x=x+cfg.symbol_width*(k+1)/(len(items)+1),
                            y=y if side=='TOP' else y+cfg.symbol_height,direction=side))
                symbols.append(dict(id=c.id,name=c.name,category=c.category,type=c.category,x=x,y=y,
                    width=cfg.symbol_width,height=cfg.symbol_height,label=f'{c.id}\n{c.current_rating:g}A',terminals=ports))
        symbols.append(dict(id='PANEL_ROOT',name=cem.panel_id,category='PANEL',type='PANEL',x=40,y=820,width=110,height=72,
            label=cem.panel_id,terminals=[dict(id='EARTH_STUD',port_id='PANEL_ROOT:EARTH_STUD',x=95,y=820,direction='TOP')]))
        by_id={s['id']:s for s in symbols};obstacles=[]
        for s in symbols:
            obstacles.extend([(s['x']-8,s['y']-8,s['x']+s['width']+8,s['y']+s['height']+8)])
        ports={(s['id'],t['id']):t for s in symbols for t in s['terminals']}
        wires=[];occupied=[];checks=[]
        for net in cem.nets:
            for conn in net.connections:
                a=ports.get((conn.from_component,conn.from_terminal));b=ports.get((conn.to_component,conn.to_terminal))
                if a is None or b is None:raise DesignError('SCHEMATIC_PORT_MISSING','A CEM terminal has no symbol port.',{'connection_id':conn.id})
                start=(a['x'],a['y']);end=(b['x'],b['y'])
                stub=lambda t:(t['x'],t['y']+(-cfg.port_stub if t['direction']=='TOP' else cfg.port_stub))
                try:points=simplify([start]+orthogonal_route(stub(a),stub(b),obstacles,
                    tracks=[30,60,220,250,280,460,490,520,700,730,780,940],occupied=occupied)+[end])
                except ValueError as exc:raise DesignError('SCHEMATIC_ROUTING_FAILED',str(exc),{'connection_id':conn.id}) from exc
                occupied.extend(zip(points,points[1:]))
                color='#3B82F6' if conn.wire_class=='NEUTRAL' else '#22C55E' if conn.wire_class=='PE' else '#EF4444'
                wires.append(dict(id=conn.id,conductor_id=conn.id,net_id=net.id,net_name=net.name,
                    **{'from':conn.from_component,'to':conn.to_component},from_terminal=conn.from_terminal,to_terminal=conn.to_terminal,
                    source_port_id=a['port_id'],target_port_id=b['port_id'],wire_class=conn.wire_class,color=color,
                    waypoints=[dict(x=x,y=y) for x,y in points],svg_path='M '+' L '.join(f'{x} {y}' for x,y in points),
                    status='PASS',layer='WIRING',crossings=[],junctions=[]))
        # Only a shared CEM net can have a junction. Distinct nets have explicit non-connected crossings.
        for i,a in enumerate(wires):
            for b in wires[i+1:]:
                intersection=LineString([(p['x'],p['y']) for p in a['waypoints']]).intersection(LineString([(p['x'],p['y']) for p in b['waypoints']]))
                parts=list(intersection.geoms) if hasattr(intersection,'geoms') else [intersection]
                for part in parts:
                    if part.is_empty:continue
                    if part.geom_type=='Point':
                        ends=lambda w:{(w['from'],w['from_terminal']),(w['to'],w['to_terminal'])}
                        shared=ends(a)&ends(b)
                        connected=a['net_id']==b['net_id'] and any(
                            abs(ports[k]['x']-part.x)<1e-6 and abs(ports[k]['y']-part.y)<1e-6 for k in shared)
                        point=dict(x=part.x,y=part.y,other_id=b['id'],connected=connected)
                        if connected:a['junctions'].append(point)
                        else:
                            # Paint the gap on the later SVG edge, otherwise a
                            # subsequent wire would paint over the crossing mask.
                            point['other_id']=a['id']
                            point['axis']='VERTICAL' if any(abs(p['x']-q['x'])<1e-6 and abs(p['x']-part.x)<1e-6
                                and min(p['y'],q['y'])<part.y<max(p['y'],q['y']) for p,q in zip(b['waypoints'],b['waypoints'][1:])) else 'HORIZONTAL'
                            b['crossings'].append(point)
                    elif part.geom_type=='LineString' and part.length>0.01:
                        checks.append(dict(id=f"OVERLAP:{a['id']}:{b['id']}",status='WARNING',type='COINCIDENT_SEGMENTS',
                            object_ids=[a['id'],b['id']],message='Drawing tracks overlap; connectivity remains defined by CEM, never by geometry.'))
        memberships={}
        for wire in wires:
            for key in ((wire['from'],wire['from_terminal']),(wire['to'],wire['to_terminal'])):
                memberships.setdefault((wire['net_id'],key),[]).append(wire)
        for (net_id,key),members in memberships.items():
            if len(members)>1:
                port=ports[key]
                if not any(abs(p['x']-port['x'])<1e-6 and abs(p['y']-port['y'])<1e-6 for p in members[0]['junctions']):
                    members[0]['junctions'].append(dict(id=f'JUNCTION:{net_id}:{port["port_id"]}',
                        x=port['x'],y=port['y'],connected=True,port_id=port['port_id']))
        return dict(width=width,height=1000,symbols=symbols,wires=wires,validation_results=checks,
            coordinate_system='schematic-mm-top-left',layout_algorithm='DB-functional-template/orthogonal-A*-bend-congestion-cost')
