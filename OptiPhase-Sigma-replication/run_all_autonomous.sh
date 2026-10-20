#!/usr/bin/env bash
# Runs every stage of the OptiPhase-Sigma pipeline in dependency order.
# Each stage checkpoints its own outputs, so rerunning the script resumes where it stopped.
# The timed sweeps (task4) must not share the machine with other CPU-heavy work, so run this script alone.
# Every stage is checked by its own exit status (set -e), and each LaTeX build writes its own log under manuscript/build.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
PYTHON="$ROOT/.venv/bin/python"
cd "$ROOT"

"$PYTHON" src/task1_lit_harvester.py
"$PYTHON" src/task2_nlp_gap_miner.py
"$PYTHON" src/task3_benchmark_scaffolder.py
"$PYTHON" src/task4_sweep_engine.py --phase r1-r5
"$PYTHON" src/task4_sweep_engine.py --phase r2x
"$PYTHON" src/task4_sweep_engine.py --phase r6
"$PYTHON" src/verify_bitcount_digests.py
"$PYTHON" src/verify_sweep_variants.py
"$PYTHON" src/verify_z3_encoding.py
"$PYTHON" src/task5_z3_verifier_and_math.py
"$PYTHON" src/analyze_refinement.py
"$PYTHON" src/analyze_sat_witnesses.py
"$PYTHON" src/export_certificates.py
"$PYTHON" src/pass_checks.py
"$PYTHON" src/lowering_pilot.py
"$PYTHON" src/figure_instcount.py
"$PYTHON" src/task5_plot_generator.py
"$PYTHON" src/task6_manuscript_author.py
"$PYTHON" src/build_manuscripts.py
"$PYTHON" src/verify_manuscript.py
