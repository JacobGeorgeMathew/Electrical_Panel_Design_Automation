"""Resolve DB questionnaire choices from published questions and actual engine capabilities.

No catalog/questionnaire versions are edited. This materialized view is also used
by server validation, so direct API requests cannot bypass the shown choices.
"""
from copy import deepcopy
import math
from app.services.component_selector import ComponentSelector
from app.services.netlist_engine import NetlistEngine
from app.services.design_errors import DesignError
from app.algorithms.duct_routing import DuctRouter


class CatalogRows:
    def __init__(self,rows):self.rows=rows
    def get_by_id(self,key):return next((r for r in self.rows if r['id']==key),None)
    def filter_candidates(self,category,min_current=0,min_breaking_capacity=0,poles=None):
        return [r for r in self.rows if r['category']==category and r['current_rating']>=min_current
            and r['breaking_capacity']>=min_breaking_capacity and (poles is None or r['poles']==poles)]


def resolve_choices(template,rows):
    result=deepcopy(template)
    if template.get('archetype')!='DB':return result
    questions={q['id']:q for q in result['questions']}
    selector=ComponentSelector(CatalogRows(rows));netlist=NetlistEngine()
    phase_options=questions['phases'].get('options') or [1,3]
    rating_options=questions['incomer_rating'].get('options') or []
    supported=[]
    for phase in phase_options:
        for rating in rating_options:
            if not any(c['category']=='MCCB' and c['current_rating']==rating and c['poles']==phase for c in rows):continue
            try:
                parts=selector.select_components(rating,4,phase,busbar_rating=rating*1.25)
                nets=netlist.generate_netlist(None,parts,phases=phase)
                if netlist.validate_netlist(nets,parts)[0]:supported.append((phase,rating))
            except DesignError:continue
    for key,index in [('phases',0),('incomer_rating',1)]:
        q=questions[key];q['options']=sorted({pair[index] for pair in supported})
        q['help_text']='Choices supported by the current incomer, busbar and terminal catalog. Other standard ratings need additional catalog parts.'
    q=questions['num_feeders'];bounds=q.get('validation') or {};allowed=[]
    if supported:
        phase,rating=supported[0]
        for count in range(int(bounds.get('min',4)),int(bounds.get('max',48))+1):
            try:
                parts=selector.select_components(rating,count,phase,busbar_rating=rating*1.25)
                nets=netlist.generate_netlist(None,parts,phases=phase)
                if sum(len(n.connections) for n in nets)<=DuctRouter.MAX_CONDUCTORS:allowed.append(count)
            except DesignError:continue
    q['options']=allowed
    q['help_text']='Bounded by available bar ways and the current duct routing capacity; full placement and thermal feasibility are checked during generation.'
    q=questions['spare_capacity_pct'];bounds=q.get('validation') or {}
    q['options']=list(range(int(bounds.get('min',0)),int(bounds.get('max',50))+1))
    result['choice_policy']='catalog-db-v1'
    return result


def suggest_requirements(template,rows,values):
    questions={q['id']:q for q in template['questions']}
    effective={q['id']:q.get('default') for q in template['questions']};effective.update(values)
    count=effective.get('num_feeders');phase=effective.get('phases');spare=effective.get('spare_capacity_pct')
    for key in ('num_feeders','phases','spare_capacity_pct'):
        value=effective.get(key)
        if type(value) not in (int,float) or not math.isfinite(value) or value not in (questions[key].get('options') or []):
            return {'suggestions':{},'estimates':{},'message':'Choose supported feeder, phase and spare-capacity values first.'}
    ratings=questions['incomer_rating'].get('options') or []
    if not ratings:return {'suggestions':{},'estimates':{},'message':'No compatible incomer is available in the current catalog.'}
    parts=ComponentSelector(CatalogRows(rows)).select_components(min(ratings),int(count),int(phase),busbar_rating=min(ratings)*1.25)
    currents=[0.0]*int(phase)
    for index,feeder in enumerate(c for c in parts if c.category=='MCB'):
        if feeder.poles>1:
            for p in range(min(feeder.poles,len(currents))):currents[p]+=feeder.current_rating
        else:currents[index%len(currents)]+=feeder.current_rating
    diversity=.75  # Same prototype assumption used by CalculationEngine.
    demand=max(currents)*diversity*(1+spare/100)
    rating=next((r for r in sorted(ratings) if r>=demand),None)
    return {'suggestions':({'incomer_rating':{'value':rating,'reason':f'Next supported rating above the estimated {demand:.1f} A maximum phase demand.'}} if rating else {}),
        'estimates':{'phase_connected_current_a':currents,'estimated_max_phase_demand_a':round(demand,2),
            'spare_feeder_spaces':math.ceil(count*spare/100),'planning_total_feeder_spaces':count+math.ceil(count*spare/100)},
        'assumptions':['Uses the existing automatic 16 A / 32 A / 40 A feeder mix, not measured connected loads.',
            'Uses the prototype 0.75 diversity factor and your selected spare percentage.',
            'Spare spaces are a planning estimate; extra physical feeder bays are not automatically generated.'],
        'message':'Estimate only. Confirm actual loads before choosing an incomer; your selected value is never changed automatically.' if rating else 'Estimated demand exceeds supported incomers. Revise loads or extend the catalog.'}
