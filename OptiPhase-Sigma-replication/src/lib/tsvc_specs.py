"""TSVC kernel specs: one loop per kernel, built through the shared harness and the category's dummy module."""

from lib.kernel_registry import MATH_LIBRARY, REPO_ROOT
from lib.kernel_spec import KernelSpec

TSVC_ROOT = "data/benchmarks/tsvc_coremark/tsvc"
HARNESS_SOURCE = "src/harnesses/tsvc_kernel_harness.c"
HARNESS_REPETITIONS = 10
CATEGORY_DIRECTORIES = {
    "LINEAR_DEPENDENCE": "LinearDependence-flt",
    "CONTROL_FLOW": "ControlFlow-flt",
    "REDUCTIONS": "Reductions-flt",
    "RECURRENCES": "Recurrences-flt",
}
# (kernel function in tsc.inc, TSVC category macro that tsc.inc needs), per the agent's selection
TSVC_KERNELS = (
    ("s000", "LINEAR_DEPENDENCE"),
    ("s111", "LINEAR_DEPENDENCE"),
    ("s271", "CONTROL_FLOW"),
    ("s311", "REDUCTIONS"),
    ("s321", "RECURRENCES"),
)


def tsvc_spec(kernel, category):
    category_directory = f"{TSVC_ROOT}/{CATEGORY_DIRECTORIES[category]}"
    return KernelSpec(
        kernel_id=f"tsvc/{kernel}",
        suite="tsvc_coremark",
        sources=(HARNESS_SOURCE, f"{category_directory}/dummy.c"),
        include_dirs=(TSVC_ROOT,),
        defines=(
            f"KERNEL_FUNCTION={kernel}",
            f"TESTS={category}",
            f"HARNESS_NTIMES={HARNESS_REPETITIONS}",
        ),
        extra_flags=("-w",),
        link_libraries=MATH_LIBRARY,
        run_directory="",
        program_name=kernel,
        arguments=(),
        stdin_file="",
        setup_arguments=(),
        staged_files=(),
        volatile_patterns=(),
    )


def tsvc_kernels():
    for kernel, category in TSVC_KERNELS:
        assert (REPO_ROOT / TSVC_ROOT / CATEGORY_DIRECTORIES[category] / "dummy.c").is_file()
    return [tsvc_spec(kernel, category) for kernel, category in TSVC_KERNELS]
