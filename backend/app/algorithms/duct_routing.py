"""Duct-constrained trunks with obstacle-checked terminal leads.

JPS/A* operates on the *physical* duct interior, not a soft corridor preference.
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
        network = unary_union([box(d.x,d.y,d.x+d.width,d.y+d.height) for d in ducts]).buffer(-3)
        from shapely.geometry import Point
        allowed = {(x,y) for x in range(max_x+1) for y in range(max_y+1)
                   if (x,y) not in obstacles and network.covers(Point(x*self.grid_size,y*self.grid_size))}
        blocked = {(x,y) for x in range(max_x+1) for y in range(max_y+1)}-allowed
        components={c.cem_component_id:c for c in layout.components}
        lead_cache={}
        trunk_cache={}
        routes=[]
        duct_z=ducts[0].z+ducts[0].wall_mm+min(12, (ducts[0].depth-2*ducts[0].wall_mm)/2)

        def lead(component_id, terminal_id):
            key=(component_id,terminal_id)
            if key in lead_cache: return lead_cache[key]
            comp=components.get(component_id)
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
                # are not all rendered on a single line. Fill is checked separately.
                level=duct_z+(len(routes)%8)*4
                src=self._remove_duplicate_points(src[:-1]+[(src[-1][0],src[-1][1],level)])
                dst=self._remove_duplicate_points(dst[:-1]+[(dst[-1][0],dst[-1][1],level)])
                key=(start,goal)
                if key not in trunk_cache:
                    path=self._jps_search(start,goal,blocked,set(),enclosure_w,enclosure_h)
                    if not path: path=self._astar_search(start,goal,blocked,set(),enclosure_w,enclosure_h)
                    if path: path=self._theta_star_smooth(path,blocked)
                    trunk_cache[key]=path
                path=trunk_cache[key]
                if not path:
                    raise RoutePlanningError(conn.id,net.id,'Physical wiring duct network is disconnected or blocked.')
                trunk=[(self._undiscretize(x),self._undiscretize(y),level) for x,y in path]
                points=self._remove_duplicate_points(src+trunk+list(reversed(dst)))
                # Locate actual trunk indices after duplicate removal, including same-cell trunks.
                entry=points.index(trunk[0]); exit=points.index(trunk[-1],entry)
                if not self._route_is_clear(points,layout.components,sc,tc,enclosure_w,enclosure_h,enclosure_d):
                    raise RoutePlanningError(conn.id,net.id,'A terminal lead or duct trunk violates component clearance.')
                trunk_line=LineString([(p[0],p[1]) for p in trunk]) if len(trunk)>1 else None
                used=[d.id for d in ducts if (trunk_line.intersects(box(d.x,d.y,d.x+d.width,d.y+d.height)) if trunk_line else
                    d.x<=trunk[0][0]<=d.x+d.width and d.y<=trunk[0][1]<=d.y+d.height)]
                # Insulation outside diameter is an explicit generic estimate, not ampacity sizing.
                diameter=6.0 if net.id.startswith('NET-MAIN') else 3.0
                if conn.wire_class in {'PE','NEUTRAL'}: diameter=4.0
                phase=re.search(r'L([123])',conn.from_terminal+' '+conn.to_terminal+' '+net.id)
                color=('#A6653E','#303844','#88939C')[int(phase.group(1))-1] if phase and conn.wire_class=='POWER' else self._wire_color(conn.wire_class)
                route=WireRoute(id='ROUTE-'+conn.id,net_id=net.id,net_name=net.name,
                    from_component=conn.from_component,from_terminal=conn.from_terminal,to_component=conn.to_component,to_terminal=conn.to_terminal,
                    wire_class=conn.wire_class,waypoints=[Waypoint3D(x=round(x,3),y=round(y,3),z=round(z,3)) for x,y,z in points],
                    length_mm=round(self._path_length(points),1),bend_count=self._count_bends(points),color_hex=color,
                    duct_ids=used,duct_entry_index=entry,duct_exit_index=exit,wire_diameter_mm=diameter)
                routes.append(route)
        for d in ducts:
            d.route_ids=[r.id for r in routes if d.id in r.duct_ids]
            d.wire_area_mm2=round(sum(math.pi*(r.wire_diameter_mm/2)**2 for r in routes if d.id in r.duct_ids),2)
            d.capacity_pct=round(100*d.wire_area_mm2/max(1,d.usable_area_mm2),2)
        return routes

    def _nearest_network(self,start,allowed,blocked,max_x,max_y):
        """Dijkstra to the nearest reachable trough; deterministic, no corner cutting."""
        if start in blocked or not self._valid_cell(start,max_x,max_y): return []
        queue=[(0.0,start)]; scores={start:0.0}; parent={start:None}
        while queue:
            distance,p=heapq.heappop(queue)
            if distance>scores[p]: continue
            if p in allowed: return self._reconstruct_path(parent,p)
            for dx,dy in ((1,0),(-1,0),(0,1),(0,-1),(1,1),(1,-1),(-1,1),(-1,-1)):
                q=(p[0]+dx,p[1]+dy)
                if q in blocked or not self._valid_cell(q,max_x,max_y): continue
                if dx and dy and ((p[0]+dx,p[1]) in blocked or (p[0],p[1]+dy) in blocked): continue
                score=distance+(math.sqrt(2) if dx and dy else 1)
                if score<scores.get(q,float('inf')):
                    scores[q]=score;parent[q]=p;heapq.heappush(queue,(score,q))
        return []
