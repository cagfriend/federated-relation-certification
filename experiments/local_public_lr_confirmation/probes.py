"""Use the same read-only probes and fixed selection stream as E28."""
from experiments.local_public_lr.probes import manifest, selection, prediction_summary, head_distance, PROBE_STREAM

__all__ = ('manifest', 'selection', 'prediction_summary', 'head_distance', 'PROBE_STREAM')
