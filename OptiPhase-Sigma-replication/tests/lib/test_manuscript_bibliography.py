"""The curated bibliography rules: counts, DOI repeats, url fields, years, and which entries are cited."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from lib.manuscript_bibliography import bibliography_entries, bibliography_report, citation_report  # noqa: E402

CURATED_ENTRY = """@article{ashouri2026protean,
  title = {{Protean Compiler}},
  year = {2026},
  doi = {10.1145/3831596},
}
"""
FOUNDATIONAL_ENTRY = """@inproceedings{lattner2004llvm,
  title = {{LLVM}},
  year = {2004},
  doi = {10.1109/cgo.2004.1281665},
}
"""


def write_bib(directory, text):
    path = Path(directory) / "references.bib"
    path.write_text(text, encoding="utf-8")
    return path


class BibliographyReportTests(unittest.TestCase):
    def test_counts_curated_and_foundational_entries_separately(self):
        with tempfile.TemporaryDirectory() as directory:
            entries = bibliography_entries(write_bib(directory, CURATED_ENTRY + FOUNDATIONAL_ENTRY))
        report = bibliography_report(entries)
        self.assertEqual((report["curated_count"], report["foundational_count"]), (1, 1))

    def test_reports_a_doi_shared_by_two_entries(self):
        shared = CURATED_ENTRY + CURATED_ENTRY.replace("ashouri2026protean", "second2026key")
        with tempfile.TemporaryDirectory() as directory:
            entries = bibliography_entries(write_bib(directory, shared))
        self.assertEqual(bibliography_report(entries)["duplicate_dois"], ["10.1145/3831596"])

    def test_reports_an_entry_with_a_url_field(self):
        with_url = CURATED_ENTRY.replace("}\n", "  url = {https://example.org},\n}\n")
        with tempfile.TemporaryDirectory() as directory:
            entries = bibliography_entries(write_bib(directory, with_url))
        self.assertEqual(bibliography_report(entries)["entries_with_url_field"], ["ashouri2026protean"])

    def test_reports_an_entry_without_a_year(self):
        without_year = CURATED_ENTRY.replace("  year = {2026},\n", "")
        with tempfile.TemporaryDirectory() as directory:
            entries = bibliography_entries(write_bib(directory, without_year))
        self.assertEqual(bibliography_report(entries)["entries_without_year"], ["ashouri2026protean"])


class CitationReportTests(unittest.TestCase):
    def test_reports_a_curated_entry_that_no_section_cites(self):
        with tempfile.TemporaryDirectory() as directory:
            entries = bibliography_entries(write_bib(directory, CURATED_ENTRY))
            section = Path(directory) / "section.tex"
            section.write_text("No citation here.", encoding="utf-8")
            report = citation_report([section], entries)
        self.assertEqual(report["uncited_curated_keys"], ["ashouri2026protean"])

    def test_counts_a_curated_entry_cited_in_a_section(self):
        with tempfile.TemporaryDirectory() as directory:
            entries = bibliography_entries(write_bib(directory, CURATED_ENTRY))
            section = Path(directory) / "section.tex"
            section.write_text(r"As shown~\cite{ashouri2026protean}.", encoding="utf-8")
            report = citation_report([section], entries)
        self.assertEqual(report["cited_curated_count"], 1)


if __name__ == "__main__":
    unittest.main()
