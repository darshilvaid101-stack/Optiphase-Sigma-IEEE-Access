"""Build the three manuscripts with tectonic and keep each build's log for the verifier.

ACM and SN compile in place. The IEEE Access class loads spotcolor for its Pantone accent colour, and spotcolor needs
pdfTeX, while tectonic runs XeTeX. The IEEE build therefore runs in a staging copy whose Pantone block is replaced by
the spot colour's own CMYK alternative, which is blue. The class also loads hyperref only under pdfTeX, so the staging copy loads it explicitly
for the XeTeX build, with the class's own options. The repository's copy of the class, the repository's main file, and
the Overleaf bundle keep the original, and under pdfLaTeX the class loads hyperref itself.
"""

import re
import shutil
import subprocess
import sys
from pathlib import Path

from lib.kernel_registry import REPO_ROOT

MANUSCRIPT = REPO_ROOT / "manuscript"
BUILD_DIRECTORY = MANUSCRIPT / "build"
IEEE_TEMPLATE = MANUSCRIPT / "ieee_template"
IEEE_STAGE = BUILD_DIRECTORY / "ieee-stage"
FIGURES_DIRECTORY = REPO_ROOT / "figures"
IN_PLACE_STEMS = ("optiphase_sigma_acm", "optiphase_sigma_sn")
IEEE_STEM = "optiphase_sigma_ieee"
IEEE_CLASS = "ieeeaccess.cls"
IEEE_FILES = (IEEE_CLASS, "IEEEtran.cls", "Logo.png", "notaglineLogo.png", "bullet.png")
PANTONE_BLOCK = re.compile(
    r"  \\RequirePackage\{spotcolor\}.*?\\definecolor\{accessblue\}\{spotcolor\}\{PANTONE3015C,1\.0\}%\n", re.DOTALL)
CMYK_ACCENT = "  \\definecolor{accessblue}{cmyk}{1,0.3,0,0.2}\n"
HYPERREF_ANCHOR = "\\usepackage{textcomp}\n"
HYPERREF_LINE = "\\usepackage[hidelinks=true,bookmarks=false]{hyperref}\n"


def replace_pantone_block(class_text):
    """The class text with its single Pantone block replaced by the class's own CMYK fallback, and nothing else."""
    count = len(PANTONE_BLOCK.findall(class_text))
    if count != 1:
        raise RuntimeError(f"expected one Pantone block in {IEEE_CLASS}, found {count}")
    return PANTONE_BLOCK.sub(lambda _match: CMYK_ACCENT, class_text)


def insert_hyperref(main_text):
    """The IEEE main file with hyperref loaded after its last package, for the XeTeX build only."""
    if main_text.count(HYPERREF_ANCHOR) != 1:
        raise RuntimeError("expected one \\usepackage{textcomp} line before the hyperref insertion")
    return main_text.replace(HYPERREF_ANCHOR, HYPERREF_ANCHOR + HYPERREF_LINE, 1)


def run_tectonic(directory, stem):
    """Compile one manuscript in its directory; return the exit status and the combined output."""
    (directory / "build").mkdir(exist_ok=True)
    completed = subprocess.run(
        ["tectonic", "--keep-logs", "-o", "build", f"{stem}.tex"],
        cwd=directory, capture_output=True, text=True, check=False,
    )
    return completed.returncode, completed.stdout + completed.stderr


def record_log(stem, output):
    (BUILD_DIRECTORY / f"{stem}_stdout.txt").write_text(output, encoding="utf-8")


def publish_pdf(source_directory, stem):
    shutil.copy2(source_directory / "build" / f"{stem}.pdf", MANUSCRIPT / f"{stem}.pdf")


def build_in_place(stem):
    status, output = run_tectonic(MANUSCRIPT, stem)
    record_log(stem, output)
    if status == 0:
        publish_pdf(MANUSCRIPT, stem)
    return status


def stage_ieee():
    shutil.rmtree(IEEE_STAGE, ignore_errors=True)
    IEEE_STAGE.mkdir(parents=True)
    main_text = (MANUSCRIPT / f"{IEEE_STEM}.tex").read_text(encoding="utf-8")
    (IEEE_STAGE / f"{IEEE_STEM}.tex").write_text(insert_hyperref(main_text), encoding="utf-8")
    shutil.copy2(MANUSCRIPT / "references_curated.bib", IEEE_STAGE)
    shutil.copytree(MANUSCRIPT / "sections", IEEE_STAGE / "sections")
    shutil.copytree(MANUSCRIPT / "generated", IEEE_STAGE / "generated",
                    ignore=shutil.ignore_patterns("provenance.json"))
    shutil.copytree(FIGURES_DIRECTORY, IEEE_STAGE / "figures", ignore=shutil.ignore_patterns("*.png", "*.svg"))
    for name in IEEE_FILES:
        shutil.copy2(IEEE_TEMPLATE / name, IEEE_STAGE / name)
    class_text = (IEEE_TEMPLATE / IEEE_CLASS).read_text(encoding="utf-8")
    (IEEE_STAGE / IEEE_CLASS).write_text(replace_pantone_block(class_text), encoding="utf-8")


def build_ieee():
    stage_ieee()
    status, output = run_tectonic(IEEE_STAGE, IEEE_STEM)
    record_log(IEEE_STEM, output)
    if status == 0:
        publish_pdf(IEEE_STAGE, IEEE_STEM)
    return status


def main():
    BUILD_DIRECTORY.mkdir(parents=True, exist_ok=True)
    statuses = {stem: build_in_place(stem) for stem in IN_PLACE_STEMS}
    statuses[IEEE_STEM] = build_ieee()
    failed = sorted(stem for stem, status in statuses.items() if status != 0)
    print(f"builds {len(statuses)}, failed {failed or 'none'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
