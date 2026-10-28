"""Physical enclosure hardware and reserved wiring troughs, in enclosure mm."""
import json
from dataclasses import replace
from pathlib import Path

from app.models.pdm import CableDuct, PanelAccessory, Position3D
from app.services.design_errors import DesignError


def fixture_hardware():
    """Explicit direct-engine fixture; the HTTP service injects database rows."""
    return json.loads((Path(__file__).parents[1] / 'data/panel_hardware.json').read_text())['items']


class PanelAssemblyEngine:
    def __init__(self, catalog=None):
        self.catalog = {r.get('code', r['id']): r for r in (fixture_hardware() if catalog is None else catalog)}

    def item(self, code):
        if code not in self.catalog:
            raise DesignError('HARDWARE_CATALOG_INCOMPLETE', f'Import panel hardware before generation: {code}.')
        return self.catalog[code]

    def parameters(self, code):
        row = self.item(code)
        return row.get('specification', {}).get('parameters', row.get('parameters', {}))

    def layout_config(self, enclosure, config):
        p = self.parameters('PANEL_SHELL_STEEL')
        duct = self.item('WIRE_DUCT_40_60')
        width = float(duct['width'])
        clearance = float(p['device_clearance_mm'])
        edge = float(p['edge_mm'])
        # Reserve real left/right gutters, bottom trough and every inter-row trough.
        margin = enclosure.mounting_plate_offset_x + edge + width + clearance
        return replace(config, margin_x=margin,
            margin_bottom=enclosure.mounting_plate_offset_y + edge + width + clearance,
            margin_top=enclosure.mounting_plate_offset_y + edge + clearance,
            duct_gap_y=width + 2 * clearance, duct_width_mm=width,
            duct_edge_mm=edge, duct_device_clearance_mm=clearance,
            z_plate=enclosure.mounting_plate_offset_z + p['backplate_mm'] + 2,
            z_din=enclosure.mounting_plate_offset_z + p['backplate_mm'] + 7.5,
            rail_z=enclosure.mounting_plate_offset_z + p['backplate_mm'])

    def ducts(self, placement, enclosure, config):
        row = self.item('WIRE_DUCT_40_60')
        params = self.parameters('WIRE_DUCT_40_60')
        w = float(row['width']); depth = float(row['depth']); wall = float(params['wall_mm'])
        edge = config.duct_edge_mm
        left = enclosure.mounting_plate_offset_x + edge
        bottom = enclosure.mounting_plate_offset_y + edge
        right = enclosure.mounting_plate_offset_x + enclosure.mounting_plate_width - edge - w
        top = enclosure.mounting_plate_offset_y + enclosure.mounting_plate_height - edge
        z = enclosure.mounting_plate_offset_z + self.parameters('PANEL_SHELL_STEEL')['backplate_mm']
        if right <= left + w or z + depth >= enclosure.depth - 20:
            raise DesignError('DUCT_SPACE_INFEASIBLE', 'The enclosure cannot contain its wiring ducts.')
        common = dict(z=z, depth=depth, catalog_id='WIRE_DUCT_40_60', component_version_id=row.get('component_version_id'),
            wall_mm=wall, usable_area_mm2=(w-2*wall)*(depth-wall), max_fill_pct=params['max_fill_pct'])
        result = [CableDuct(id=f'DUCT-{side}', label=f'{side.title()} vertical wiring duct',
            x=x, y=bottom, width=w, height=top-bottom, orientation='VERTICAL', **common)
            for side, x in [('LEFT', left), ('RIGHT', right)]]
        din_h = max((c.height for c in placement.components if c.rail_id), default=0)
        ys = [config.margin_bottom - config.duct_device_clearance_mm - w]
        ys += [r.y + din_h + config.duct_device_clearance_mm for r in placement.rails]
        for i, y in enumerate(sorted(set(ys))):
            if y < bottom - 0.01 or y+w > top + 0.01:
                raise DesignError('DUCT_SPACE_INFEASIBLE', 'A reserved horizontal duct leaves the backplate.')
            result.append(CableDuct(id=f'DUCT-H{i+1:02d}', label=f'Horizontal wiring duct {i+1}',
                x=left+w, y=y, width=right-left-w, height=w, orientation='HORIZONTAL', **common))
        return result

    def accessories(self, pdm):
        result = []
        def add(code, key, xyz, dims=None, parent='ENCLOSURE', extra=None):
            row = self.item(code)
            spec = row.get('specification', row)
            dims = dims or [row[k] for k in ('width','height','depth')]
            result.append(PanelAccessory(id=key, catalog_id=code, component_version_id=row.get('component_version_id'),
                name=row['name'], category=row.get('category', ''), parent_id=parent,
                position=Position3D(x=xyz[0],y=xyz[1],z=xyz[2]), width=dims[0],height=dims[1],depth=dims[2],
                material=spec.get('material',''), color_hex=spec.get('color','#CBD5E1'),
                parameters={**self.parameters(code), **(extra or {})}))
        W,H,D = pdm.enclosure_width,pdm.enclosure_height,pdm.enclosure_depth
        gap = self.parameters('PANEL_SHELL_STEEL')['door_gap_mm']
        add('PANEL_SHELL_STEEL','ENCLOSURE-BODY',(0,0,0),(W,H,D))
        add('PANEL_DOOR_STEEL','DOOR',(gap,gap,D+gap),(W-2*gap,H-2*gap,18))
        add('PANEL_GASKET','DOOR-GASKET',(gap+8,gap+8,D+gap-4),(W-2*gap-16,H-2*gap-16,4),parent='DOOR')
        h = self.item('PANEL_HANDLE')
        add('PANEL_HANDLE','DOOR-HANDLE',(W-55,H/2-h['height']/2,D+gap+18),parent='DOOR')
        for i,y in enumerate((H*.2,H*.8),1):
            add('PANEL_HINGE',f'HINGE-{i}',(0,y,D-8),parent='DOOR')
        add('PANEL_GLAND_PLATE','GLAND-PLATE',(W*.2,1,D*.2),(W*.6,2,D*.6))
        # End stops and insulating end plates flank each terminal group on a rail.
        for rail in pdm.rails:
            terminals = [c for c in pdm.components if c.rail_id==rail.id and c.category=='TERMINAL']
            if not terminals: continue
            x0=min(c.position.x for c in terminals); x1=max(c.position.x+c.width for c in terminals)
            y=min(c.position.y for c in terminals); z=min(c.position.z for c in terminals)
            add('TERMINAL_END_STOP',f'END-STOP-{rail.id}-L',(x0-12,y,z),parent=rail.id)
            add('TERMINAL_END_STOP',f'END-STOP-{rail.id}-R',(x1+4,y,z),parent=rail.id)
            add('TERMINAL_END_PLATE',f'END-PLATE-{rail.id}',(x1,y,z),parent=rail.id)
        return result


def assembly_bom(cem, pdm):
    rows=[dict(component_id=c.id,catalog_id=c.catalog_id,name=c.name,category=c.category,quantity=c.quantity,
        current_rating_a=c.current_rating,breaking_capacity_ka=c.breaking_capacity,heat_loss_w=c.heat_loss,unit='each') for c in cem.components]
    rows += [dict(component_id=a.id,catalog_id=a.catalog_id,name=a.name,category=a.category,quantity=1,unit='each') for a in pdm.accessories]
    rows += [dict(component_id=d.id,catalog_id=d.catalog_id,name=d.label,category='WIRE_DUCT',quantity=1,unit='cut',
        cut_length_mm=d.height if d.orientation=='VERTICAL' else d.width) for d in pdm.ducts]
    rows += [dict(component_id=r.id,catalog_id='DIN_RAIL_35',name=r.label,category='DIN_RAIL',quantity=1,unit='cut',cut_length_mm=r.length) for r in pdm.rails]
    return rows
