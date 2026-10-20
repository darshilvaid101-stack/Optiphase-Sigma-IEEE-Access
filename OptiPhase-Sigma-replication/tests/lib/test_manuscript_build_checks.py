"""Build checks: the overfull-box limit, undefined references, and provenance hashes of the manuscript inputs."""

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from lib.manuscript_build_checks import (  # noqa: E402
    IEEE_TEMPLATE_OVERFULL,
    build_log_findings,
    provenance_findings,
)

LOG_TEXT = r"""Overfull \hbox (1.5pt too wide) in paragraph at lines 12--13
Overfull \hbox (3.2pt too wide) in paragraph at lines 40--41
LaTeX Warning: Citation `missing2024key' on page 3 undefined on input line 9.
"""


class BuildLogTests(unittest.TestCase):
    def test_counts_only_overfull_boxes_above_the_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "build.log"
            log.write_text(LOG_TEXT, encoding="utf-8")
            findings = build_log_findings(log)
        self.assertEqual(findings["overfull_hbox_over_limit"], 1)

    def test_reports_the_largest_overfull_box(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "build.log"
            log.write_text(LOG_TEXT, encoding="utf-8")
            findings = build_log_findings(log)
        self.assertEqual(findings["largest_overfull_points"], 3.2)

    def test_counts_an_undefined_citation(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "build.log"
            log.write_text(LOG_TEXT, encoding="utf-8")
            findings = build_log_findings(log)
        self.assertEqual(findings["undefined_citations"], 1)

    def test_a_missing_log_is_reported_as_absent(self):
        findings = build_log_findings(Path("/nonexistent/build.log"))
        self.assertFalse(findings["log_present"])


FOOTER_LOG = r"""Overfull \hbox (505.12177pt too wide) has occurred while \output is active
Overfull \hbox (9.2679pt too wide) in paragraph at lines 65--65
Overfull \hbox (9.2679pt too wide) in paragraph at lines 80--80
Overfull \hbox (9.2679pt too wide) has occurred while \output is active
"""


class TemplateExemptionTests(unittest.TestCase):
    def findings(self, text):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "build.log"
            log.write_text(text, encoding="utf-8")
            return build_log_findings(log, IEEE_TEMPLATE_OVERFULL)

    def test_template_footer_box_is_skipped(self):
        self.assertEqual(self.findings(FOOTER_LOG)["template_overfull_boxes_skipped"], 3)

    def test_a_template_width_outside_its_context_still_counts(self):
        self.assertEqual(self.findings(FOOTER_LOG)["overfull_hbox_over_limit"], 1)

    def test_an_unexplained_overfull_box_counts_at_any_width(self):
        findings = self.findings(r"Overfull \hbox (4.0pt too wide) in paragraph at lines 3--3" + "\n")
        self.assertEqual(findings["overfull_hbox_over_limit"], 1)


class ProvenanceTests(unittest.TestCase):
    def test_matching_input_hash_is_not_mismatched(self):
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory) / "input.csv"
            data.write_text("a,b\n1,2\n", encoding="utf-8")
            digest = hashlib.sha256(data.read_bytes()).hexdigest()
            provenance = Path(directory) / "provenance.json"
            provenance.write_text(json.dumps({"inputs": {str(data): digest}}), encoding="utf-8")
            findings = provenance_findings(provenance)
        self.assertEqual(findings["mismatched"], [])

    def test_changed_input_is_reported_as_mismatched(self):
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory) / "input.csv"
            data.write_text("a,b\n1,2\n", encoding="utf-8")
            provenance = Path(directory) / "provenance.json"
            provenance.write_text(json.dumps({"inputs": {str(data): "0" * 64}}), encoding="utf-8")
            findings = provenance_findings(provenance)
        self.assertEqual(findings["mismatched"], [str(data)])


if __name__ == "__main__":
    unittest.main()
