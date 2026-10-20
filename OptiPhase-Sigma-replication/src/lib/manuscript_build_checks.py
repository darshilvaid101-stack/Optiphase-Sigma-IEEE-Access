"""Checks on the built manuscripts: LaTeX logs, the text of each PDF, and the SHA-256 provenance of the inputs."""

import hashlib
import json
import re
import subprocess
import tempfile
from pathlib import Path

from lib.kernel_registry import REPO_ROOT

OVERFULL_HBOX_PATTERN = re.compile(r"Overfull \\hbox \((\d+(?:\.\d+)?)pt too wide\)(.*)")
OVERFULL_WIDTH_TOLERANCE_POINTS = 0.001
# Overfull boxes the IEEE Access template produces on its own: each entry is (width in points, text that must follow).
# The class footer is one text width and is set on every page; the title block overflows by the same amount in the
# untouched template sample. Any other overfull box, at any width, still counts.
IEEE_TEMPLATE_OVERFULL = (
    (505.12177, "has occurred while \\output is active"),
    (9.2679, "in paragraph at lines"),
)
UNDEFINED_CITATION_PATTERN = re.compile(r"Citation `[^']+' on page \d+ undefined")
UNDEFINED_REFERENCE_PATTERN = re.compile(r"Reference `[^']+' on page \d+ undefined")
MISSING_CHARACTER_PATTERN = re.compile(r"Missing character")
OVERFULL_LIMIT_POINTS = 2.0
BRACKET_ARTIFACT_PATTERN = re.compile(r"\[\?|\?\?\?|\[\s*\]|\[n\. ?d\. ?\]")
LETTER_SPACED_URL_PATTERN = re.compile(r"h\s+t\s+t\s+p|w\s+w\s+w\s*\.\s*\w")


def read_text(path):
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


def is_template_overfull(width, tail, exemptions):
    return any(
        abs(width - exempt_width) < OVERFULL_WIDTH_TOLERANCE_POINTS and marker in tail
        for exempt_width, marker in exemptions
    )


def overfull_widths(log_text, exemptions):
    """Widths of the overfull boxes that count, and how many template boxes were skipped."""
    widths, skipped = [], 0
    for width_text, tail in OVERFULL_HBOX_PATTERN.findall(log_text):
        width = float(width_text)
        if is_template_overfull(width, tail, exemptions):
            skipped += 1
        else:
            widths.append(width)
    return widths, skipped


def build_log_findings(log_path, exemptions=()):
    log_text = read_text(log_path)
    overfull, template_boxes = overfull_widths(log_text, exemptions)
    return {
        "log_present": log_path.exists(),
        "overfull_hbox_over_limit": sum(width > OVERFULL_LIMIT_POINTS for width in overfull),
        "largest_overfull_points": max(overfull, default=0.0),
        "template_overfull_boxes_skipped": template_boxes,
        "undefined_citations": len(UNDEFINED_CITATION_PATTERN.findall(log_text)),
        "undefined_references": len(UNDEFINED_REFERENCE_PATTERN.findall(log_text)),
        "missing_characters": len(MISSING_CHARACTER_PATTERN.findall(log_text)),
    }


def build_log_checks(findings):
    return (
        findings["log_present"],
        findings["overfull_hbox_over_limit"] == 0,
        findings["undefined_citations"] == 0,
        findings["undefined_references"] == 0,
        findings["missing_characters"] == 0,
    )


def pdf_text(pdf_path):
    if not pdf_path.exists():
        return ""
    completed = subprocess.run(["pdftotext", str(pdf_path), "-"], capture_output=True, text=True, check=False)
    return completed.stdout if completed.returncode == 0 else ""


QPDF_OK_EXIT_CODES = (0, 3)
CITE_ANCHOR_PATTERN = re.compile(r"cite\.([A-Za-z0-9_:.\-]+)")


def expanded_pdf(pdf_path):
    """The PDF with its objects written out in plain text, so that annotations and named destinations can be read."""
    if not pdf_path.exists():
        return ""
    with tempfile.TemporaryDirectory() as directory:
        target = Path(directory) / "expanded.pdf"
        completed = subprocess.run(
            ["qpdf", "--qdf", "--object-streams=disable", str(pdf_path), str(target)],
            capture_output=True, check=False,
        )
        if completed.returncode not in QPDF_OK_EXIT_CODES:
            return ""
        return target.read_bytes().decode("latin-1")


def pdf_findings(pdf_path, citation_keys):
    text = pdf_text(pdf_path)
    expanded = expanded_pdf(pdf_path)
    anchors = set(CITE_ANCHOR_PATTERN.findall(expanded))
    leaked_keys = sorted(key for key in citation_keys if key in text)
    return {
        "pdf_present": pdf_path.exists(),
        "pdf_text_present": bool(text),
        "pdf_expandable": bool(expanded),
        "link_annotations": expanded.count("/Subtype /Link"),
        "unlinked_citation_keys": sorted(key for key in citation_keys if key not in anchors),
        "raw_keys_in_text": leaked_keys,
        "bracket_artifacts": len(BRACKET_ARTIFACT_PATTERN.findall(text)),
        "letter_spaced_urls": len(LETTER_SPACED_URL_PATTERN.findall(text)),
    }


def pdf_checks(findings):
    return (
        findings["pdf_present"],
        findings["pdf_text_present"],
        findings["pdf_expandable"] and findings["link_annotations"] > 0,
        findings["unlinked_citation_keys"] == [],
        findings["raw_keys_in_text"] == [],
        findings["bracket_artifacts"] == 0,
        findings["letter_spaced_urls"] == 0,
    )


def file_sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def provenance_findings(provenance_path):
    """Compare each recorded input hash with the file on disk now."""
    if not provenance_path.exists():
        return {"present": False, "inputs": 0, "mismatched": []}
    inputs = json.loads(provenance_path.read_text(encoding="utf-8"))["inputs"]
    mismatched = []
    for relative, expected in inputs.items():
        path = REPO_ROOT / relative
        if not path.exists() or file_sha256(path) != expected:
            mismatched.append(relative)
    return {"present": True, "inputs": len(inputs), "mismatched": sorted(mismatched)}
