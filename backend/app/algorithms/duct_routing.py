"""Duct-constrained trunks with obstacle-checked terminal leads.

Manhattan A* operates on the physical duct interior, not a soft corridor preference.
Only the terminal lead-ins may leave that network. No unrestricted trunk fallback.
"""
import heapq
import math
import re

from shapely.geometry import LineString, box
from shapely.ops import unary_union

from app.algorithms.jps_theta_star import JPSThetaStarRouter, RoutePlanningError
from app.models.pdm import WireRoute, Waypoint3D


class DuctRouter(JPSThetaStarRouter):
    def route_layout(self, layout, nets, enclosure_w, enclosure_h, enclosure_d=0, ducts=None):
        if not ducts:
            raise ValueError('Physical wiring ducts are required for duct routing.')
        max_x, max_y = int(enclosure_w/self.grid_size), int(enclosure_h/self.grid_size)
        obstacles = self._build_obstacle_grid(layout.components, enclosure_w, enclosure_h)
        # Union outer footprints first: a T junction has no internal end wall.
        trough = unary_union([box(d.x,d.y,d.x+d.width,d.y+d.height) for d in ducts])
        network = trough.buffer(-17)
        from shapely.geometry import Point
        allowed = {(x,y) for x in range(max_x+1) for y in range(max_y+1)
                   if (x,y) not in obstacles and network.covers(Point(x*self.grid_size,y*self.grid_size))}
        blocked = {(x,y) for x in range(max_x+1) for y in range(max_y+1)}-allowed
        components={c.cem_component_id:c for c in layout.components}
        lead_cache={}
        trunk_cache={}
        routes=[]
        duct_z=ducts[0].z+ducts[0].wall_mm+min(11, (ducts[0].depth-2*ducts[0].wall_mm)/2)

        def lead(component_id, terminal_id):
            key=(component_id,terminal_id)
            if key in lead_cache: return lead_cache[key]
            comp=components.get(component_id)
            if comp is None and (component_id,terminal_id)!=('PANEL_ROOT','EARTH_STUD'):
                raise ValueError('Unknown physical terminal '+component_id+':'+terminal_id)
            terminal=self._component_terminal(comp,terminal_id) if comp else (
                ducts[0].x+ducts[0].width/2, ducts[0].y+self.grid_size*2, duct_z)
            options=self._terminal_exit_options(comp,terminal,layout.components,enclosure_w,enclosure_h) if comp else [(terminal,terminal)]
            for _,anchor in options:
                path=self._nearest_network(self._to_grid(anchor),allowed,obstacles,max_x,max_y)
                if not path: continue
                points=[terminal,anchor]+[(self._undiscretize(x),self._undiscretize(y),terminal[2]) for x,y in path]
                points=self._remove_duplicate_points(points)
                # Retain the exact off-grid anchor; search starts at the nearest free grid cell.
                end=(points[-1][0],points[-1][1],duct_z)
                points=self._remove_duplicate_points(points+[end])
                lead_cache[key]=(points,path[-1],comp)
                return lead_cache[key]
            return None

        for net in nets:
            for conn in net.connections:
                try:
                    a=lead(conn.from_component,conn.from_terminal)
                    b=lead(conn.to_component,conn.to_terminal)
                except ValueError as exc:
                    raise RoutePlanningError(conn.id,net.id,str(exc)) from exc
                if not a or not b:
                    raise RoutePlanningError(conn.id,net.id,'No collision-free terminal lead reaches a wiring duct.')
                src, start, sc=a; dst, goal, tc=b
                # Distribute the bundle through trough depth so coincident trunks
                # occupy bounded lateral/depth slots. Fill is checked separately.
                level=duct_z+(len(routes)%8)*6
                lateral=((len(routes)//8)%7-3)*3.2
                if len(routes)>=56:
                    raise RoutePlanningError(conn.id,net.id,'Configured discrete bundle lanes exhausted; enlarge routing space.')
                src=self._remove_duplicate_points(src[:-1]+[(src[-1][0],src[-1][1],level),(src[-1][0]+lateral,src[-1][1],level),(src[-1][0]+lateral,src[-1][1]+lateral,level)])
                dst=self._remove_duplicate_points(dst[:-1]+[(dst[-1][0],dst[-1][1],level),(dst[-1][0]+lateral,dst[-1][1],level),(dst[-1][0]+lateral,dst[-1][1]+lateral,level)])
                key=(start,goal)
                if key not in trunk_cache:
                    path=self._manhattan_search(start,goal,blocked,max_x,max_y)
                    trunk_cache[key]=path
                path=trunk_cache[key]
                if not path:
                    raise RoutePlanningError(conn.id,net.id,'Physical wiring duct network is disconnected or blocked.')
                trunk=[(self._undiscretize(x)+lateral,self._undiscretize(y)+lateral,level) for x,y in path]
                points=self._remove_duplicate_points(src+trunk+list(reversed(dst)))
                # Locate actual trunk indices after duplicate removal, including same-cell trunks.
                try:points=self._orthogonalize(points,layout.components,sc,tc,enclosure_w,enclosure_h,enclosure_d)
                except ValueError as exc:raise RoutePlanningError(conn.id,net.id,str(exc)) from exc
                points=self._finalize(points)
                inside=[i for i,p in enumerate(points) if trough.buffer(-3).covers(Point(p[0],p[1])) and any(d.z+d.wall_mm<=p[2]<=d.z+d.depth-d.wall_mm for d in ducts)]
                if not inside:raise RoutePlanningError(conn.id,net.id,'No retained trunk lies in a wiring duct.')
                entry,exit=inside[0],inside[-1]
                if not self._route_is_clear(points,layout.components,sc,tc,enclosure_w,enclosure_h,enclosure_d):
                    raise RoutePlanningError(conn.id,net.id,'A terminal lead or duct trunk violates component clearance.')
                trunk_line=LineString([(p[0],p[1]) for p in trunk]) if len(trunk)>1 else None
                used=[d.id for d in ducts if (trunk_line.intersects(box(d.x,d.y,d.x+d.width,d.y+d.height)) if trunk_line else
                    d.x<=trunk[0][0]<=d.x+d.width and d.y<=trunk[0][1]<=d.y+d.height)]
                # Insulation outside diameter is an explicit generic estimate, not ampacity sizing.
                diameter=6.0 if net.id.startswith('NET-MAIN') else 3.0
                if conn.wire_class in {'PE','NEUTRAL'}: diameter=4.0
                dimension_source='catalog' if conn.insulation_diameter_mm else 'generic-preview-estimate'
                diameter=conn.insulation_diameter_mm or diameter
                phase=re.search(r'L([123])',conn.from_terminal+' '+conn.to_terminal+' '+net.id)
                color=('#A6653E','#303844','#88939C')[int(phase.group(1))-1] if phase and conn.wire_class=='POWER' else self._wire_color(conn.wire_class)
                route=WireRoute(id='ROUTE-'+conn.id,net_id=net.id,net_name=net.name,
                    from_component=conn.from_component,from_terminal=conn.from_terminal,to_component=conn.to_component,to_terminal=conn.to_terminal,
                    wire_class=conn.wire_class,waypoints=[Waypoint3D(x=round(x,3),y=round(y,3),z=round(z,3)) for x,y,z in points],
                    length_mm=round(self._path_length(points),1),bend_count=self._count_bends(points),color_hex=color,
                    duct_ids=used,duct_entry_index=entry,duct_exit_index=exit,wire_diameter_mm=diameter,
                    conductor_id=conn.id,dimension_source=dimension_source,minimum_bend_radius_mm=conn.minimum_bend_radius_mm,
                    routing_algorithm='duct-Manhattan-A*',status='PASS',
                    routing_config={'grid_mm':self.grid_size,'bend_penalty':2,'lane_lateral_mm':lateral,'lane_z_mm':level})
                if any(d.allowed_wire_classes and conn.wire_class not in d.allowed_wire_classes for d in ducts if d.id in used):
                    raise RoutePlanningError(conn.id,net.id,'The route uses a duct that forbids its electrical routing class.')
                routes.append(route)
        for d in ducts:
            d.route_ids=[r.id for r in routes if d.id in r.duct_ids]
            d.wire_area_mm2=round(sum(math.pi*(r.wire_diameter_mm/2)**2 for r in routes if d.id in r.duct_ids),2)
            d.capacity_pct=round(100*d.wire_area_mm2/max(1,d.usable_area_mm2),2)
            if d.capacity_pct>d.max_fill_pct:
                raise RoutePlanningError(d.route_ids[-1] if d.route_ids else '', '', 'Wiring duct '+d.id+' exceeds its configured fill capacity.')
        return routes

    def _nearest_network(self,start,allowed,blocked,max_x,max_y):
        """Dijkstra to the nearest reachable trough; deterministic, no corner cutting."""
        if start in blocked or not self._valid_cell(start,max_x,max_y): return []
        queue=[(0.0,start)]; scores={start:0.0}; parent={start:None}
        while queue:
            distance,p=heapq.heappop(queue)
            if distance>scores[p]: continue
            if p in allowed: return self._reconstruct_path(parent,p)
            for dx,dy in ((1,0),(-1,0),(0,1),(0,-1)):
                q=(p[0]+dx,p[1]+dy)
                if q in blocked or not self._valid_cell(q,max_x,max_y): continue
                if dx and dy and ((p[0]+dx,p[1]) in blocked or (p[0],p[1]+dy) in blocked): continue
                score=distance+(math.sqrt(2) if dx and dy else 1)
                if score<scores.get(q,float('inf')):
                    scores[q]=score;parent[q]=p;heapq.heappush(queue,(score,q))
        return []

    def _manhattan_search(self,start,goal,blocked,max_x,max_y):
        # Ducts require orthogonal paths. Theta* shortcuts would leave this
        # manufacturing constraint; retain the original JPS/Theta router for open space.
        first=(*start,-1);queue=[(0,0,first)];scores={first:0};parents={first:None}
        while queue:
            _,cost,state=heapq.heappop(queue)
            if cost!=scores[state]:continue
            x,y,d=state
            if (x,y)==goal:
                path=[]
                while state is not None:
                    path.append(state[:2]);state=parents[state]
                return list(reversed(path))
            for dx,dy,axis in ((1,0,0),(-1,0,0),(0,1,1),(0,-1,1)):
                q=(x+dx,y+dy)
                if q in blocked or not self._valid_cell(q,max_x,max_y):continue
                value=cost+1+(2 if d!=-1 and d!=axis else 0);n=(*q,axis)
                if value<scores.get(n,float('inf')):
                    scores[n]=value;parents[n]=state
                    heapq.heappush(queue,(value+abs(q[0]-goal[0])+abs(q[1]-goal[1]),value,n))
        return []

    @staticmethod
    def _finalize(points):
        # A lead can meet a trunk beyond the nearest grid turn. Remove a
        # collinear out-and-back detour before bend construction; the shortened
        # segment is a subset of the already obstacle-checked segments.
        result=[]
        for p in points:
            while len(result)>1:
                a,b=result[-2:];u=[b[k]-a[k] for k in range(3)];v=[p[k]-b[k] for k in range(3)]
                cross=(u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0])
                if sum(x*x for x in cross)>1e-10:break
                result.pop()
            if not result or math.dist(result[-1],p)>1e-7:result.append(p)
        return result

    def _orthogonalize(self,points,components,src,dst,width,height,depth):
        from itertools import permutations
        index=0
        while index<len(points)-1:
            a,b=points[index:index+2]
            axes=[k for k in range(3) if abs(a[k]-b[k])>1e-7]
            if len(axes)<=1:
                index+=1;continue
            for order in permutations(axes):
                cursor=list(a);bridge=[]
                for axis in order:
                    cursor[axis]=b[axis];bridge.append(tuple(cursor))
                candidate=points[:index+1]+bridge+points[index+2:]
                if self._route_is_clear(candidate,components,src,dst,width,height,depth):
                    points=candidate;index+=len(bridge);break
            else:raise ValueError('No obstacle-clear orthogonal terminal approach fits the routing grid.')
        return points
