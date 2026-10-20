"""CoreMark kernel specs: five kernels built through one harness plus the unmodified CoreMark sources."""

from lib.kernel_registry import MATH_LIBRARY
from lib.kernel_spec import KernelSpec

COREMARK_ROOT = "data/benchmarks/tsvc_coremark/coremark"
HARNESS_SOURCE = "src/harnesses/coremark_kernel_harness.c"
PORT_SOURCE = f"{COREMARK_ROOT}/posix/core_portme.c"
KERNEL_SOURCES = (
    f"{COREMARK_ROOT}/core_list_join.c",
    f"{COREMARK_ROOT}/core_matrix.c",
    f"{COREMARK_ROOT}/core_state.c",
    f"{COREMARK_ROOT}/core_util.c",
)
# (kernel name, RUN_* macro that selects it in the harness)
COREMARK_KERNELS = (
    ("core_bench_list", "RUN_LIST"),
    ("core_bench_matrix", "RUN_MATRIX"),
    ("core_bench_state", "RUN_STATE"),
    ("crcu8", "RUN_CRCU8"),
    ("matrix_mul_matrix_bitextract", "RUN_MATMUL"),
)


def coremark_spec(kernel, selector):
    return KernelSpec(
        kernel_id=f"coremark/{kernel}",
        suite="tsvc_coremark",
        sources=(HARNESS_SOURCE, PORT_SOURCE, *KERNEL_SOURCES),
        include_dirs=(COREMARK_ROOT, f"{COREMARK_ROOT}/posix"),
        defines=(f"{selector}=1",),
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


def coremark_kernels():
    return [coremark_spec(kernel, selector) for kernel, selector in COREMARK_KERNELS]
