"""Additive, idempotent hardware catalog and new detailed preview model versions."""
import json
from pathlib import Path
from types import SimpleNamespace
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import insert, select
from app.persistence import models as m
from app.persistence.assets import AssetStore, content_hash, primitive_glb
from app.persistence.repositories import CatalogRepository
from app.services.panel_geometry import component_geometry, assembly_geometry
from app.services.panel_assembly import PanelAssemblyEngine
from app.models.pdm import PhysicalDesignModel


def stable(key):
    return uuid5(NAMESPACE_URL,'panelstudio:hardware-v1:'+key)


def import_panel_hardware(database):
    source=json.loads((Path(__file__).parents[1]/'data/panel_hardware.json').read_text())
    store=AssetStore(database.settings.asset_root)
    with database.sessions.begin() as session:
        def put(table,key,**values):
            uid=stable(key)
            if not session.scalar(select(table.c.id).where(table.c.id==uid)):
                session.execute(insert(table).values(id=uid,**values))
            return uid
        manufacturer=put(m.manufacturers,'manufacturer',code='GENERIC_PANEL_HARDWARE',name='Generic parametric panel hardware')
        version_ids={}
        for item in source['items']:
            code=item['id'];component=put(m.components,'component:'+code,code=code,name=item['name'],category_code=item['category'],component_kind='ELECTRICAL' if item.get('engine_component') else 'MECHANICAL')
            spec={**item,'import_source':'panel-hardware-v1','provenance':source['provenance'],'source_sha256':content_hash(item)}
            vid=put(m.component_versions,'version:'+code,component_id=component,version_no=1,status='PUBLISHED',
                width_mm=item['width'],height_mm=item['height'],depth_mm=item['depth'],specification=spec,
                rated_current_a=item.get('current_rating'),breaking_capacity_ka=item.get('breaking_capacity'),pole_count=item.get('poles'))
            existing=session.execute(select(m.component_versions.c.specification).where(m.component_versions.c.id==vid)).scalar_one()
            if existing.get('source_sha256')!=spec['source_sha256']:
                raise RuntimeError('Hardware source changed; publish a new catalog version instead of altering version 1: '+code)
            version_ids[code]=vid
            product=put(m.products,'product:'+code,manufacturer_id=manufacturer,manufacturer_sku=code,display_name=item['name'])
            put(m.product_versions,'product-version:'+code,product_id=product,component_version_id=vid,version_no=1,status='PUBLISHED',lifecycle_status='UNKNOWN')
            put(m.component_mounting,'mount:'+code,component_version_id=vid,mounting_code=item.get('mounting','MECHANICAL'),mounting_parameters=item['parameters'])
            for terminal in item.get('terminals',[]):
                put(m.component_terminals,'terminal:'+code+':'+terminal['id'],component_version_id=vid,code=terminal['id'],terminal_kind='FEED_THROUGH',
                    electrical_role=terminal['type'],connection_type='SCREW',coordinate_mm={k:terminal[k] for k in ('x','y','z')})
            if not session.scalar(select(m.component_thermal_specs.c.component_version_id).where(m.component_thermal_specs.c.component_version_id==vid)):
                session.execute(insert(m.component_thermal_specs).values(component_version_id=vid,heat_loss_w=item.get('heat_loss',0)))
        catalog=CatalogRepository(session,store)
        rows=[catalog._component(r) for r in session.execute(catalog._query()).mappings()]
        enclosure_versions=[]
        for row in rows:
            code=row['code'];spec=row['specification'];legacy=spec.get('import_source')=='legacy-json-v1'
            hardware=spec.get('import_source')=='panel-hardware-v1'
            if not (legacy or hardware): continue
            model_key='detailed:'+code
            model=put(m.cad_models,'cad:'+code,code='PANEL_DETAIL_'+code,name=row['name']+' assembly geometry',model_kind='PART')
            mv=put(m.cad_model_versions,model_key,cad_model_id=model,version_no=2,status='PUBLISHED',
                coordinate_system={'handedness':'right','source_length_unit':'mm','glb_length_unit':'m','origin':'centre'},
                feature_definition={'handler':'panel_detail_v2','category':row['category'],'parameters':spec.get('parameters',{}),'generic_geometry':True},
                generator_name='panelstudio-primitives',generator_version='2')
            for axis in ('width','height','depth'):
                put(m.cad_parameter_definitions,model_key+':'+axis,cad_model_version_id=mv,code=axis+'_mm',value_type='DECIMAL',unit_code='mm',
                    default_value=row[axis],min_value=1,editable=row['category']=='ENCLOSURE',derived=False,
                    description='Generic geometric dimension, not a certified product range.')
            if not session.scalar(select(m.component_cad_models.c.component_version_id).where(
                m.component_cad_models.c.component_version_id==row['component_version_id'],m.component_cad_models.c.cad_model_version_id==mv)):
                session.execute(insert(m.component_cad_models).values(component_version_id=row['component_version_id'],cad_model_version_id=mv))
            if row['category']=='ENCLOSURE':
                enclosure_versions.append(row['component_version_id'])
                pdm=PhysicalDesignModel(id='PREVIEW',project_id='CATALOG',panel_id='CATALOG',enclosure_id=code,
                    enclosure_width=row['width'],enclosure_height=row['height'],enclosure_depth=row['depth'],ip_rating=spec['ip_rating'],
                    **{k:spec[k] for k in ('mounting_plate_width','mounting_plate_height')},
                    mounting_plate_x=spec['mounting_plate_offset_x'],mounting_plate_y=spec['mounting_plate_offset_y'],mounting_plate_z=spec['mounting_plate_offset_z'])
                assembly=PanelAssemblyEngine(source['items']);pdm.construction=assembly.parameters('PANEL_SHELL_STEEL');pdm.accessories=assembly.accessories(pdm)
                primitives=assembly_geometry(pdm)
            else:
                primitives=component_geometry(SimpleNamespace(**{**row,'id':code,'color_hex':spec.get('color','#CBD5E1')}))
            centred=[]
            for primitive in primitives:
                pos=primitive['position']; centred.append({**primitive,'position':{k:pos[k]-row[axis]/2 for k,axis in zip(('x','y','z'),('width','height','depth'))}})
            file=store.put(primitive_glb(centred),'glb')
            put(m.cad_assets,'preview:'+code,cad_model_version_id=mv,asset_role='PREVIEW',file_format='GLB',
                **file,media_type='model/gltf-binary',generator_name='panelstudio-primitives',generator_version='2',generation_status='READY')
        for enclosure in enclosure_versions:
            for code,vid in version_ids.items():
                put(m.component_accessories,'accessory:'+enclosure+':'+code,component_version_id=enclosure,
                    accessory_component_version_id=vid,relation_code='PANEL_CONSTRUCTION',constraints={'generic':True,'dimension_source':'project-enclosure'})
    return {'hardware_items':len(source['items']),'detailed_previews':sum(r['specification'].get('import_source') in {'legacy-json-v1','panel-hardware-v1'} for r in rows)}
