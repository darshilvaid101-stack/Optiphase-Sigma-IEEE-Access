"""Assemble the IEEE Access submission for Overleaf: a folder and a zip with main.tex at the top level.

The bundle holds the main file, the shared sections, the generated macros and tables, the figures the text uses, the
curated bibliography, and the IEEE Access class files exactly as the template ships them. The main file differs from
the repository's copy only in its graphics path, which points at the bundle's own figures folder.
"""

import re
import shutil
import sys
import zipfile
from pathlib import Path

from lib.kernel_registry import REPO_ROOT

MANUSCRIPT = REPO_ROOT / "manuscript"
TEMPLATE = MANUSCRIPT / "ieee_template"
FIGURES = REPO_ROOT / "figures"
BUNDLE = REPO_ROOT / "manuscript" / "build" / "overleaf_ieee_access"
ARCHIVE = BUNDLE.with_suffix(".zip")
MAIN_SOURCE = MANUSCRIPT / "optiphase_sigma_ieee.tex"
MAIN_NAME = "main.tex"
GRAPHICS_LINE_OLD = "\\graphicspath{{figures/}{../figures/}}\n"
GRAPHICS_LINE_NEW = "\\graphicspath{{figures/}}\n"
BIBLIOGRAPHY = "references_curated.bib"
TEMPLATE_FILES = ("ieeeaccess.cls", "IEEEtran.cls", "Logo.png", "notaglineLogo.png", "bullet.png")
INPUT_PATTERN = re.compile(r"\\input\{([^}]+)\}")
FIGURE_PATTERN = re.compile(r"\\PaperFigure\{([^}]+\.pdf)\}")
COMMENT_PATTERN = re.compile(r"(?<!\\)%.*")
README_TEXT = """# OptiPhase-Sigma: IEEE Access submission (Overleaf)

Upload this folder, or the zip beside it, to Overleaf with New Project > Upload Project.

Settings:
- Main document: main.tex
- Compiler: pdfLaTeX (the default for this template)
- Bibliography: BibTeX runs automatically; the bibliography file is references_curated.bib

Files:
- main.tex: the paper, with the author, address, and funding blocks of IEEE Access
- sections/: the shared text, included by main.tex
- generated/: the macros and tables computed from the telemetry; do not edit by hand
- figures/: the figures used in the text
- references_curated.bib: the bibliography; every entry is cited
- ieeeaccess.cls, IEEEtran.cls, Logo.png, notaglineLogo.png, bullet.png: the IEEE Access template, unchanged
  (the two logos are named as the class requests them)

Open items before submission (also marked in main.tex and sections/declarations.tex):
- Biographies: placeholders for the three authors. No photographs are used.
- Author contributions: the statement for Kanagaraj R is a placeholder.
- GitHub URL: insert the URL of the replication repository where the bold placeholder in sections/declarations.tex
  (Data and Code Availability) stands. Make that repository public, or deposit an archived copy with a DOI, before submission.
- \\doi and \\history: the template values; IEEE production sets them at acceptance.
- Funding statement, competing interests, and author contributions: check them against the facts.
- AI-use declaration: not in this draft. It must be restored before submission.
- E-mail for the first author: the domain was corrected to vitstudent.ac.in, like the second author's; confirm it.
- Kanagaraj R's affiliation is assumed to be the same School as the other authors. Confirm it.
"""


def bundle_main_text():
    """The repository's main file with the graphics path pointed at the bundle's figures folder."""
    text = MAIN_SOURCE.read_text(encoding="utf-8")
    if text.count(GRAPHICS_LINE_OLD) != 1:
        raise RuntimeError("expected one graphics path line in the main file")
    return text.replace(GRAPHICS_LINE_OLD, GRAPHICS_LINE_NEW, 1)


def section_texts():
    return [path.read_text(encoding="utf-8") for path in sorted((MANUSCRIPT / "sections").glob("*.tex"))]


def uncommented(text):
    return COMMENT_PATTERN.sub("", text)


def input_paths(texts):
    """Every \\input target named by the main file and the sections, as a path under the manuscript folder."""
    names = {name for text in texts for name in INPUT_PATTERN.findall(uncommented(text))}
    return sorted(name if name.endswith(".tex") else f"{name}.tex" for name in names)


def figure_names(texts):
    return sorted({name for text in texts for name in FIGURE_PATTERN.findall(uncommented(text))})


def copy_required(paths, source_root, target_root):
    for relative in paths:
        source = source_root / relative
        if not source.exists():
            raise RuntimeError(f"the paper refers to {relative}, which does not exist")
        target = target_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def assemble_folder():
    shutil.rmtree(BUNDLE, ignore_errors=True)
    BUNDLE.mkdir(parents=True)
    texts = [bundle_main_text(), *section_texts()]
    (BUNDLE / MAIN_NAME).write_text(texts[0], encoding="utf-8")
    copy_required(input_paths(texts), MANUSCRIPT, BUNDLE)
    copy_required([f"figures/{name}" for name in figure_names(texts)], REPO_ROOT, BUNDLE)
    shutil.copy2(MANUSCRIPT / BIBLIOGRAPHY, BUNDLE / BIBLIOGRAPHY)
    for name in TEMPLATE_FILES:
        shutil.copy2(TEMPLATE / name, BUNDLE / name)
    (BUNDLE / "README.md").write_text(README_TEXT, encoding="utf-8")
    return sorted(path for path in BUNDLE.rglob("*") if path.is_file())


def write_archive(files):
    if ARCHIVE.exists():
        ARCHIVE.unlink()
    with zipfile.ZipFile(ARCHIVE, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, arcname=path.relative_to(BUNDLE).as_posix())


def main():
    files = assemble_folder()
    write_archive(files)
    print(f"bundle files {len(files)}: {BUNDLE} and {ARCHIVE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
