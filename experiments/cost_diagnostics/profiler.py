"""Insert timers into the original AST, with an automatic arithmetic identity check."""
import ast
from contextlib import contextmanager
import copy
import inspect
import textwrap
from time import perf_counter

import numpy as np
from experiments.public_scaling.certification import RelationGenerator

PHASES = ('advance', 'candidates', 'bitsets', 'certification', 'endpoints', 'teacher', 'cache', 'finalize')


def measured(phase, nodes, capture=None):
    return ast.With(items=[ast.withitem(context_expr=ast.Call(
        func=ast.Attribute(value=ast.Name(id='self', ctx=ast.Load()),attr='_measure',ctx=ast.Load()),
        args=[ast.Constant(phase)]+([] if capture is None else [ast.parse(capture,mode='eval').body]),keywords=[]))],body=nodes)


def find(nodes, prefix):
    hits = [i for i,n in enumerate(nodes) if ast.unparse(ast.fix_missing_locations(n)).startswith(prefix)]
    if len(hits)!=1: raise RuntimeError(f'Core AST changed: {prefix}: {hits}')
    return hits[0]


def instrument(name):
    original=ast.parse(textwrap.dedent(inspect.getsource(getattr(RelationGenerator,name))))
    tree=copy.deepcopy(original); fn=tree.body[0]; b=fn.body
    if name in ('_advance','candidate_matrix'):
        fn.body=[measured('advance' if name=='_advance' else 'candidates',b)]
    elif name=='candidate_sets':
        fn.body=b[:1]+[measured('bitsets',b[1:])]
    elif name=='_refresh':
        cache=find(b,'self.winners[ids] =')
        fn.body=b[:1]+[measured('teacher',b[1:cache]),measured('cache',b[cache:])]
    elif name=='generate':
        point=next(n for n in b if isinstance(n,ast.If) and ast.unparse(n.test)=="self.mode == 'point'")
        pb=point.body; ids=find(pb,'ids ='); refresh=find(pb,'self._refresh(')
        point.body=pb[:1]+[measured('certification',pb[1:ids]),measured('endpoints',pb[ids:refresh],'lambda: self._capture(ids)')]+pb[refresh:refresh+1]+[measured('finalize',pb[refresh+1:])]
        start=find(b,'different ='); needed=find(b,'needed ='); refresh=find(b,'self._refresh(')
        fn.body=b[:start]+[measured('certification',b[start:needed]),measured('endpoints',b[needed:refresh],'lambda: self._capture(ids, needed)')]+b[refresh:refresh+1]+[measured('finalize',b[refresh+1:])]
    else: raise ValueError(name)
    class Strip(ast.NodeTransformer):
        def visit_With(self,node):
            # This source has no original with-statements. Remove timer wrappers only.
            if not ast.unparse(node.items[0].context_expr).startswith('self._measure('):
                raise RuntimeError('Unexpected context manager')
            return [self.visit(n) for n in node.body]
    stripped=Strip().visit(copy.deepcopy(tree))
    if ast.dump(stripped,include_attributes=False)!=ast.dump(original,include_attributes=False):
        raise RuntimeError(f'Instrumentation changed arithmetic: {name}')
    ns={'np':np,'hard_relations':__import__('experiments.public_scaling.certification',fromlist=['hard_relations']).hard_relations}
    exec(compile(ast.fix_missing_locations(tree),f'<timed original {name}>','exec'),ns)
    return ns[name]


_generate=instrument('generate')


class ProfiledGenerator(RelationGenerator):
    """Same arithmetic/cache transitions; timings include instrumentation overhead."""
    _advance=instrument('_advance')
    candidate_matrix=instrument('candidate_matrix')
    candidate_sets=instrument('candidate_sets')
    _refresh=instrument('_refresh')

    def __init__(self,*args,**kwargs):
        self.phase_seconds={p:0.0 for p in PHASES}
        self.diagnostics={}
        super().__init__(*args,**kwargs)

    @contextmanager
    def _measure(self,phase,capture=None):
        start=perf_counter()
        try: yield
        finally:
            self.phase_seconds[phase]+=perf_counter()-start
            if capture is not None: capture()

    def _capture(self,ids,needed=None):
        self.diagnostics={'selected_endpoints':len(ids),
                          'unresolved_endpoint_union':None if needed is None else int(needed.sum())}

    def generate(self,weights,bias):
        self.phase_seconds={p:0.0 for p in PHASES}
        self.diagnostics={}
        return _generate(self,weights,bias)
