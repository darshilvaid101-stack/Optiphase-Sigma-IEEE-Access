"""Sweep plans for regimes R1-R5. R6 is planned only after the M_pass matrix exists, because it uses it."""

from dataclasses import dataclass
from itertools import product

from lib.kernel_registry import REPO_ROOT
from lib.llvm_tools import run_tool
from lib.pass_catalog import stage_by_name, valid_stages
from lib.pipeline_prefix import pipeline_prefix

REFERENCE_BITCODE = REPO_ROOT / "data" / "benchmarks" / "bitcode_O0_canon" / "polybench__gemm.bc"
R1_STANDARD_LEVELS = ("O0", "O1", "O2", "O3")
# LLVM 23 rejects default<Os> and default<Oz>. Their documented equivalents are O2 with the
# optsize or minsize function attribute forced on every defined function.
R1_ATTRIBUTE_LEVELS = (("Os", "optsize"), ("Oz", "minsize"))
R3_PASSES = (
    "instcombine", "simplifycfg", "early-cse", "gvn", "licm", "loop-rotate", "indvars",
    "loop-unroll", "loop-vectorize", "slp-vectorizer", "sccp", "dce", "dse", "reassociate",
    "jump-threading",
)
R4_PREFIX_STAGES = 65
R5_PIVOT = "loop-vectorize"
R5_BEFORE = (
    (), ("simplifycfg",), ("jump-threading",), ("simplifycfg", "jump-threading"),
    ("jump-threading", "simplifycfg"), ("instcombine",), ("simplifycfg", "instcombine"),
    ("instcombine", "jump-threading"),
)
R5_AFTER = ((), ("simplifycfg",), ("jump-threading",), ("instcombine",), ("dce",))


@dataclass(frozen=True)
class SweepPlan:
    """opt_pipeline is what opt receives; pass_sequence is what telemetry records for the same run."""

    regime_id: str
    label: str
    pass_sequence: str
    opt_pipeline: str
    force_attribute: str = ""
    opt_arguments: tuple = ()


def print_o3_pipeline():
    """Return LLVM's own nested text for default<O3>, which R4 truncates stage by stage."""
    completed = run_tool(
        "opt",
        ["-passes=default<O3>", "-print-pipeline-passes", str(REFERENCE_BITCODE), "-S", "-o", "/dev/null"],
    )
    return completed.stdout.strip()


def r1_plans():
    plans = [SweepPlan("R1", level, f"default<{level}>", f"default<{level}>") for level in R1_STANDARD_LEVELS]
    for level, attribute in R1_ATTRIBUTE_LEVELS:
        pipeline = "forceattrs,default<O2>"
        plans.append(SweepPlan("R1", level, f"{pipeline}[force-attribute={attribute}]", pipeline, attribute))
    return plans


# internalize without a preserve list also internalizes main, and the executable then cannot link.
# The program's public API is main, so that is the only symbol it is told to keep.
PASS_ARGUMENTS = {"internalize": ("-internalize-public-api-list=main",)}


def r2_plans():
    plans = []
    for name, stage in valid_stages():
        arguments = PASS_ARGUMENTS.get(name, ())
        recorded = f"{stage}[{' '.join(arguments)}]" if arguments else stage
        plans.append(SweepPlan("R2", name, recorded, stage, opt_arguments=arguments))
    return plans


def r3_plans():
    stages = stage_by_name()
    return [
        SweepPlan("R3", f"{first}>{second}", f"{stages[first]},{stages[second]}", f"{stages[first]},{stages[second]}")
        for first, second in product(R3_PASSES, repeat=2)
    ]


def r4_plans(o3_pipeline):
    plans = []
    for stages in range(1, R4_PREFIX_STAGES + 1):
        prefix = pipeline_prefix(o3_pipeline, stages)
        plans.append(SweepPlan("R4", f"O3-prefix-{stages:02d}", prefix, prefix))
    return plans


def r5_plans():
    stages = stage_by_name()
    plans = []
    for before, after in product(R5_BEFORE, R5_AFTER):
        names = [*before, R5_PIVOT, *after]
        label = f"before={'+'.join(before) or 'none'}|after={'+'.join(after) or 'none'}"
        pipeline = ",".join(stages[name] for name in names)
        plans.append(SweepPlan("R5", label, pipeline, pipeline))
    return plans


def static_plans():
    """Plans for R1 through R5: everything that does not depend on measured data."""
    o3_pipeline = print_o3_pipeline()
    return r1_plans() + r2_plans() + r3_plans() + r4_plans(o3_pipeline) + r5_plans()
