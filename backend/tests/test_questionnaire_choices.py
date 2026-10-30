import json
from pathlib import Path
import pytest
from app.services.questionnaire_choices import resolve_choices,suggest_requirements
from app.services.requirement_engine import RequirementEngine
from app.repositories.component_repository import ComponentRepository

@pytest.fixture
def profile():
    template=json.loads((Path(__file__).parents[1]/'app/data/panel_templates.json').read_text(encoding='utf-8'))[0]
    rows=ComponentRepository().get_all()
    frozen=json.dumps(template,sort_keys=True)
    result=resolve_choices(template,rows)
    assert json.dumps(template,sort_keys=True)==frozen
    return result,rows


def test_choices_are_bounded_by_actual_catalog_and_router(profile):
    template,_=profile;questions={q['id']:q for q in template['questions']}
    assert questions['incomer_rating']['options']==[100,250]
    assert questions['phases']['options']==[3]
    assert questions['num_feeders']['options']==list(range(4,17))
    assert questions['spare_capacity_pct']['options']==list(range(51))
    assert all(q.get('options') for q in questions.values() if q['type']=='number')


@pytest.mark.parametrize('field,value',[('incomer_rating',300),('incomer_rating',400),('incomer_rating',160),('num_feeders',17),('phases',1),('spare_capacity_pct',20.5),('frequency',55)])
def test_server_rejects_values_that_cannot_be_selected(profile,field,value):
    template,_=profile
    result=RequirementEngine(templates={'DB':template}).validate_requirements('P','DB',{field:value})
    assert not result.is_valid


@pytest.mark.parametrize('feeders,rating',[(4,100),(8,250),(12,250),(16,250)])
def test_feeder_suggestions_explain_their_assumptions_and_never_mutate_choices(profile,feeders,rating):
    template,rows=profile;values={'num_feeders':feeders,'incomer_rating':100,'spare_capacity_pct':20}
    result=suggest_requirements(template,rows,values)
    assert result['suggestions']['incomer_rating']['value']==rating
    assert values['incomer_rating']==100
    assert result['estimates']['spare_feeder_spaces']==__import__('math').ceil(feeders*.2)
    assert any('not measured' in a for a in result['assumptions'])


def test_demand_above_the_catalog_has_no_fabricated_suggestion(profile):
    template,rows=profile
    result=suggest_requirements(template,rows,{'num_feeders':16,'spare_capacity_pct':50})
    assert not result['suggestions']
    assert 'exceeds' in result['message']


def test_questions_suggestions_and_writes_use_the_same_choices(api):
    project=api.post('/api/projects',json={'name':'Questionnaire choices'}).json();key=project['id']
    questions=api.get('/api/projects/'+key+'/requirements/questions').json()
    assert next(q for q in questions if q['id']=='incomer_rating')['options']==[100,250]
    for path in ['/api/projects/'+key+'/requirements/suggestions','/api/archetypes/DB/suggestions']:
        result=api.post(path,json={'num_feeders':4}).json()
        assert result['suggestions']['incomer_rating']['value']==100
    after=api.get('/api/projects/'+key).json()
    assert after['requirements']==project['requirements'] and after['lock_version']==project['lock_version']
    assert not api.post('/api/projects/'+key+'/requirements/validate',json={'incomer_rating':300}).json()['is_valid']
    rejected=api.patch('/api/projects/'+key,json={'expected_version':project['lock_version'],'requirements':{'incomer_rating':300}})
    assert rejected.status_code==422

def test_four_feeder_suggested_rating_generates_a_real_design():
    from app.services.orchestrator import DesignOrchestrator
    result=DesignOrchestrator().generate_design('SUGGESTION-DEMO',{'num_feeders':4,'incomer_rating':100},persist_requirements=False)
    assert result['validation_errors']==[]
    assert next(c for c in result['cem']['components'] if c['category']=='MCCB')['current_rating']==100
