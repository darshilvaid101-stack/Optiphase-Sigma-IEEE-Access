"""Regime R6: 60 M_pass-guided pass sequences per kernel, chosen deterministically from the transition matrix."""

from itertools import permutations

R6_SEQUENCES_PER_KERNEL = 60
R6_SEQUENCE_LENGTH = 3


def score_sequence(sequence, matrix):
    """Sum of M_pass transition values over consecutive pairs; higher means a better predicted chain."""
    return sum(matrix[(first, second)] for first, second in zip(sequence, sequence[1:]))


def plan_regime6(matrix, passes, count=R6_SEQUENCES_PER_KERNEL, length=R6_SEQUENCE_LENGTH):
    """Return the `count` highest-scoring ordered sequences of distinct passes.

    Ties are broken lexicographically on the sequence, so the plan is identical on every run.
    """
    candidates = list(permutations(passes, length))
    ranked = sorted(candidates, key=lambda seq: (-score_sequence(seq, matrix), seq))
    return ranked[:count]
