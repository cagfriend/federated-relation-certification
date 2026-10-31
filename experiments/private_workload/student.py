"""Public student update is unchanged from the public-budget experiment.

Re-export the frozen implementation so the fixed-8-step public budget
has a single source; this experiment varies only the private workload.
"""
from experiments.public_budget.student import Coverage, schedule_digest, selected_edges, update

__all__ = ('Coverage', 'schedule_digest', 'selected_edges', 'update')
