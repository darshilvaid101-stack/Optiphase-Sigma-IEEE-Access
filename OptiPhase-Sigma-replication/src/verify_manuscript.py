"""Local integrity checks for the three manuscripts. Nothing is uploaded: all text stays on this machine.

Hard checks, all of which must pass: the curated bibliography holds CURATED_COUNT papers from 2024 onward, every one of them
cited, and the only other keys cited are the foundational tool and benchmark references; no DOI repeats and no entry has a
url field; every citation key exists; every reference label is defined; each build's log has no overfull horizontal box
above the limit, no undefined citation or reference, and no missing character; each build's PDF text holds no raw citation
key, bracket artifact, or letter-spaced URL; the inputs match their recorded SHA-256 provenance; no legacy manuscript file
remains; prose contains no bare number (every quantity is a macro); and no 12-word run in the prose is copied from a
harvested abstract or, when the design dossier is present, from that dossier, outside quotation marks. The defect checks find leftover phrases, internal file names in the body, and run-in labels printed without a
title. Soft report: unused bibliography entries and 8-word
runs shared with those sources.
"""

import json
import re
import sys
from pathlib import Path

from lib.kernel_registry import REPO_ROOT
from lib.manuscript_bibliography import (
    bibliography_checks_pass,
    bibliography_entries,
    bibliography_report,
    citation_report,
    read_text,
)
from lib.manuscript_build_checks import (
    IEEE_TEMPLATE_OVERFULL,
    build_log_checks,
    build_log_findings,
    pdf_checks,
    pdf_findings,
    pdf_text,
    provenance_findings,
)
from lib.manuscript_defects import body_name_hits, orphan_label_hits, phrase_hits

MANUSCRIPT = REPO_ROOT / "manuscript"
PROSE_DIRECTORY = MANUSCRIPT / "sections"
GENERATED_DIRECTORY = MANUSCRIPT / "generated"
BUILD_DIRECTORY = MANUSCRIPT / "build"
BUILDS = {"acm": "optiphase_sigma_acm", "ieee": "optiphase_sigma_ieee", "sn": "optiphase_sigma_sn"}
LEGACY_FILES = (
    "optiphase_sigma_paper.tex",
    "optiphase_sigma_paper.pdf",
    "optiphase_sigma_paper_sn.tex",
    "optiphase_sigma_paper_sn.pdf",
)
ABSTRACTS_PATH = REPO_ROOT / "data" / "literature" / "harvested_metadata.jsonl"
DOSSIER_PATH = REPO_ROOT / "optiphase_sigma_research_dossier.tex"
PROVENANCE_PATH = GENERATED_DIRECTORY / "provenance.json"
REPORT_PATH = MANUSCRIPT / "integrity_report.json"
HARD_OVERLAP_WORDS = 12
SOFT_OVERLAP_WORDS = 8
CITED_HARD_WORDS = 10
CITED_SOFT_WORDS = 8
LABEL_PATTERN = re.compile(r"\\label\{([^}]+)\}")
REF_PATTERN = re.compile(r"\\(?:ref|eqref|autoref|cref|Cref|pageref)\{([^}]+)\}")
CITE_PATTERN = re.compile(r"\\cite[a-zA-Z]*\*?(?:\[[^\]]*\])*\{([^}]*)\}")
COMMENT_PATTERN = re.compile(r"(?<!\\)%.*$", re.MULTILINE)
NON_PROSE_PATTERNS = (
    re.compile(r"\\begin\{(table|figure|equation|align|verbatim|tabular|displaymath)\*?\}.*?\\end\{\1\*?\}", re.DOTALL),
    re.compile(r"\\\[.*?\\\]", re.DOTALL),
    re.compile(r"\$\$.*?\$\$", re.DOTALL),
    re.compile(r"\$[^$]*\$"),
    re.compile(r"\\texttt\{(?:[^{}]|\{[^{}]*\})*\}"),
    re.compile(r"\\(?:cite[a-zA-Z]*|ref|eqref|autoref|cref|Cref|label|input|include|includegraphics|bibliography|"
               r"bibliographystyle|texttt|url|href|SI|si|PaperFigure)\*?(?:\[[^\]]*\])*\{[^}]*\}"),
    # Affiliation indices in the Springer title block are template syntax, not prose.
    re.compile(r"\\(?:author|affil)\*?\[[^\]]*\]"),
)
DIGIT_PATTERN = re.compile(r"(?<![A-Za-z\\\d.])\d+(?:[.,]\d+)*")
YEAR_PATTERN = re.compile(r"^(?:19|20)\d{2}$")
QUOTED_PATTERN = re.compile(r"``.*?''|\"[^\"]*\"", re.DOTALL)
WORD_PATTERN = re.compile(r"[a-z0-9]+")


def build_stems():
    return BUILDS.values()


def prose_sources():
    """The shared sections hold the prose. The venue files hold front matter (dates, DOIs, addresses, and figure and
    photo sizes), which is not prose, so they are not scanned here."""
    return sorted(path for path in PROSE_DIRECTORY.glob("*.tex") if path.exists())


def all_tex_sources():
    return [*prose_sources(), *sorted(GENERATED_DIRECTORY.glob("*.tex"))]


def body_text(paths):
    """Only the text a reader sees: everything after \\begin{document} in each file, or the whole file if none."""
    bodies = []
    for path in paths:
        text = read_text(path)
        marker = "\\begin{document}"
        bodies.append(text.split(marker, 1)[1] if marker in text else text)
    return "\n".join(bodies)


def without_non_prose(source):
    text = COMMENT_PATTERN.sub("", source)
    for pattern in NON_PROSE_PATTERNS:
        text = pattern.sub(" ", text)
    return text


def bare_numbers(source):
    tokens = DIGIT_PATTERN.findall(without_non_prose(source))
    return [token for token in tokens if not YEAR_PATTERN.match(token)]


def words(text):
    return WORD_PATTERN.findall(text.lower())


def ngram_set(tokens, size):
    return {" ".join(tokens[index:index + size]) for index in range(len(tokens) - size + 1)}


def abstract_rows():
    if not ABSTRACTS_PATH.exists():
        return []
    return [json.loads(line) for line in ABSTRACTS_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]


def source_ngrams(size):
    grams = set()
    for row in abstract_rows():
        if row.get("abstract"):
            grams |= ngram_set(words(row["abstract"]), size)
    grams |= ngram_set(words(read_text(DOSSIER_PATH)), size)
    return grams


def shared_runs(source, size):
    prose = words(without_non_prose(source))
    quoted = ngram_set(words(" ".join(QUOTED_PATTERN.findall(source))), size)
    runs = {" ".join(prose[index:index + size]) for index in range(len(prose) - size + 1)}
    return sorted((runs & source_ngrams(size)) - quoted)


def label_report(sources):
    text = "\n".join(read_text(path) for path in sources)
    labels = set(LABEL_PATTERN.findall(text))
    refs = set(REF_PATTERN.findall(text))
    return {"undefined_labels": sorted(refs - labels), "labels": len(labels)}


def overlap_report(prose):
    hard = shared_runs(prose, HARD_OVERLAP_WORDS)
    soft = shared_runs(prose, SOFT_OVERLAP_WORDS)
    return {
        "hard_overlap_runs": hard[:50],
        "hard_overlap_count": len(hard),
        "soft_overlap_runs": soft[:50],
        "soft_overlap_count": len(soft),
    }


def longest_shared_run(first, second):
    """Length of the longest run of consecutive words that appears in both token lists."""
    best = 0
    previous = [0] * (len(second) + 1)
    for token in first:
        current = [0] * (len(second) + 1)
        for column, other in enumerate(second, start=1):
            if token == other:
                current[column] = previous[column - 1] + 1
                best = max(best, current[column])
        previous = current
    return best


def corpus_abstracts_by_key():
    return {row["bibtex_key"]: row["abstract"] for row in abstract_rows() if row.get("abstract") and row.get("bibtex_key")}


def cited_overlap_report(prose):
    """Word runs shared between a sentence and the abstract of a work that the sentence cites, outside quotations."""
    abstracts = corpus_abstracts_by_key()
    hard, soft, uncovered = [], [], set()
    for sentence in re.split(r"(?<=[.!?])\s+", prose):
        keys = set()
        for group in CITE_PATTERN.findall(sentence):
            keys.update(key.strip() for key in group.split(",") if key.strip())
        if not keys:
            continue
        sentence_words = words(without_non_prose(QUOTED_PATTERN.sub(" ", sentence)))
        for key in sorted(keys):
            if key not in abstracts:
                uncovered.add(key)
                continue
            run = longest_shared_run(sentence_words, words(abstracts[key]))
            record = {"key": key, "run_words": run, "sentence": sentence.strip()[:200]}
            if run >= CITED_HARD_WORDS:
                hard.append(record)
            elif run >= CITED_SOFT_WORDS:
                soft.append(record)
    return {
        "hard_count": len(hard),
        "soft_count": len(soft),
        "hard": hard[:50],
        "soft": soft[:50],
        "cited_keys_without_abstract": len(uncovered),
    }


def legacy_files_present():
    return [name for name in LEGACY_FILES if (MANUSCRIPT / name).exists()]


def per_build_findings(entries):
    keys = list(entries)
    findings = {}
    for name, stem in BUILDS.items():
        exemptions = IEEE_TEMPLATE_OVERFULL if stem == BUILDS["ieee"] else ()
        log = build_log_findings(BUILD_DIRECTORY / f"{stem}_stdout.txt", exemptions)
        pdf = pdf_findings(MANUSCRIPT / f"{stem}.pdf", keys)
        findings[name] = {"log": log, "pdf": pdf}
    return findings


def build_checks(findings):
    checks = []
    for build in findings.values():
        checks += [*build_log_checks(build["log"]), *pdf_checks(build["pdf"])]
    return checks


def defect_report():
    body = [path for path in prose_sources() if path.name != "declarations.tex"]
    body_text = "\n".join(read_text(path) for path in body)
    pdf_texts = {name: pdf_text(MANUSCRIPT / f"{stem}.pdf") for name, stem in BUILDS.items()}
    return {
        "body_file_names": body_name_hits(body_text),
        "pdf_phrases": {name: phrase_hits(content) for name, content in pdf_texts.items()},
        "pdf_orphan_labels": {name: orphan_label_hits(content) for name, content in pdf_texts.items()},
    }


def defect_checks(defects):
    return [
        defects["body_file_names"] == [],
        all(hits == [] for hits in defects["pdf_phrases"].values()),
        all(hits == [] for hits in defects["pdf_orphan_labels"].values()),
    ]


def main():
    entries = bibliography_entries()
    sources = all_tex_sources()
    prose = body_text(prose_sources())
    citations = citation_report(sources, entries)
    report = {
        "bibliography": bibliography_report(entries),
        "citations": citations,
        "labels": label_report(sources),
        "builds": per_build_findings(entries),
        "provenance": provenance_findings(PROVENANCE_PATH),
        "legacy_files_present": legacy_files_present(),
        "bare_number_count": len(bare_numbers(prose)),
        "bare_numbers": bare_numbers(prose)[:50],
        "overlap": overlap_report(prose),
        "cited_overlap": cited_overlap_report(prose),
        "defects": defect_report(),
        "dossier_present": DOSSIER_PATH.exists(),
    }
    checks = [
        *bibliography_checks_pass(report["bibliography"], citations),
        citations["missing_bibliography_keys"] == [],
        report["labels"]["undefined_labels"] == [],
        *build_checks(report["builds"]),
        report["provenance"]["present"] and report["provenance"]["mismatched"] == [],
        report["legacy_files_present"] == [],
        report["bare_number_count"] == 0,
        report["overlap"]["hard_overlap_count"] == 0,
        report["cited_overlap"]["hard_count"] == 0,
        *defect_checks(report["defects"]),
    ]
    report["hard_checks_passed"] = all(checks)
    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "hard_checks_passed": report["hard_checks_passed"],
        "curated_count": report["bibliography"]["curated_count"],
        "cited_curated_count": citations["cited_curated_count"],
        "cited_recent_share": citations["cited_recent_share"],
        "bare_number_count": report["bare_number_count"],
        "overlap_hard": report["overlap"]["hard_overlap_count"],
        "cited_overlap_hard": report["cited_overlap"]["hard_count"],
        "legacy_files_present": report["legacy_files_present"],
        "provenance_mismatched": report["provenance"].get("mismatched", []),
        "builds": {name: {"log": build["log"], "pdf": build["pdf"]} for name, build in report["builds"].items()},
    }, indent=2))
    return 0 if report["hard_checks_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
