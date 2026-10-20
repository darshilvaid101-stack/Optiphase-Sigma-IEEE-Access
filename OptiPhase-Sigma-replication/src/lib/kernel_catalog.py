"""The complete kernel catalog: PolyBench/C, MiBench, and TSVC/CoreMark, in suite order."""

from lib.coremark_specs import coremark_kernels
from lib.kernel_registry import mibench_kernels, polybench_kernels
from lib.tsvc_specs import tsvc_kernels


def all_kernels():
    return polybench_kernels() + mibench_kernels() + tsvc_kernels() + coremark_kernels()
