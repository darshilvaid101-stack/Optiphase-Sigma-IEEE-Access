"""The vectorized-loop count reads the loop metadata of the optimized module, not the remark stream."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from lib.telemetry_metrics import vectorized_loop_count  # noqa: E402


class VectorizedLoopCountTests(unittest.TestCase):
    def test_counts_each_loop_marked_as_vectorized(self):
        listing = '!1 = distinct !{!1, !2, !3}\n!2 = !{!"llvm.loop.isvectorized", i32 1}\n!3 = !{!"llvm.loop.isvectorized", i32 1}\n'
        self.assertEqual(vectorized_loop_count(listing), 2)

    def test_returns_zero_when_no_loop_is_vectorized(self):
        self.assertEqual(vectorized_loop_count("define i32 @f() {\n  ret i32 0\n}\n"), 0)

    def test_ignores_a_remark_that_names_the_pass(self):
        self.assertEqual(vectorized_loop_count("remark: loop-vectorize vectorized loop\n"), 0)


if __name__ == "__main__":
    unittest.main()
