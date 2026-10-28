"""One geometry contract for the assembly viewer, GLB and FreeCAD script."""
from app.models.pdm import PhysicalDesignModel
from app.services.panel_geometry import assembly_geometry, placed_component_geometry


class CADEngine:
    def generate_parametric_geometry(self, pdm: PhysicalDesignModel):
        primitives=assembly_geometry(pdm)
        for comp in pdm.components:
            primitives.extend(placed_component_geometry(comp))
            # Envelope is retained for existing ID/dimension consumers, not rendered.
            primitives.append(dict(id='CAD-'+comp.id,type='ENVELOPE',name=comp.name,
                position={'x':comp.position.x+comp.width/2,'y':comp.position.y+comp.height/2,'z':comp.position.z+comp.depth/2},
                dimensions={'width':comp.width,'height':comp.height,'depth':comp.depth},
                cem_component_id=comp.cem_component_id,pdm_component_id=comp.id))
        for route in pdm.routes:
            primitives.append(dict(id='CAD-'+route.id,type='TUBE',name='Wire '+route.net_name,
                route_id=route.id,net_id=route.net_id,points=[p.model_dump() for p in route.waypoints],
                radius=route.wire_diameter_mm/2,color=route.color_hex,opacity=1))
        return {'panel_id':pdm.panel_id,'units':'mm','primitives':primitives}

    def export_freecad_script(self, pdm: PhysicalDesignModel):
        script=['# Electrical panel assembly; all lengths in millimetres',
            'import FreeCAD as App','import Part',"doc = App.newDocument('ElectricalPanel')"]
        for index,p in enumerate(self.generate_parametric_geometry(pdm)['primitives']):
            kind=p['type']
            if kind not in {'BOX','CYLINDER','TUBE'}: continue
            name='PanelPart_'+str(index)
            script.append('# '+p.get('name',name).replace('\n',' '))
            if kind=='TUBE':
                points=', '.join(f"App.Vector({v['x']},{v['y']},{v['z']})" for v in p['points'])
                script += [f'points = [{points}]', 'segments = []',
                    'for a, b in zip(points, points[1:]):',
                    '    vector = b - a',
                    '    if vector.Length > 0.001:',
                    f"        segments.append(Part.makeCylinder({p['radius']}, vector.Length, a, vector))",
                    'shape = Part.makeCompound(segments)']
            else:
                pos=p['position']
                if kind=='BOX':
                    dims=p['dimensions'];w,h,d=(dims[k] for k in ('width','height','depth'))
                    script += [f'shape = Part.makeBox({w},{h},{d})',f'shape.translate(App.Vector({-w/2},{-h/2},{-d/2}))']
                else:
                    script += [f"shape = Part.makeCylinder({p['radius']},{p['height']})",f"shape.translate(App.Vector(0,0,{-p['height']/2}))"]
                if p.get('rotation_xyzw'):
                    q=p['rotation_xyzw'];script.append(f'shape.Placement.Rotation = App.Rotation({q[0]},{q[1]},{q[2]},{q[3]})')
                script.append(f"shape.translate(App.Vector({pos['x']},{pos['y']},{pos['z']}))")
            script.append(f"doc.addObject('Part::Feature', '{name}').Shape = shape")
        script += ['doc.recompute()',"Part.export(doc.Objects, 'panel_model.step')"]
        return '\n'.join(script)
