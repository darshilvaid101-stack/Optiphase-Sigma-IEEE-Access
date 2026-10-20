"""Cluster-level mathematical remedies, one per gap cluster."""

REMEDIATION_BY_CLUSTER = {
    "G1": (
        "Model each NewPM analysis as a cached value with an invalidation set: for pass pi, "
        "define I(pi) as a subset of the analysis set A, and score DeltaJ(pi | G) only after "
        "applying I(pi), so that analysis-dependent rewrites are not scored against stale state."
    ),
    "G2": (
        "Replace the raw instruction delta with a loop-weighted cost J(G) = sum over blocks b of "
        "w(b) * c(b), where w(b) = 10^depth(b), c(b) reflects vector width W, and a spill penalty "
        "lambda * max(0, p(b) - K) charges register-pressure growth."
    ),
    "G3": (
        "Encode source and target blocks as two-rail bit-vectors (value BV64, poison BV1) over "
        "Array(BV64, BV8) memory, and check that Phi_viol = not refines(B_src, B_tgt) is UNSAT "
        "under a bounded solver timeout."
    ),
    "G4": (
        "Define the redundant pass bloat rho_RPB = |{i : IR_i unchanged}| / n over a pass schedule "
        "of length n, and report the compile waste W_cycle = sum over i of t_i * 1[IR_i unchanged] "
        "so that zero-delta invocations are measured instead of assumed to be cheap."
    ),
    "G5": (
        "Score each schedule as a vector (speedup, binary size reduction, compile throughput) and "
        "report the exact 3D Lebesgue hypervolume HV(F*, r) against a fixed reference point r, "
        "rather than a weighted sum with ad-hoc weights."
    ),
    "G6": (
        "Evaluate on a cross-suite panel (PolyBench/C, MiBench, TSVC/CoreMark) and report the same "
        "exact-operator metric per suite, so generalization across workload families is measured "
        "rather than assumed."
    ),
}
