"""The M_pass observations cover every kernel whose R2 and R3 sweeps are complete, read from the recorded telemetry."""

import csv
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from lib.kernel_catalog import all_kernels  # noqa: E402
from lib.pipeline_plans import R3_PASSES, static_plans  # noqa: E402
from lib.regime6_inputs import build_observations  # noqa: E402

MASTER_PATH = ROOT / "data" / "telemetry" / "master_sweeps_28800.csv"
BASELINES_PATH = ROOT / "data" / "telemetry" / "canonical_baselines.json"


class ObservationCoverageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with MASTER_PATH.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        baselines = json.loads(BASELINES_PATH.read_text(encoding="utf-8"))
        kernel_ids = [kernel.kernel_id for kernel in all_kernels()]
        cls.kernel_count = len(kernel_ids)
        cls.observations, cls.excluded = build_observations(kernel_ids, baselines, static_plans(), rows)

    def test_every_kernel_contributes_an_observation(self):
        self.assertEqual(len(self.observations), self.kernel_count)

    def test_no_kernel_is_excluded(self):
        self.assertEqual(self.excluded, [])

    def test_each_observation_holds_every_r3_single_pass(self):
        self.assertEqual(set(self.observations[0]["single"]), set(R3_PASSES))

    def test_each_observation_holds_every_ordered_r3_pair(self):
        self.assertEqual(len(self.observations[0]["pair"]), len(R3_PASSES) ** 2)


if __name__ == "__main__":
    unittest.main()
