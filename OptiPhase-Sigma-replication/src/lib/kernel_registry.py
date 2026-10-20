"""Registry of benchmark kernels: 30 PolyBench/C kernels and 20 MiBench invocations.

MiBench source lists come from each program's Makefile; arguments come from the
official runme_small.sh. TSVC and CoreMark kernels are added in a separate module.
"""

from pathlib import Path

from lib.kernel_spec import KernelSpec

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
POLYBENCH_ROOT = "data/benchmarks/polybench_c_4.2.1"
MIBENCH_ROOT = "data/benchmarks/mibench_v1"
POLYBENCH_DEFINES = ("SMALL_DATASET", "POLYBENCH_DUMP_ARRAYS")
POLYBENCH_UTILITY = "utilities/polybench.c"
LEGACY_C_FLAGS = ("-std=gnu89", "-w", "-Wno-incompatible-pointer-types")
COMPATIBILITY_INCLUDE = "src/compat/include"
MATH_LIBRARY = ("-lm",)
BLOWFISH_KEY = "1234567890abcdeffedcba0987654321"
RIJNDAEL_KEY = "1234567890abcdeffedcba09876543211234567890abcdeffedcba0987654321"
BLOWFISH_SOURCES = ("bf.c", "bf_skey.c", "bf_ecb.c", "bf_enc.c", "bf_cbc.c", "bf_cfb64.c", "bf_ofb64.c")
GSM_LIBRARY_SOURCES = (
    "add.c", "code.c", "debug.c", "decode.c", "long_term.c", "lpc.c", "preprocess.c", "rpe.c",
    "gsm_destroy.c", "gsm_decode.c", "gsm_encode.c", "gsm_explode.c", "gsm_implode.c",
    "gsm_create.c", "gsm_print.c", "gsm_option.c", "short_term.c", "table.c",
)
GSM_TOAST_SOURCES = ("toast.c", "toast_lin.c", "toast_ulaw.c", "toast_alaw.c", "toast_audio.c")
# Defines from the GSM Makefile's CCFLAGS and SASR; without them gsm_mult and Postprocessing
# are not defined and the library does not link.
GSM_DEFINES = ("SASR", "STUPID_COMPILER", "NeedFunctionPrototypes=1")
# sha.c and blowfish read uninitialized automatic variables (see the rows below). Zero-
# initialising them makes native and bitcode builds agree; this changes no intended output.
ZERO_INITIALIZED_AUTOMATICS = ("-ftrivial-auto-var-init=zero",)
BITCOUNT_SOURCES = (
    "bitcnt_1.c", "bitcnt_2.c", "bitcnt_3.c", "bitcnt_4.c", "bitcnts.c",
    "bitfiles.c", "bitstrng.c", "bstr_i.c",
)
# Wall-clock fields printed by the benchmark itself; masked before hashing so that
# the digest covers only deterministic output. Everything else is compared exactly.
BITCOUNT_TIMING = r"Time:\s*[0-9.]+\s*sec"
# The benchmark also names its fastest and slowest algorithm, which is chosen by the same timings.
BITCOUNT_RANKING = r"(?m)^(?:Best|Worst)\s+> [^\n]*"
PATRICIA_TIMING = r"(?m)^[0-9]+\.[0-9]+ "


def repo_relative(path):
    return path.relative_to(REPO_ROOT).as_posix()


def polybench_spec(source):
    """Build the spec for one PolyBench kernel: its source plus the shared timing-free harness."""
    kernel_dir = repo_relative(source.parent)
    return KernelSpec(
        kernel_id=f"polybench/{source.stem}",
        suite="polybench",
        sources=(repo_relative(source), f"{POLYBENCH_ROOT}/{POLYBENCH_UTILITY}"),
        include_dirs=(f"{POLYBENCH_ROOT}/utilities", kernel_dir),
        defines=POLYBENCH_DEFINES,
        extra_flags=("-w",),
        link_libraries=MATH_LIBRARY,
        run_directory="",
        program_name=source.stem,
        arguments=(),
        stdin_file="",
        setup_arguments=(),
        staged_files=(),
        volatile_patterns=(),
    )


def polybench_kernels():
    root = REPO_ROOT / POLYBENCH_ROOT
    sources = sorted(
        path for path in root.rglob("*.c") if "utilities" not in path.relative_to(root).parts
    )
    return [polybench_spec(source) for source in sources]


def mibench_entry(entry):
    """Turn one MiBench table row into a KernelSpec; every row is one kernel invocation."""
    return KernelSpec(
        kernel_id=f"mibench/{entry['id']}",
        suite="mibench",
        sources=tuple(f"{MIBENCH_ROOT}/{source}" for source in entry["sources"]),
        include_dirs=(
            *(f"{MIBENCH_ROOT}/{directory}" for directory in entry["includes"]),
            COMPATIBILITY_INCLUDE,
        ),
        defines=tuple(entry.get("defines", ())),
        extra_flags=(*LEGACY_C_FLAGS, *entry.get("extra_flags", ())),
        link_libraries=entry.get("libraries", ()),
        run_directory=f"{MIBENCH_ROOT}/{entry['run']}",
        program_name=entry["program"],
        arguments=tuple(entry.get("arguments", ())),
        stdin_file=entry.get("stdin", ""),
        setup_arguments=tuple(tuple(setup) for setup in entry.get("setup", ())),
        staged_files=tuple(
            (f"{MIBENCH_ROOT}/{source}", destination) for source, destination in entry.get("staged", ())
        ),
        volatile_patterns=tuple(entry.get("volatile", ())),
    )


def gsm_sources():
    library = tuple(f"telecomm/gsm/src/{name}" for name in GSM_LIBRARY_SOURCES)
    toast = tuple(f"telecomm/gsm/src/{name}" for name in GSM_TOAST_SOURCES)
    return library + toast


MIBENCH_TABLE = (
    {"id": "bitcount", "program": "bitcnts", "run": "automotive/bitcount",
     "sources": tuple(f"automotive/bitcount/{name}" for name in BITCOUNT_SOURCES),
     "includes": ("automotive/bitcount",), "arguments": ("75000",),
     "volatile": (BITCOUNT_TIMING, BITCOUNT_RANKING)},
    {"id": "basicmath", "program": "basicmath_small", "run": "automotive/basicmath",
     "sources": ("automotive/basicmath/basicmath_small.c", "automotive/basicmath/rad2deg.c",
                 "automotive/basicmath/cubic.c", "automotive/basicmath/isqrt.c"),
     "includes": ("automotive/basicmath",), "libraries": MATH_LIBRARY},
    {"id": "qsort", "program": "qsort_small", "run": "automotive/qsort",
     "sources": ("automotive/qsort/qsort_small.c",), "includes": ("automotive/qsort",),
     "libraries": MATH_LIBRARY, "arguments": ("input_small.dat",)},
    {"id": "susan-smoothing", "program": "susan", "run": "automotive/susan",
     "sources": ("automotive/susan/susan.c",), "includes": ("automotive/susan",),
     "libraries": MATH_LIBRARY,
     "arguments": ("input_small.pgm", "output_small.smoothing.pgm", "-s")},
    {"id": "susan-edges", "program": "susan", "run": "automotive/susan",
     "sources": ("automotive/susan/susan.c",), "includes": ("automotive/susan",),
     "libraries": MATH_LIBRARY,
     "arguments": ("input_small.pgm", "output_small.edges.pgm", "-e")},
    {"id": "susan-corners", "program": "susan", "run": "automotive/susan",
     "sources": ("automotive/susan/susan.c",), "includes": ("automotive/susan",),
     "libraries": MATH_LIBRARY,
     "arguments": ("input_small.pgm", "output_small.corners.pgm", "-c")},
    {"id": "dijkstra", "program": "dijkstra_small", "run": "network/dijkstra",
     "sources": ("network/dijkstra/dijkstra_small.c",), "includes": ("network/dijkstra",),
     "arguments": ("input.dat",)},
    {"id": "patricia", "program": "patricia", "run": "network/patricia",
     "sources": ("network/patricia/patricia.c", "network/patricia/patricia_test.c"),
     "includes": ("network/patricia",), "arguments": ("small.udp",),
     "volatile": (PATRICIA_TIMING,)},
    {"id": "blowfish-encode", "program": "bf", "run": "security/blowfish",
     "sources": tuple(f"security/blowfish/{name}" for name in BLOWFISH_SOURCES),
     "includes": ("security/blowfish",),
     "arguments": ("e", "input_small.asc", "output_small.enc", BLOWFISH_KEY),
     "extra_flags": ZERO_INITIALIZED_AUTOMATICS},
    {"id": "blowfish-decode", "program": "bf", "run": "security/blowfish",
     "sources": tuple(f"security/blowfish/{name}" for name in BLOWFISH_SOURCES),
     "includes": ("security/blowfish",),
     "arguments": ("d", "output_small.enc", "output_small.asc", BLOWFISH_KEY),
     "extra_flags": ZERO_INITIALIZED_AUTOMATICS,
     "setup": (("e", "input_small.asc", "output_small.enc", BLOWFISH_KEY),)},
    {"id": "rijndael-encode", "program": "rijndael", "run": "security/rijndael",
     "sources": ("security/rijndael/aes.c", "security/rijndael/aesxam.c"),
     "includes": ("security/rijndael",),
     "arguments": ("input_small.asc", "output_small.enc", "e", RIJNDAEL_KEY)},
    {"id": "rijndael-decode", "program": "rijndael", "run": "security/rijndael",
     "sources": ("security/rijndael/aes.c", "security/rijndael/aesxam.c"),
     "includes": ("security/rijndael",),
     "arguments": ("output_small.enc", "output_small.dec", "d", RIJNDAEL_KEY),
     "setup": (("input_small.asc", "output_small.enc", "e", RIJNDAEL_KEY),)},
    {"id": "sha", "program": "sha", "run": "security/sha",
     "sources": ("security/sha/sha_driver.c", "security/sha/sha.c"),
     "includes": ("security/sha",), "arguments": ("input_small.asc",),
     # sha.c reads uninitialized automatic variables: plain -O0 builds give different digests
     # on identical input. Zero-initialization restores the intended deterministic SHA-1.
     "extra_flags": ("-ftrivial-auto-var-init=zero",)},
    {"id": "crc32", "program": "crc", "run": "telecomm/CRC32",
     "sources": ("telecomm/CRC32/crc_32.c",), "includes": ("telecomm/CRC32",),
     "arguments": ("large.pcm",),
     "staged": (("telecomm/adpcm/data/large.pcm", "large.pcm"),)},
    {"id": "fft-forward", "program": "fft", "run": "telecomm/FFT",
     "sources": ("telecomm/FFT/main.c", "telecomm/FFT/fftmisc.c", "telecomm/FFT/fourierf.c"),
     "includes": ("telecomm/FFT",), "libraries": MATH_LIBRARY, "arguments": ("4", "4096")},
    {"id": "fft-inverse", "program": "fft", "run": "telecomm/FFT",
     "sources": ("telecomm/FFT/main.c", "telecomm/FFT/fftmisc.c", "telecomm/FFT/fourierf.c"),
     "includes": ("telecomm/FFT",), "libraries": MATH_LIBRARY,
     "arguments": ("4", "8192", "-i")},
    {"id": "adpcm-rawcaudio", "program": "rawcaudio", "run": "telecomm/adpcm",
     "sources": ("telecomm/adpcm/src/rawcaudio.c", "telecomm/adpcm/src/adpcm.c"),
     "includes": ("telecomm/adpcm/src",), "stdin": "data/small.pcm"},
    {"id": "adpcm-rawdaudio", "program": "rawdaudio", "run": "telecomm/adpcm",
     "sources": ("telecomm/adpcm/src/rawdaudio.c", "telecomm/adpcm/src/adpcm.c"),
     "includes": ("telecomm/adpcm/src",), "stdin": "data/small.adpcm"},
    {"id": "gsm-toast", "program": "toast", "run": "telecomm/gsm",
     "sources": gsm_sources(), "includes": ("telecomm/gsm/inc",), "libraries": MATH_LIBRARY,
     "defines": GSM_DEFINES, "arguments": ("-fps", "-c", "data/small.au")},
    {"id": "gsm-untoast", "program": "untoast", "run": "telecomm/gsm",
     "sources": gsm_sources(), "includes": ("telecomm/gsm/inc",), "libraries": MATH_LIBRARY,
     "defines": GSM_DEFINES, "arguments": ("-fps", "-c", "data/small.au.run.gsm")},
)


def mibench_kernels():
    return [mibench_entry(entry) for entry in MIBENCH_TABLE]


