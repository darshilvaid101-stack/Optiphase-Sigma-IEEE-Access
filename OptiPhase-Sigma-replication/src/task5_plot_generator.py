"""Task 5 figures: three vector PDFs rendered from the telemetry tables.

  Figure 1, the instruction-count interaction, is drawn by src/figure_instcount.py.
  fig3_shannon_entropy_rpb_trajectory.pdf   mean IR opcode entropy and RPB ratio along the R4 -O3 prefix
  fig4_pareto_3d_hypervolume_surface.pdf    exact hypervolume surface over reference-point shifts
  fig5_z3_solver_scaling_profile.pdf        Z3 check time against the number of compared values
"""

import csv
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.colors import SymLogNorm  # noqa: E402
import numpy as np  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib.fixpoint_retry import canonical_spelling  # noqa: E402
from lib.kernel_registry import REPO_ROOT  # noqa: E402
from lib.objectives import REFERENCE_POINT  # noqa: E402
from lib.pass_algebra import hypervolume_3d  # noqa: E402
from lib.pipeline_plans import R3_PASSES  # noqa: E402
from lib.pipeline_prefix import count_leaves, split_top_level  # noqa: E402

TELEMETRY = REPO_ROOT / "data" / "telemetry"
FIGURES = REPO_ROOT / "figures"
MASTER_CSV = TELEMETRY / "master_sweeps_28800.csv"
MATRIX_CSV = TELEMETRY / "m_pass_transition_matrix.csv"
PARETO_CSV = TELEMETRY / "pareto_3d_frontiers.csv"
PROOFS_CSV = TELEMETRY / "z3_verification_proofs.csv"
SCEV_EDGE_COUNT = 25
MPASS_LINEAR_THRESHOLD = 0.1  # magnitudes below this are drawn on a linear colour scale
SURFACE_GRID = 12
SURFACE_SPAN = (0.0, 0.45)
FIGURE_FORMAT = "pdf"
PLOT_DPI = 150


def read_csv(path):
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def save(figure, name):
    FIGURES.mkdir(parents=True, exist_ok=True)
    figure.savefig(FIGURES / name, format=FIGURE_FORMAT, bbox_inches="tight")
    plt.close(figure)


def _stage_lookup():
    from lib.pass_catalog import stage_by_name

    return stage_by_name()


def figure_entropy_rpb():
    rows = [row for row in read_csv(MASTER_CSV) if row["regime_id"] == "R4"]
    by_stage = defaultdict(lambda: {"entropy": [], "rpb": []})
    for row in rows:
        stage = count_leaves(split_top_level(row["pass_sequence_str"]))
        by_stage[stage]["entropy"].append(float(row["shannon_H_after"]))
        by_stage[stage]["rpb"].append(float(row["rpb_ratio"]))
    stages = sorted(by_stage)
    entropy = [np.mean(by_stage[stage]["entropy"]) for stage in stages]
    rpb = [np.mean(by_stage[stage]["rpb"]) for stage in stages]
    figure, (top, bottom) = plt.subplots(2, 1, figsize=(8, 6), sharex=True)
    top.plot(stages, entropy, color="#2c7fb8")
    top.set_ylabel("mean opcode entropy (bits)")
    bottom.plot(stages, rpb, color="#d95f0e")
    bottom.set_ylabel("mean RPB ratio")
    bottom.set_xlabel("-O3 prefix length (pass stages)")
    save(figure, "fig3_shannon_entropy_rpb_trajectory.pdf")


def figure_hypervolume_surface():
    rows = read_csv(PARETO_CSV)
    by_kernel = defaultdict(list)
    for row in rows:
        by_kernel[row["kernel_id"]].append(
            (float(row["speedup_objective"]), float(row["size_objective"]), float(row["compile_objective"]))
        )
    grid = np.linspace(SURFACE_SPAN[0], SURFACE_SPAN[1], SURFACE_GRID)
    surface = np.zeros((SURFACE_GRID, SURFACE_GRID))
    for i, shift_speed in enumerate(grid):
        for j, shift_size in enumerate(grid):
            reference = (REFERENCE_POINT[0] - shift_speed, REFERENCE_POINT[1] - shift_size, REFERENCE_POINT[2])
            surface[j, i] = np.mean([float(hypervolume_3d(points, reference)) for points in by_kernel.values()])
    figure = plt.figure(figsize=(8, 6.5))
    axis = figure.add_subplot(projection="3d")
    mesh_x, mesh_y = np.meshgrid(grid, grid)
    axis.plot_surface(mesh_x, mesh_y, surface, cmap="viridis", linewidth=0, antialiased=True)
    axis.set_xlabel("speedup reference shift")
    axis.set_ylabel("size reference shift")
    axis.set_zlabel("mean exact hypervolume")
    axis.set_title("Hypervolume over reference-point shifts (compile reference fixed)")
    save(figure, "fig4_pareto_3d_hypervolume_surface.pdf")


def figure_z3_scaling():
    rows = read_csv(PROOFS_CSV)
    points = [
        (float(row["names_refines"]) + float(row["names_violated"]) + float(row["names_unknown"]), float(row["check_seconds"]))
        for row in rows if float(row["check_seconds"]) > 0
    ]
    xs = np.array([max(1.0, p[0]) for p in points])
    ys = np.array([p[1] for p in points])
    figure, axis = plt.subplots(figsize=(7, 5))
    axis.scatter(xs, ys, s=8, alpha=0.5, color="#2c3e50")
    axis.set_xscale("log")
    axis.set_yscale("log")
    axis.set_xlabel("names compared per sweep (log; sweeps with none are plotted at 1)")
    axis.set_ylabel("validation time per sweep, seconds (log)")
    axis.set_title("Per-sweep validation time: opt re-derivation plus Z3 queries")
    save(figure, "fig5_z3_solver_scaling_profile.pdf")


def main():
    figure_entropy_rpb()
    figure_hypervolume_surface()
    figure_z3_scaling()
    return 0


if __name__ == "__main__":
    sys.exit(main())
