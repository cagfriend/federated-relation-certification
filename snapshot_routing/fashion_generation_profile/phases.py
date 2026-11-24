"""Phase timers for the current E55 generators, using their original statements."""

import ast
from contextlib import contextmanager
import inspect
from textwrap import dedent
from time import perf_counter

from experiments.cost_diagnostics.profiler import find, measured
from experiments.public_scaling.certification import RelationGenerator
from experiments.public_scaling.endpoint_bias import EndpointBiasGenerator

PHASES = (
    'bootstrap', 'advance', 'candidates', 'bitsets', 'edge_certification',
    'endpoint_selection', 'feature_gather', 'scoring', 'label_selection',
    'cache_update', 'output',
)


def timed_method(name, wrap):
    original = getattr(RelationGenerator, name)
    tree = ast.parse(dedent(inspect.getsource(original)))
    fn = tree.body[0]
    fn.body = wrap(fn.body)
    namespace = dict(original.__globals__)
    exec(compile(ast.fix_missing_locations(tree), original.__code__.co_filename, 'exec'), namespace)
    return namespace[name]


def generation_sections(body):
    full = next(node for node in body if isinstance(node, ast.If)
                and ast.unparse(node.test) == "self.mode == 'full'")
    score, labels, output = full.body
    if not (ast.unparse(score).startswith('scores = ') and ast.unparse(labels).startswith('labels = ')
            and isinstance(output, ast.Return)):
        raise RuntimeError('Full generator phase boundaries changed')
    full.body = [measured('scoring', [score]), measured('label_selection', [labels]),
                 measured('output', [output])]
    edge = find(body, 'different =')
    selection = find(body, 'needed =')
    refresh = find(body, 'self._refresh(')
    return (body[:edge] + [measured('edge_certification', body[edge:selection]),
                          measured('endpoint_selection', body[selection:refresh])]
            + body[refresh:refresh+1] + [measured('output', body[refresh+1:])])


def bitset_sections(body):
    start = find(body, 'bits =')
    return body[:start] + [measured('bitsets', body[start:])]


def refresh_sections(body):
    start = find(body, 'scores =')
    cache = find(body, 'self.winners[ids] =')
    score = body[start]
    # Lift only the indexing expression so copying rows and scoring have separate clocks.
    if ast.unparse(score) != 'scores = self.features[ids] @ weights.T + bias':
        raise RuntimeError('Refresh scoring expression changed')
    gather = ast.Assign(targets=[ast.Name(id='selected_features', ctx=ast.Store())],
                        value=score.value.left.left)
    product = score.value.left
    product.left = ast.Name(id='selected_features', ctx=ast.Load())
    products = ast.Assign(targets=[ast.Name(id='products', ctx=ast.Store())], value=product)
    score.value.left = ast.Name(id='products', ctx=ast.Load())
    release_features, release_products = ast.parse('del selected_features\ndel products').body
    return (body[:start] + [measured('feature_gather', [gather]),
                           measured('scoring', [products, release_features, score, release_products]),
                           measured('label_selection', body[start+1:cache]),
                           measured('cache_update', body[cache:])])


class PhaseTimers:
    def __init__(self, *args, profile_rows, client, **kwargs):
        self.profile_rows, self.client = profile_rows, client
        self.phases = dict.fromkeys(PHASES, 0.)
        start = perf_counter()
        super().__init__(*args, **kwargs)
        elapsed = perf_counter()-start
        self.phases['bootstrap'] = elapsed
        self.record(elapsed, dict(forward_endpoints=self.samples,
                                  certified_edges_before_refresh=0,
                                  unresolved_edges_before_refresh=len(self.edges),
                                  candidate_entries=None))

    @contextmanager
    def _measure(self, phase):
        start = perf_counter()
        try:
            yield
        finally:
            self.phases[phase] += perf_counter()-start

    def record(self, elapsed, stats):
        self.profile_rows.append(dict(round=self.round+1, client=self.client, width=self.dimension,
                                      seconds=elapsed, **stats, **self.phases))

    def generate(self, weights, bias):
        self.phases = dict.fromkeys(PHASES, 0.)
        start = perf_counter()
        relation, stats = self.timed_generate(weights, bias)
        self.record(perf_counter()-start, stats)
        return relation, stats

    timed_generate = timed_method('generate', generation_sections)


class ProfiledFull(PhaseTimers, RelationGenerator):
    pass


class ProfiledRelation(PhaseTimers, EndpointBiasGenerator):
    candidate_sets = timed_method('candidate_sets', bitset_sections)
    _refresh = timed_method('_refresh', refresh_sections)

    def _advance(self, weights, bias):
        with self._measure('advance'):
            return super()._advance(weights, bias)

    def candidate_matrix(self):
        with self._measure('candidates'):
            return super().candidate_matrix()


def factory(profile_rows, clients):
    next_client = iter(range(clients))

    def construct(features, weights, bias, edges, mode):
        args = (features, weights, bias, edges)
        kwargs = dict(profile_rows=profile_rows, client=next(next_client))
        if mode == 'full':
            return ProfiledFull(*args, mode, **kwargs)
        if mode == 'relation':
            return ProfiledRelation(*args, **kwargs)
        raise ValueError(f'Unsupported generation path: {mode}')

    return construct
