"""Build the per-kernel observations that the M_pass transition tensor needs, from R1-R5 telemetry rows."""

from lib.pipeline_plans import R3_PASSES

SWEEP_ID_TEMPLATE = "K{kernel_index:02d}-{regime}-{plan_index:03d}"


def sweep_id_for(kernel_index, regime, plan_index):
    return SWEEP_ID_TEMPLATE.format(kernel_index=kernel_index, regime=regime, plan_index=plan_index)


def is_needed(plan):
    """The tensor needs the single-pass sweeps of the R3 passes and every ordered pair of R3 passes, and no others."""
    if plan.regime_id == "R2":
        return plan.label in R3_PASSES
    return plan.regime_id == "R3"


def kernel_observation(kernel_index, baseline_ns, plans, rows_by_id):
    """Return the observation for one kernel, or None when a sweep that the tensor needs is missing."""
    single, pair = {}, {}
    for plan_index, plan in enumerate(plans):
        if not is_needed(plan):
            continue
        row = rows_by_id.get(sweep_id_for(kernel_index, plan.regime_id, plan_index))
        if row is None:
            return None
        delta = float(row["delta_cost_J"])
        if plan.regime_id == "R2":
            single[plan.label] = delta
        else:
            first, second = plan.label.split(">")
            pair[(first, second)] = delta
    required_pairs = {(first, second) for first in R3_PASSES for second in R3_PASSES}
    if set(single) != set(R3_PASSES) or set(pair) != required_pairs:
        return None
    return {"J0": baseline_ns, "single": single, "pair": pair}


def build_observations(kernel_ids, baselines, plans, rows):
    """Return (observations, excluded kernel ids) for every kernel with complete R2 and R3 coverage."""
    rows_by_id = {row["sweep_id"]: row for row in rows}
    observations, excluded = [], []
    for kernel_index, kernel_id in enumerate(kernel_ids):
        observation = kernel_observation(
            kernel_index, baselines[kernel_id]["median_ns"], plans, rows_by_id
        )
        if observation is None:
            excluded.append(kernel_id)
        else:
            observations.append({**observation, "kernel": kernel_id})
    return observations, excluded
