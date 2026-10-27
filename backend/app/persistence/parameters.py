"""Small declarative parameter evaluator; no executable stored Python or SQL."""
import ast
import math
import operator
from app.persistence.repositories import PersistenceError

_OPS={ast.Add:operator.add,ast.Sub:operator.sub,ast.Mult:operator.mul,ast.Div:operator.truediv}
_LENGTH={'mm':1.0,'cm':10.0,'m':1000.0}


def expression(source,values):
    def visit(node):
        if isinstance(node,ast.Expression): return visit(node.body)
        if isinstance(node,ast.Constant) and type(node.value) in (int,float): return node.value
        if isinstance(node,ast.Name) and node.id in values: return values[node.id]
        if isinstance(node,ast.BinOp) and type(node.op) in _OPS: return _OPS[type(node.op)](visit(node.left),visit(node.right))
        if isinstance(node,ast.UnaryOp) and isinstance(node.op,ast.USub): return -visit(node.operand)
        raise ValueError('Unsupported parameter expression.')
    return visit(ast.parse(source,mode='eval'))


def resolve_parameters(definitions, supplied):
    by_code={p['code']:p for p in definitions}
    if set(supplied)-set(by_code):
        raise PersistenceError('INVALID_PARAMETER','Unknown CAD parameter.')
    values={}
    for code,p in by_code.items():
        if code in supplied and (not p['editable'] or p['derived']):
            raise PersistenceError('FIXED_PARAMETER',f"Parameter '{code}' is fixed by its model version.")
        raw=supplied.get(code,p.get('default_value'))
        if isinstance(raw,dict) and 'value' in raw and 'unit' in raw:
            source_unit,target_unit=raw['unit'],p['unit_code']
            if source_unit==target_unit: raw=raw['value']
            elif source_unit in _LENGTH and target_unit in _LENGTH:
                raw=raw['value']*_LENGTH[source_unit]/_LENGTH[target_unit]
            else: raise PersistenceError('INVALID_UNIT',f"Incompatible unit for '{code}'.")
        if not p['derived']: values[code]=raw
    pending={code for code,p in by_code.items() if p['derived']}
    try:
        while pending:
            done=[]
            for code in sorted(pending):
                p=by_code[code]
                if set(p.get('dependencies') or []).issubset(values):
                    values[code]=expression(p['expression'],values)
                    done.append(code)
            if not done: raise ValueError('Cyclic or unresolved parameter dependencies.')
            pending-=set(done)
        for code,value in values.items():
            p=by_code[code]
            kind=p['value_type']
            if kind in {'INTEGER','DECIMAL'}:
                if type(value) not in (int,float) or not math.isfinite(value): raise ValueError()
                if kind=='INTEGER' and int(value)!=value: raise ValueError()
                if p.get('min_value') is not None and value < float(p['min_value']): raise ValueError()
                if p.get('max_value') is not None and value > float(p['max_value']): raise ValueError()
            elif kind=='BOOLEAN' and type(value) is not bool: raise ValueError()
            elif kind in {'STRING','ENUM'} and not isinstance(value,str): raise ValueError()
            elif kind=='OBJECT' and not isinstance(value,dict): raise ValueError()
            if p.get('allowed_values') is not None and value not in p['allowed_values']: raise ValueError()
    except (ValueError,TypeError,ZeroDivisionError,SyntaxError,KeyError):
        raise PersistenceError('INVALID_PARAMETER','CAD parameters violate the pinned model schema or dependencies.') from None
    return values
