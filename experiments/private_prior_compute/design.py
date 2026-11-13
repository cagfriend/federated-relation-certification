from experiments.private_prior.design import CASES, spec

METHODS = ('B', 'E', 'D')


def schedule(memory=False):
    selected = [c for c in CASES if not memory or c['seed'] == 1002]
    return [dict(case, method=method, memory=memory)
            for i,case in enumerate(selected)
            for method in METHODS[i % 3:] + METHODS[:i % 3]]


def filename(case):
    return case['case_id'] + '_' + case['method'] + '.json'
