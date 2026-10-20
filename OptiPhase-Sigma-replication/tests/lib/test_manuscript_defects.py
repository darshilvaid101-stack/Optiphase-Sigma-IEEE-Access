"""Defect checks: leftover phrases are found in any case, run-in labels only at the start of a line, and body file names."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from lib.manuscript_defects import body_name_hits, orphan_label_hits, phrase_hits  # noqa: E402


class LeftoverPhraseTests(unittest.TestCase):
    def test_a_leftover_phrase_is_found_in_any_case(self):
        self.assertEqual(phrase_hits("We describe the Research Plan here."), ["research plan"])

    def test_clean_text_has_no_leftover_phrase(self):
        self.assertEqual(phrase_hits("The sweep design is listed in the table."), [])


class OrphanLabelTests(unittest.TestCase):
    def test_a_label_at_the_start_of_a_line_is_found(self):
        self.assertEqual(len(orphan_label_hits("a: Soundness of the query. Let B be a block.\nNext line.")), 1)

    def test_a_letter_inside_a_sentence_is_not_a_label(self):
        self.assertEqual(orphan_label_hits("The pass is b: Not a label here."), [])


class BodyFileNameTests(unittest.TestCase):
    def test_script_and_data_paths_are_found(self):
        hits = body_name_hits("The check is in src/pass_checks.py and writes data/telemetry/pass_checks.json.")
        self.assertEqual(hits, ["data/telemetry/pass_checks.json", "src/pass_checks.py"])

    def test_plain_prose_has_no_file_name(self):
        self.assertEqual(body_name_hits("The instruction count is exact for each kernel."), [])


if __name__ == "__main__":
    unittest.main()
