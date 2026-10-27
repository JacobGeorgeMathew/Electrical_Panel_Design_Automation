-- Entirely illustrative, fictional data for schema demonstration only.
-- Values are not manufacturer specifications, certified dimensions, or safety limits.
-- Asset hashes/keys are illustrative metadata; replace with hashes of real generated files.
BEGIN;
INSERT INTO manufacturers(id,code,name) VALUES
 ('10000000-0000-0000-0000-000000000001','DEMO','Illustrative Demo Supplier');
INSERT INTO product_families(id,manufacturer_id,code,name) VALUES
 ('11000000-0000-0000-0000-000000000001','10000000-0000-0000-0000-000000000001','DEMO-DB','Illustrative distribution-board parts');
INSERT INTO components(id,code,name,category_code,component_kind) VALUES
 ('20000000-0000-0000-0000-000000000001','ENC-ILL-01','Illustrative enclosure','ENCLOSURE','MECHANICAL'),
 ('20000000-0000-0000-0000-000000000002','RAIL-ILL-01','Illustrative DIN rail','DIN_RAIL','MECHANICAL'),
 ('20000000-0000-0000-0000-000000000003','DUCT-ILL-01','Illustrative wire duct','WIRE_DUCT','MECHANICAL'),
 ('20000000-0000-0000-0000-000000000004','BRK-ILL-01','Illustrative breaker','CIRCUIT_BREAKER','ELECTRICAL'),
 ('20000000-0000-0000-0000-000000000005','TERM-ILL-01','Illustrative terminal block','TERMINAL_BLOCK','ELECTRICAL'),
 ('20000000-0000-0000-0000-000000000006','PLATE-ILL-01','Illustrative backplate','MOUNTING_PLATE','MECHANICAL');
INSERT INTO component_versions(id,component_id,version_no,status,width_mm,height_mm,depth_mm,rated_voltage_v,rated_current_a,breaking_capacity_ka,pole_count,specification) VALUES
 ('21000000-0000-0000-0000-000000000001','20000000-0000-0000-0000-000000000001',1,'PUBLISHED',400,600,200,NULL,NULL,NULL,NULL,'{"backplate_width_mm":360,"backplate_height_mm":560,"ip_code":"illustrative"}'),
 ('21000000-0000-0000-0000-000000000002','20000000-0000-0000-0000-000000000002',1,'PUBLISHED',360,7.5,35,NULL,NULL,NULL,NULL,'{"nominal_length_mm":1000,"profile":"illustrative"}'),
 ('21000000-0000-0000-0000-000000000003','20000000-0000-0000-0000-000000000003',1,'PUBLISHED',300,40,60,NULL,NULL,NULL,NULL,'{"nominal_length_mm":1000,"slot_pitch_mm":10}'),
 ('21000000-0000-0000-0000-000000000004','20000000-0000-0000-0000-000000000004',1,'PUBLISHED',18,80,70,400,16,6,2,'{"trip_curve":"illustrative-only"}'),
 ('21000000-0000-0000-0000-000000000005','20000000-0000-0000-0000-000000000005',1,'PUBLISHED',6,45,50,400,32,NULL,1,'{"conductor_range_mm2":[0.5,6]}'),
 ('21000000-0000-0000-0000-000000000006','20000000-0000-0000-0000-000000000006',1,'PUBLISHED',360,560,2,NULL,NULL,NULL,NULL,'{"material":"illustrative"}');
INSERT INTO products(id,manufacturer_id,family_id,manufacturer_sku,display_name) VALUES
 ('22000000-0000-0000-0000-000000000001','10000000-0000-0000-0000-000000000001','11000000-0000-0000-0000-000000000001','DEMO-ENC-01','Illustrative enclosure SKU'),
 ('22000000-0000-0000-0000-000000000002','10000000-0000-0000-0000-000000000001','11000000-0000-0000-0000-000000000001','DEMO-BRK-01','Illustrative breaker SKU'),
 ('22000000-0000-0000-0000-000000000003','10000000-0000-0000-0000-000000000001','11000000-0000-0000-0000-000000000001','DEMO-TB-01','Illustrative terminal SKU');
INSERT INTO product_versions(id,product_id,component_version_id,version_no,status,lifecycle_status) VALUES
 ('23000000-0000-0000-0000-000000000001','22000000-0000-0000-0000-000000000001','21000000-0000-0000-0000-000000000001',1,'PUBLISHED','AVAILABLE'),
 ('23000000-0000-0000-0000-000000000002','22000000-0000-0000-0000-000000000002','21000000-0000-0000-0000-000000000004',1,'PUBLISHED','AVAILABLE'),
 ('23000000-0000-0000-0000-000000000003','22000000-0000-0000-0000-000000000003','21000000-0000-0000-0000-000000000005',1,'PUBLISHED','AVAILABLE');
INSERT INTO component_terminals(id,component_version_id,code,terminal_kind,electrical_role,connection_type) VALUES
 ('24000000-0000-0000-0000-000000000001','21000000-0000-0000-0000-000000000004','L1','SCREW','LINE','POWER'),
 ('24000000-0000-0000-0000-000000000002','21000000-0000-0000-0000-000000000004','T1','SCREW','LOAD','POWER'),
 ('24000000-0000-0000-0000-000000000003','21000000-0000-0000-0000-000000000005','1','SCREW','FEED_THROUGH','POWER');

INSERT INTO panel_archetypes(id,code,name,description) VALUES
 ('30000000-0000-0000-0000-000000000001','DB_BASIC','Illustrative distribution board','Reusable distribution-board pattern');
INSERT INTO panel_archetype_versions(id,archetype_id,version_no,status,defaults) VALUES
 ('31000000-0000-0000-0000-000000000001','30000000-0000-0000-0000-000000000001',1,'PUBLISHED','{"currency":"illustrative"}');
INSERT INTO functional_modules(id,code,name) VALUES
 ('32000000-0000-0000-0000-000000000001','INCOMER','Incoming protection');
INSERT INTO functional_module_versions(id,module_id,version_no,status) VALUES
 ('33000000-0000-0000-0000-000000000001','32000000-0000-0000-0000-000000000001',1,'PUBLISHED');
INSERT INTO archetype_modules(archetype_version_id,module_version_id,sequence_no,required) VALUES
 ('31000000-0000-0000-0000-000000000001','33000000-0000-0000-0000-000000000001',1,true);
INSERT INTO module_role_requirements(module_version_id,role_code,quantity_min,required_properties) VALUES
 ('33000000-0000-0000-0000-000000000001','INCOMER_PROTECTION',1,'{"rated_current_a":{"operator":"MIN","value":"from-project-requirement"}}');

INSERT INTO cad_models(id,code,name,model_kind) VALUES
 ('40000000-0000-0000-0000-000000000001','ENCLOSURE_PARAM','Illustrative enclosure model','PART'),
 ('40000000-0000-0000-0000-000000000002','DB_ASSEMBLY','Illustrative DB assembly','ASSEMBLY');
INSERT INTO cad_model_versions(id,cad_model_id,version_no,status,coordinate_system,feature_definition,generator_name,generator_version) VALUES
 ('41000000-0000-0000-0000-000000000001','40000000-0000-0000-0000-000000000001',1,'PUBLISHED','{"handedness":"right","length_unit":"mm","origin":"lower-left-front"}','{"features":["shell","backplate","door"]}','illustrative-generator','0.1'),
 ('41000000-0000-0000-0000-000000000002','40000000-0000-0000-0000-000000000002',1,'PUBLISHED','{"handedness":"right","length_unit":"mm"}','{"features":["enclosure","rail","duct","breaker"]}','illustrative-generator','0.1');
INSERT INTO cad_parameter_definitions(cad_model_version_id,code,value_type,unit_code,default_value,min_value,max_value,editable,derived,description) VALUES
 ('41000000-0000-0000-0000-000000000001','width_mm','DECIMAL','mm','400',200,1200,true,false,'Project-configurable illustrative model dimension'),
 ('41000000-0000-0000-0000-000000000001','height_mm','DECIMAL','mm','600',200,2000,true,false,'Project-configurable illustrative model dimension'),
 ('41000000-0000-0000-0000-000000000001','depth_mm','DECIMAL','mm','200',80,600,true,false,'Project-configurable illustrative model dimension'),
 ('41000000-0000-0000-0000-000000000001','usable_width_mm','DECIMAL','mm',NULL,NULL,NULL,false,true,'width less declared margins; evaluate in constrained engine');
INSERT INTO cad_features(cad_model_version_id,code,sequence_no,operation_code,feature_definition,depends_on_codes) VALUES
 ('41000000-0000-0000-0000-000000000001','shell',1,'BOX_SHELL','{"operation":"illustrative-shell","wall_parameter":"wall_thickness_mm"}','{width_mm,height_mm,depth_mm}');
INSERT INTO cad_assets(id,cad_model_version_id,asset_role,file_format,storage_key,sha256,byte_size,generator_name,generator_version,generation_status) VALUES
 ('42000000-0000-0000-0000-000000000001','41000000-0000-0000-0000-000000000001','PREVIEW','GLB','sha256/00/00/0000000000000000000000000000000000000000000000000000000000000000.glb',repeat('0',64),0,'illustrative-generator','0.1','READY');
INSERT INTO component_cad_models(component_version_id,cad_model_version_id,representation_role) VALUES
 ('21000000-0000-0000-0000-000000000001','41000000-0000-0000-0000-000000000001','PRIMARY');
INSERT INTO cad_assemblies(id,code,name) VALUES ('43000000-0000-0000-0000-000000000001','DB_BASIC_ASM','Illustrative DB assembly definition');
INSERT INTO cad_assembly_versions(id,assembly_id,version_no,status) VALUES
 ('44000000-0000-0000-0000-000000000001','43000000-0000-0000-0000-000000000001',1,'PUBLISHED');
INSERT INTO cad_assembly_members(assembly_version_id,member_cad_model_version_id,member_code,transform) VALUES
 ('44000000-0000-0000-0000-000000000001','41000000-0000-0000-0000-000000000001','ENCLOSURE','{"translation_mm":[0,0,0],"quaternion_xyzw":[0,0,0,1]}'),
 ('44000000-0000-0000-0000-000000000001','41000000-0000-0000-0000-000000000002','PANEL_CONTENTS','{"translation_mm":[0,0,0],"quaternion_xyzw":[0,0,0,1]}');

INSERT INTO questionnaires(id,code,name) VALUES ('50000000-0000-0000-0000-000000000001','DB_REQ','Illustrative DB requirements');
INSERT INTO questionnaire_versions(id,questionnaire_id,version_no,status) VALUES
 ('51000000-0000-0000-0000-000000000001','50000000-0000-0000-0000-000000000001',1,'PUBLISHED');
INSERT INTO questionnaire_sections(id,questionnaire_version_id,code,title,sequence_no) VALUES
 ('52000000-0000-0000-0000-000000000001','51000000-0000-0000-0000-000000000001','SUPPLY','Supply requirements',1);
INSERT INTO questions(id,questionnaire_version_id,section_id,code,prompt,value_type,unit_code,required,sequence_no) VALUES
 ('53000000-0000-0000-0000-000000000001','51000000-0000-0000-0000-000000000001','52000000-0000-0000-0000-000000000001','system_voltage','Nominal system voltage','MEASUREMENT','V',true,1),
 ('53000000-0000-0000-0000-000000000002','51000000-0000-0000-0000-000000000001','52000000-0000-0000-0000-000000000001','panel_use','Panel use','SINGLE_SELECT',NULL,true,2),
 ('53000000-0000-0000-0000-000000000003','51000000-0000-0000-0000-000000000001','52000000-0000-0000-0000-000000000001','motor_count','Number of motors','INTEGER',NULL,true,3);
INSERT INTO question_options(question_id,option_code,label,value,sequence_no) VALUES
 ('53000000-0000-0000-0000-000000000002','distribution','Distribution','"distribution"',1),
 ('53000000-0000-0000-0000-000000000002','motor_control','Motor control','"motor_control"',2);
INSERT INTO question_dependencies(question_id,depends_on_question_id,operator_code,expected_value) VALUES
 ('53000000-0000-0000-0000-000000000003','53000000-0000-0000-0000-000000000002','EQ','"motor_control"');
INSERT INTO archetype_questionnaires(archetype_version_id,questionnaire_version_id,sequence_no) VALUES
 ('31000000-0000-0000-0000-000000000001','51000000-0000-0000-0000-000000000001',1);

INSERT INTO rule_sets(id,code,name) VALUES ('60000000-0000-0000-0000-000000000001','DB_BASELINE','Illustrative demonstration rules');
INSERT INTO rule_set_versions(id,rule_set_id,version_no,status) VALUES
 ('61000000-0000-0000-0000-000000000001','60000000-0000-0000-0000-000000000001',1,'PUBLISHED');
INSERT INTO design_rules(id,code,name,engine_handler) VALUES
 ('62000000-0000-0000-0000-000000000001','PLACEMENT_BOUNDS','Placement within enclosure bounds','placement_bounds'),
 ('62000000-0000-0000-0000-000000000002','RATING_MATCH','Selected rating meets requirement','rating_minimum');
INSERT INTO design_rule_versions(id,rule_id,version_no,status,severity,hardness,parameters,provenance) VALUES
 ('63000000-0000-0000-0000-000000000001','62000000-0000-0000-0000-000000000001',1,'PUBLISHED','ERROR','HARD','{}','{"source":"illustrative software rule","verified_standard":false}'),
 ('63000000-0000-0000-0000-000000000002','62000000-0000-0000-0000-000000000002',1,'PUBLISHED','WARNING','HARD','{}','{"source":"illustrative software rule","verified_standard":false}');
INSERT INTO rule_set_members(rule_set_version_id,rule_version_id) VALUES
 ('61000000-0000-0000-0000-000000000001','63000000-0000-0000-0000-000000000001'),
 ('61000000-0000-0000-0000-000000000001','63000000-0000-0000-0000-000000000002');
INSERT INTO electrical_templates(id,code,name) VALUES
 ('70000000-0000-0000-0000-000000000001','BREAKER_FEEDER','Illustrative breaker feeder');
INSERT INTO electrical_template_versions(id,template_id,version_no,status) VALUES
 ('71000000-0000-0000-0000-000000000001','70000000-0000-0000-0000-000000000001',1,'PUBLISHED');
INSERT INTO archetype_electrical_templates(archetype_version_id,template_version_id,sequence_no,required) VALUES
 ('31000000-0000-0000-0000-000000000001','71000000-0000-0000-0000-000000000001',1,true);
INSERT INTO template_component_roles(id,template_version_id,role_code,component_category) VALUES
 ('72000000-0000-0000-0000-000000000001','71000000-0000-0000-0000-000000000001','BREAKER','CIRCUIT_BREAKER'),
 ('72000000-0000-0000-0000-000000000002','71000000-0000-0000-0000-000000000001','LOAD_TERMINAL','TERMINAL_BLOCK');
INSERT INTO template_terminals(id,template_role_id,terminal_code,terminal_role) VALUES
 ('73000000-0000-0000-0000-000000000001','72000000-0000-0000-0000-000000000001','T1','LOAD'),
 ('73000000-0000-0000-0000-000000000002','72000000-0000-0000-0000-000000000002','1','LINE');
INSERT INTO template_connections(id,template_version_id,from_template_terminal_id,to_template_terminal_id,connection_code,connection_type) VALUES
 ('74000000-0000-0000-0000-000000000001','71000000-0000-0000-0000-000000000001','73000000-0000-0000-0000-000000000001','73000000-0000-0000-0000-000000000002','BREAKER_TO_LOAD','POWER');

INSERT INTO projects(id,project_code,name,created_by) VALUES
 ('80000000-0000-0000-0000-000000000001','DEMO-PROJECT-01','Illustrative DB project','sample');
INSERT INTO project_revisions(id,project_id,revision_no,status,archetype_version_id,rule_set_version_id,model_manifest,content_sha256,created_by) VALUES
 ('81000000-0000-0000-0000-000000000001','80000000-0000-0000-0000-000000000001',1,'PUBLISHED','31000000-0000-0000-0000-000000000001','61000000-0000-0000-0000-000000000001',
  '{"electrical_template_versions":["71000000-0000-0000-0000-000000000001"],"generator":{"name":"illustrative-generator","version":"0.1"}}',repeat('a',64),'sample');
INSERT INTO questionnaire_sessions(id,project_id,questionnaire_version_id,status,submitted_at) VALUES
 ('82000000-0000-0000-0000-000000000001','80000000-0000-0000-0000-000000000001','51000000-0000-0000-0000-000000000001','SUBMITTED',now());
INSERT INTO question_answers(id,session_id,question_id,answer_value,actor_id) VALUES
 ('83000000-0000-0000-0000-000000000001','82000000-0000-0000-0000-000000000001','53000000-0000-0000-0000-000000000001','{"value":230,"unit":"V"}','sample'),
 ('83000000-0000-0000-0000-000000000002','82000000-0000-0000-0000-000000000001','53000000-0000-0000-0000-000000000002','"distribution"','sample');
INSERT INTO project_requirements(id,project_id,project_revision_id,code,operator_code,value,unit_code,resolution_status) VALUES
 ('84000000-0000-0000-0000-000000000001','80000000-0000-0000-0000-000000000001','81000000-0000-0000-0000-000000000001','system_voltage','EQ','{"value":230}','V','RESOLVED'),
 ('84000000-0000-0000-0000-000000000002','80000000-0000-0000-0000-000000000001','81000000-0000-0000-0000-000000000001','incomer_current','MIN','{"value":16}','A','RESOLVED');
INSERT INTO requirement_sources(requirement_id,source_kind,question_answer_id,source_ref,details) VALUES
 ('84000000-0000-0000-0000-000000000001','ANSWER','83000000-0000-0000-0000-000000000001','question:system_voltage','{"mapping":"answer-to-requirement-v1"}'),
 ('84000000-0000-0000-0000-000000000002','ENGINEER',NULL,'illustrative design decision','{"value_is_demo":true}');
INSERT INTO revision_components(id,project_revision_id,component_version_id,product_version_id,role_code,selected_by,selection_evidence) VALUES
 ('85000000-0000-0000-0000-000000000001','81000000-0000-0000-0000-000000000001','21000000-0000-0000-0000-000000000004','23000000-0000-0000-0000-000000000002','INCOMER_PROTECTION','SELECTOR','{"reason":"illustrative sample only"}');
INSERT INTO project_parameter_overrides(project_revision_id,target_kind,target_code,value,unit_code,source_kind) VALUES
 ('81000000-0000-0000-0000-000000000001','ENCLOSURE','width_mm','400','mm','USER');
INSERT INTO cem_snapshots(project_revision_id,schema_version,snapshot,sha256) VALUES
 ('81000000-0000-0000-0000-000000000001',1,'{"project_id":"80000000-0000-0000-0000-000000000001","components":[{"stable_key":"QF001","role":"INCOMER_PROTECTION"}],"nets":[{"stable_key":"N001"}]}',repeat('b',64));
INSERT INTO cem_component_instances(id,project_revision_id,stable_key,role_code,component_version_id,product_version_id,display_name,source_template_role_id) VALUES
 ('86000000-0000-0000-0000-000000000001','81000000-0000-0000-0000-000000000001','QF001','INCOMER_PROTECTION','21000000-0000-0000-0000-000000000004','23000000-0000-0000-0000-000000000002','Illustrative incoming breaker','72000000-0000-0000-0000-000000000001'),
 ('86000000-0000-0000-0000-000000000002','81000000-0000-0000-0000-000000000001','X001','TERMINAL_INTERFACE','21000000-0000-0000-0000-000000000005','23000000-0000-0000-0000-000000000003','Illustrative terminal block','72000000-0000-0000-0000-000000000002');
INSERT INTO cem_terminal_instances(id,component_instance_id,stable_key,terminal_code,terminal_role) VALUES
 ('87000000-0000-0000-0000-000000000001','86000000-0000-0000-0000-000000000001','QF001:T1','T1','LOAD'),
 ('87000000-0000-0000-0000-000000000002','86000000-0000-0000-0000-000000000002','X001:1','1','LINE');
INSERT INTO cem_nets(id,project_revision_id,stable_key,net_code,wire_class,nominal_voltage_v) VALUES
 ('88000000-0000-0000-0000-000000000001','81000000-0000-0000-0000-000000000001','N001','L-OUT','POWER',230);
INSERT INTO cem_net_terminals(net_id,terminal_instance_id,connection_role) VALUES
 ('88000000-0000-0000-0000-000000000001','87000000-0000-0000-0000-000000000001','SOURCE'),
 ('88000000-0000-0000-0000-000000000001','87000000-0000-0000-0000-000000000002','LOAD');
INSERT INTO cem_conductors(id,net_id,conductor_code,conductor_type,cross_section_mm2) VALUES
 ('89000000-0000-0000-0000-000000000001','88000000-0000-0000-0000-000000000001','W001','COPPER_INSULATED',2.5);
INSERT INTO pdm_snapshots(project_revision_id,schema_version,snapshot,sha256) VALUES
 ('81000000-0000-0000-0000-000000000001',1,'{"coordinate_frame":"lower-left-front, mm","placements":[{"cem_key":"QF001","xyz":[30,40,20]}]}',repeat('c',64));
INSERT INTO pdm_enclosures(id,project_revision_id,component_version_id,cad_model_version_id,stable_key,width_mm,height_mm,depth_mm,coordinate_frame,parameters) VALUES
 ('90000000-0000-0000-0000-000000000001','81000000-0000-0000-0000-000000000001','21000000-0000-0000-0000-000000000001','41000000-0000-0000-0000-000000000001','ENC01',400,600,200,'{"origin":"lower-left-front","units":"mm","handedness":"right"}','{"width_mm":400,"height_mm":600,"depth_mm":200}');
INSERT INTO pdm_mounting_structures(id,project_revision_id,enclosure_id,stable_key,structure_kind,component_version_id,transform,dimensions_mm) VALUES
 ('91000000-0000-0000-0000-000000000001','81000000-0000-0000-0000-000000000001','90000000-0000-0000-0000-000000000001','RAIL01','DIN_RAIL','21000000-0000-0000-0000-000000000002','{"translation_mm":[20,100,30],"quaternion_xyzw":[0,0,0,1]}','{"length":360,"width":35,"height":7.5}'),
 ('91000000-0000-0000-0000-000000000002','81000000-0000-0000-0000-000000000001','90000000-0000-0000-0000-000000000001','DUCT01','WIRE_DUCT','21000000-0000-0000-0000-000000000003','{"translation_mm":[10,20,30],"quaternion_xyzw":[0,0,0,1]}','{"length":560,"width":40,"height":60}'),
 ('91000000-0000-0000-0000-000000000003','81000000-0000-0000-0000-000000000001','90000000-0000-0000-0000-000000000001','PLATE01','BACKPLATE','21000000-0000-0000-0000-000000000006','{"translation_mm":[20,20,20],"quaternion_xyzw":[0,0,0,1]}','{"width":360,"height":560,"thickness":2}');
INSERT INTO pdm_component_instances(id,project_revision_id,cem_component_instance_id,cad_model_version_id,stable_key) VALUES
 ('92000000-0000-0000-0000-000000000001','81000000-0000-0000-0000-000000000001','86000000-0000-0000-0000-000000000001',NULL,'PDM-QF001'),
 ('92000000-0000-0000-0000-000000000002','81000000-0000-0000-0000-000000000001','86000000-0000-0000-0000-000000000002',NULL,'PDM-X001');
INSERT INTO pdm_placements(pdm_component_instance_id,mounting_structure_id,transform,bounding_box_mm,zone_code) VALUES
 ('92000000-0000-0000-0000-000000000001','91000000-0000-0000-0000-000000000001','{"translation_mm":[30,100,30],"quaternion_xyzw":[0,0,0,1]}','{"min":[30,100,30],"max":[48,180,100]}','MAIN'),
 ('92000000-0000-0000-0000-000000000002','91000000-0000-0000-0000-000000000001','{"translation_mm":[60,100,30],"quaternion_xyzw":[0,0,0,1]}','{"min":[60,100,30],"max":[66,145,80]}','MAIN');
INSERT INTO pdm_routes(project_revision_id,stable_key,net_id,conductor_id,waypoints_mm,length_mm) VALUES
 ('81000000-0000-0000-0000-000000000001','ROUTE-N001','88000000-0000-0000-0000-000000000001','89000000-0000-0000-0000-000000000001','[{"x":48,"y":120,"z":100},{"x":60,"y":120,"z":100}]',12);
INSERT INTO project_cad_instances(project_revision_id,cad_model_version_id,stable_key,supplied_values,derived_values,evaluated_values,generation_status) VALUES
 ('81000000-0000-0000-0000-000000000001','41000000-0000-0000-0000-000000000001','ENC01-CAD','{"width_mm":400,"height_mm":600,"depth_mm":200}','{"usable_width_mm":360}','{"width_mm":400,"height_mm":600,"depth_mm":200,"generator":"illustrative-generator@0.1"}','READY');
INSERT INTO project_cad_assembly_instances(id,project_revision_id,assembly_version_id,stable_key,transform,generation_status) VALUES
 ('95000000-0000-0000-0000-000000000001','81000000-0000-0000-0000-000000000001','44000000-0000-0000-0000-000000000001','PANEL-ASSEMBLY','{"translation_mm":[0,0,0],"quaternion_xyzw":[0,0,0,1]}','READY');
INSERT INTO project_cad_assembly_members(assembly_instance_id,assembly_member_id,member_cad_model_version_id,transform,parameter_values) VALUES
 ('95000000-0000-0000-0000-000000000001',(SELECT id FROM cad_assembly_members WHERE assembly_version_id='44000000-0000-0000-0000-000000000001' AND member_code='ENCLOSURE'),'41000000-0000-0000-0000-000000000001','{"translation_mm":[0,0,0],"quaternion_xyzw":[0,0,0,1]}','{"width_mm":400,"height_mm":600,"depth_mm":200}'),
 ('95000000-0000-0000-0000-000000000001',(SELECT id FROM cad_assembly_members WHERE assembly_version_id='44000000-0000-0000-0000-000000000001' AND member_code='PANEL_CONTENTS'),'41000000-0000-0000-0000-000000000002','{"translation_mm":[0,0,0],"quaternion_xyzw":[0,0,0,1]}','{}');
INSERT INTO revision_dependencies(project_revision_id,source_kind,source_key,target_kind,target_key,dependency_kind,input_sha256,output_sha256) VALUES
 ('81000000-0000-0000-0000-000000000001','PARAMETER','ENC01.width_mm','PDM','RAIL01.length_mm','DERIVES',repeat('1',64),repeat('2',64)),
 ('81000000-0000-0000-0000-000000000001','PDM','RAIL01','ROUTE','ROUTE-N001','GEOMETRY_INPUT',repeat('2',64),repeat('3',64));
INSERT INTO provenance(project_id,project_revision_id,subject_kind,subject_key,source_kind,source_ref,actor_id,details) VALUES
 ('80000000-0000-0000-0000-000000000001','81000000-0000-0000-0000-000000000001','REQUIREMENT','incomer_current','ENGINEER','sample fixture','sample','{"illustrative":true}');
INSERT INTO validation_runs(id,project_revision_id,rule_set_version_id,engine_name,engine_version,status,input_sha256,completed_at) VALUES
 ('93000000-0000-0000-0000-000000000001','81000000-0000-0000-0000-000000000001','61000000-0000-0000-0000-000000000001','illustrative-validator','0.1','COMPLETED_WITH_WARNINGS',repeat('4',64),now());
INSERT INTO validation_results(validation_run_id,rule_version_id,rule_code,result_status,affected_entities,measured_values,message,evidence) VALUES
 ('93000000-0000-0000-0000-000000000001','63000000-0000-0000-0000-000000000001','PLACEMENT_BOUNDS','PASS','["PDM-QF001","PDM-X001"]','{"bounds":"illustrative"}','Illustrative geometry check passed.','{"fixture":true}');
INSERT INTO generated_artifacts(id,project_revision_id,artifact_type,file_format,storage_key,sha256,byte_size,generator_name,generator_version,source_model_kind,source_model_sha256,generation_status,completed_at) VALUES
 ('94000000-0000-0000-0000-000000000001','81000000-0000-0000-0000-000000000001','CAD_ASSEMBLY','STEP','sha256/aa/bb/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.step',repeat('a',64),0,'illustrative-generator','0.1','PDM',repeat('c',64),'READY',now());
COMMIT;
