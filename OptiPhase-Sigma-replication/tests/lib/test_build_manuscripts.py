"""The IEEE staging transforms: the Pantone accent becomes its CMYK fallback, and hyperref loads after the last package."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import build_manuscripts as builder  # noqa: E402

PANTONE_CLASS = (
    "before\n"
    "  \\RequirePackage{spotcolor}\n"
    "  \\NewSpotColorSpace{PANTONE}\n"
    "  \\AddSpotColor{PANTONE} {PANTONE3015C} {PANTONE\\SpotSpace 3015\\SpotSpace C} {1 0.3 0 0.2}\n"
    "  \\SetPageColorSpace{PANTONE}%\n"
    "  \\definecolor{accessblue}{spotcolor}{PANTONE3015C,1.0}%\n"
    "after\n"
)


class PantoneBlockTests(unittest.TestCase):
    def test_the_block_becomes_the_cmyk_fallback_and_nothing_else_changes(self):
        self.assertEqual(builder.replace_pantone_block(PANTONE_CLASS), "before\n" + builder.CMYK_ACCENT + "after\n")

    def test_a_class_without_the_block_is_an_error(self):
        with self.assertRaises(RuntimeError):
            builder.replace_pantone_block("no accent colour here\n")


class HyperrefInsertionTests(unittest.TestCase):
    MAIN = "\\documentclass{ieeeaccess}\n\\usepackage{textcomp}\n\\begin{document}\n"

    def test_hyperref_is_loaded_right_after_the_last_package(self):
        expected = "\\documentclass{ieeeaccess}\n\\usepackage{textcomp}\n" + builder.HYPERREF_LINE + "\\begin{document}\n"
        self.assertEqual(builder.insert_hyperref(self.MAIN), expected)

    def test_a_main_file_without_the_anchor_is_an_error(self):
        with self.assertRaises(RuntimeError):
            builder.insert_hyperref("\\documentclass{ieeeaccess}\n\\begin{document}\n")


if __name__ == "__main__":
    unittest.main()
