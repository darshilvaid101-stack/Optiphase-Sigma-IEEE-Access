"""The instruction-count transition matrix that selects the regime R6 chains.

Regime R6 chains use distinct passes only, so the diagonal is zero. Each off-diagonal entry is the instruction-count
interaction of an ordered pair, averaged over the kernels. The counts are exact, so the matrix carries no timing noise.
"""

from statistics import fmean

from lib.manuscript_instcount import instcount_interactions


def instcount_matrix(master_rows, passes):
    values = instcount_interactions(master_rows)
    return {
        (first, second): 0.0 if first == second else fmean(values[(first, second)])
        for first in passes
        for second in passes
    }
