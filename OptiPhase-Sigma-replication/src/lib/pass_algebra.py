"""Pass algebra: the M_pass transition tensor, Lie-bracket commutators, Pareto fronts, and exact 3D hypervolume.

All hypervolume arithmetic is done in rationals (fractions.Fraction), so the reported volumes are exact
for the stored objective values. Epsilon guards the M_pass denominator; its value is recorded with results.
"""

from fractions import Fraction

M_PASS_EPSILON = 1.0  # nanoseconds; keeps M_pass finite when both single-pass deltas vanish


def dominates(left, right):
    """True when `left` is at least as good as `right` everywhere and strictly better somewhere (maximisation)."""
    return all(a >= b for a, b in zip(left, right)) and any(a > b for a, b in zip(left, right))


def pareto_front(points):
    """Return the non-dominated subset of points, preserving input order and dropping exact duplicates."""
    unique = list(dict.fromkeys(points))
    return [p for p in unique if not any(dominates(q, p) for q in unique if q != p)]


def hypervolume_2d(points, reference):
    """Exact area dominated by the points above the reference corner (maximisation)."""
    relevant = [p for p in points if p[0] > reference[0] and p[1] > reference[1]]
    area, best_y = Fraction(0), reference[1]
    for x, y in sorted(relevant, key=lambda p: -p[0]):
        if y > best_y:
            area += (x - reference[0]) * (y - best_y)
            best_y = y
    return area


def hypervolume_3d(points, reference):
    """Exact 3D Lebesgue measure of the region dominated by `points` above `reference` (maximisation).

    Slices along the third objective: between consecutive z levels the cross-section is the 2D
    hypervolume of every point whose z reaches the slice. All arithmetic is rational.
    """
    ref = tuple(Fraction(v) for v in reference)
    pts = [tuple(Fraction(v) for v in p) for p in points]
    relevant = [p for p in pts if all(p[i] > ref[i] for i in range(3))]
    if not relevant:
        return Fraction(0)
    levels = sorted({p[2] for p in relevant} | {ref[2]})
    volume = Fraction(0)
    for lower, upper in zip(levels, levels[1:]):
        active = [(p[0], p[1]) for p in relevant if p[2] >= upper]
        volume += hypervolume_2d(active, (ref[0], ref[1])) * (upper - lower)
    return volume


def m_pass_entry(delta_pi_j_after_i, delta_pi_j, delta_pi_i):
    """One summand of [M]_{ij}(G): (dJ(pi_j | pi_i(G)) - dJ(pi_j | G)) / max(eps, |dJ_j| + |dJ_i|)."""
    denominator = max(M_PASS_EPSILON, abs(delta_pi_j) + abs(delta_pi_i))
    return (delta_pi_j_after_i - delta_pi_j) / denominator


def m_pass_matrix(kernel_observations, passes):
    """Average the per-kernel summands into the transition tensor.

    Each observation holds cost deltas measured against the same kernel's canonical cost in the
    same timing window:
        'single' - {pass: dJ(pass | G)},
        'pair'   - {(first, second): dJ((second o first) | G)}, the cost after `first` then `second`.
    Then dJ(second | first(G)) is approximated as pair - single[first]. Returns {(i, j): value} with
    the mean over kernels, as in the directive's 1/M sum.
    """
    kernel_count = len(kernel_observations)
    if kernel_count == 0:
        raise ValueError("no kernel has complete R2 and R3 coverage, so the transition tensor cannot be computed")
    matrix = {}
    for first in passes:
        for second in passes:
            total = 0.0
            for observation in kernel_observations:
                delta_first = observation["single"][first]
                delta_second = observation["single"][second]
                delta_second_after_first = observation["pair"][(first, second)] - delta_first
                total += m_pass_entry(delta_second_after_first, delta_second, delta_first)
            matrix[(first, second)] = total / kernel_count
    return matrix


def lie_bracket(j_first_then_second, j_second_then_first, j0):
    """[pi_i, pi_j]_J(G) = (J((pi_j o pi_i)(G)) - J((pi_i o pi_j)(G))) / J(G)."""
    return (j_first_then_second - j_second_then_first) / j0


def rpb_ratio(noop_events, total_events):
    return noop_events / total_events if total_events else 0.0


def waste_cycle(compile_ms, rpb):
    """Estimated compile time spent on zero-change pass events: compile wall time times the RPB ratio."""
    return compile_ms * rpb
