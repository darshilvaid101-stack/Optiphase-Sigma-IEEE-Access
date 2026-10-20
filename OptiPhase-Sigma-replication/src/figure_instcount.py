"""Figure 1: the instruction-count interaction over the fifteen R3 passes, averaged over kernels.

Cells on the diagonal (a pass with itself) are left blank. They are reported in their own table.
"""

import csv
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from lib.manuscript_instcount import instcount_interactions, interaction_statistics  # noqa: E402
from lib.pipeline_plans import R3_PASSES  # noqa: E402

MASTER_PATH = REPO_ROOT / "data/telemetry/master_sweeps_28800.csv"
OUTPUT_PATH = REPO_ROOT / "figures/fig1_instcount_interaction_heatmap.pdf"
PERCENT = 100.0


def interaction_matrix():
    with MASTER_PATH.open(encoding="utf-8", newline="") as handle:
        master = list(csv.DictReader(handle))
    stats = interaction_statistics(instcount_interactions(master))
    matrix = np.array([[stats[(first, second)][0] for second in R3_PASSES] for first in R3_PASSES]) * PERCENT
    np.fill_diagonal(matrix, np.nan)
    return matrix


def main():
    matrix = interaction_matrix()
    limit = np.nanmax(np.abs(matrix))
    figure, axis = plt.subplots(figsize=(7.2, 6.2))
    image = axis.imshow(matrix, cmap="RdBu_r", vmin=-limit, vmax=limit)
    axis.set_xticks(range(len(R3_PASSES)), R3_PASSES, rotation=90)
    axis.set_yticks(range(len(R3_PASSES)), R3_PASSES)
    axis.set_xlabel("second pass")
    axis.set_ylabel("first pass")
    colorbar = figure.colorbar(image, ax=axis)
    colorbar.set_label("interaction, % of canonical instruction count")
    figure.tight_layout()
    figure.savefig(OUTPUT_PATH)
    print(f"wrote {OUTPUT_PATH}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
