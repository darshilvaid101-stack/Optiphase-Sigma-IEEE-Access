"""Normalised three-objective vectors for each sweep, ready for exact Pareto and hypervolume analysis.

Each objective is x0 / (x0 + x), where x0 is the canonical reference value and x is the sweep's value.
Unchanged from canonical gives 0.5 for every objective, so the reference point is (0.5, 0.5, 0.5):
a schedule enters the hypervolume only if it is better than canonical on all three axes.
  speedup:          s = J0 / (J0 + J)   (J is the measured cost; lower is faster)
  size reduction:   b = T0 / (T0 + T)   (T is binary text bytes)
  compile throughput: c = C0 / (C0 + C) (C is compile wall time; C0 is the R1 -O0 reference)
"""

REFERENCE_POINT = (0.5, 0.5, 0.5)


def normalised_ratio(reference, value):
    total = reference + value
    if total <= 0:
        raise ValueError("objective reference and value must not both be non-positive")
    return reference / total


def objective_vector(cost_before, cost_after, text_reference, text_bytes, compile_reference_ms, compile_ms):
    return (
        normalised_ratio(cost_before, cost_after),
        normalised_ratio(text_reference, text_bytes),
        normalised_ratio(compile_reference_ms, compile_ms),
    )
