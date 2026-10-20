# OptiPhase-Σ: replication package

This package contains the code, telemetry, figures, and manuscript sources for *OptiPhase-Σ: Measured Pass Interference and Bounded Refinement Checks in the LLVM New Pass Manager*, by Devarsh Patel, Darshil Vaid, and Kanagaraj R (School of Computer Science and Engineering, Vellore Institute of Technology, Vellore, India). The manuscript is prepared for IEEE Access. The ACM and Springer Nature versions of the same sections are included.

The study measures how passes of the LLVM new pass manager interact on 60 benchmark kernels from PolyBench/C, MiBench, and TSVC/CoreMark, over 28,800 pipeline sweeps. It checks the refinement of optimized code block by block with Z3, and it analyses Pareto fronts of the sweeps.

Citation and licence: to be added by the authors before publication. No licence file is included.

## Contents

| Path | Contents |
| --- | --- |
| `README.md` | This file. |
| `requirements.txt` | Python packages, with pinned versions. |
| `run_all_autonomous.sh` | Runs the pipeline stages in dependency order (see *Reproducing*). |
| `.gitignore` | Paths that are not versioned: build outputs and third-party benchmark sources. |
| `src/` | Scripts (top level) and shared modules (`src/lib/`). |
| `tests/lib/` | Unit tests for the shared modules. |
| `config/` | Tool locations and run parameters, the pass list, validity, substitute and replacement tables, and gap-mining patterns. |
| `data/benchmarks/` | Manifests of the benchmark suites: source URLs, versions, and SHA-256 values. The sources are not included. |
| `data/telemetry/` | Sweep telemetry and analysis outputs. |
| `data/smt2_certificates/` | SMT-LIB 2 certificates for the sweeps on the Pareto fronts, with `manifest.json`. |
| `data/literature/` | Literature harvest and gap-mining outputs. |
| `figures/` | The four figures of the manuscripts, as vector PDFs. The file names keep their original numbers (`fig1`, `fig3`, `fig4`, `fig5`); the manuscripts number them 1 to 4. |
| `manuscript/` | Manuscript sources for IEEE Access, ACM, and Springer Nature, the shared sections, the bibliography, the generated macros and tables, the compiled PDFs, and the integrity report. |

## Scripts

| Script | Purpose | Main outputs |
| --- | --- | --- |
| `task1_lit_harvester.py` | Harvests 2024–2026 venue papers (needs network access), verifies each DOI, and writes BibTeX. | `data/literature/references_2500.bib`, `harvested_metadata.jsonl` |
| `task2_nlp_gap_miner.py` | Mines limitation sentences from the harvested abstracts and maps them to clusters G1–G6. | `data/literature/mined_gaps_*.csv`, `gap_mining_summary.json` |
| `audit_gap_precision.py` | Recounts the gap-precision audit from the stored judgments. | Reads `gap_precision_audit.json`. |
| `task3_benchmark_scaffolder.py` | Builds the 60 kernels from the manifests to canonical bitcode, and checks them against native runs. | `data/benchmarks/bitcode_O0_canon/` (built locally) |
| `rebuild_canonical.py` | Rebuilds the canonical bitcode with the current pipeline and refreshes its manifest. Run it when the canonical pipeline changes. | `data/benchmarks/bitcode_O0_canon/MANIFEST.json` |
| `task4_sweep_engine.py` | The sweep campaign: phases `r1-r5`, `r2x`, and `r6`. | `master_sweeps_28800.csv`, `sweep_audit.jsonl`, `sweep_plan*.json`, `m_pass_transition_matrix.csv`, `canonical_baselines.json` |
| `verify_bitcount_digests.py` | Re-verifies the output digests of the bitcount sweeps. | `bitcount_output_check.json` |
| `verify_sweep_variants.py` | Checks the standalone `instcombine` spelling and the crash replacements. | `sweep_variant_checks.json` |
| `verify_z3_encoding.py` | Checks the Z3 encoder against the reference semantics. | `z3_encoding_agreement.json` |
| `task5_z3_verifier_and_math.py` | Block-local Z3 validation, Pareto fronts, exact hypervolume, and pass algebra. | `z3_verification_proofs.csv`, `pareto_3d_frontiers.csv`, `rpb_summary.json`, `lie_bracket_mean.csv` |
| `analyze_refinement.py` | Analyses the refinement verdicts against the telemetry. | `refinement_analysis.json` |
| `analyze_sat_witnesses.py` | Classifies the SAT witnesses and attributes each flag added by the optimizer. | `sat_witness_attribution.json` |
| `export_certificates.py` | Exports SMT-LIB 2 certificates and re-checks each query with the Z3 binary. | `data/smt2_certificates/` |
| `pass_checks.py` | IR-level checks of each pass on the canonical kernels. | `pass_checks.json` |
| `lowering_pilot.py` | Tests whether the lowering level changes the size effect of a middle-end pass. | `lowering_pilot.json` |
| `investigate_output_exceptions.py` | Reproduces the four output exceptions. Run separately. | `output_exceptions.json` |
| `figure_instcount.py` | Figure 1: the instruction-count interaction. | `figures/fig1_*.pdf` |
| `task5_plot_generator.py` | Figures of the entropy, hypervolume, and solver-scaling analyses. | `figures/fig3_*.pdf`, `fig4_*.pdf`, `fig5_*.pdf` |
| `task6_manuscript_author.py` | Writes the macros, the tables, and the provenance checksums. | `manuscript/generated/` |
| `build_manuscripts.py` | Builds the three manuscripts and keeps the log of each build. | `manuscript/*.pdf`, `manuscript/build/` |
| `verify_manuscript.py` | Integrity checks: bibliography, labels, numbers in the prose, overlap with the sources, build logs, PDF links, and provenance. | `manuscript/integrity_report.json` |
| `build_overleaf_bundle.py` | Assembles the IEEE Access source files for upload to Overleaf. Optional. | `manuscript/build/overleaf_ieee_access/` |

Other modules are in `src/lib/`: the Z3 encoder and its reference semantics, the LLVM tool wrappers, the sweep executor, the pass algebra, the literature clients, and the manuscript macro and table builders.

## Requirements

- Python 3.12, with the packages in `requirements.txt`. The environment used to check this package had Python 3.12.6.
- LLVM 23.1.3, with `opt`, `llc`, `lli`, `llvm-link`, `llvm-dis`, `llvm-size`, `llvm-mca`, and `clang`. Their locations are in `config/global_config.yaml`, which lists Homebrew paths.
- A Z3 command-line binary (location in `config/global_config.yaml`). The environment used to check this package had version 5.1.0; the Python package `z3-solver` is pinned at 5.3.0.0 in `requirements.txt`.
- tectonic for the LaTeX builds. The environment used to check this package had version 0.17.0.
- Network access for `task1_lit_harvester.py`, which queries OpenAlex, Crossref, and arXiv.

## Reproducing

1. Create the environment in `.venv` and install the requirements:

   ```bash
   python3.12 -m venv .venv
   .venv/bin/pip install -r requirements.txt
   ```

2. Run the pipeline. `run_all_autonomous.sh` runs the stages in this order: the literature stages, the benchmark build, the sweep campaign (phases `r1-r5`, `r2x`, and `r6`), the sweep and encoder checks, the Z3 analysis, the refinement and witness analyses, the certificate export, the pass checks, the lowering pilot, the figures, the manuscript macros and tables, the manuscript builds, and the integrity check. The script stops at the first failing stage.

   ```bash
   ./run_all_autonomous.sh
   ```

   The sweep campaign is CPU-bound and takes several hours, so run it on an otherwise idle machine. The harvest depends on the public APIs at the time of running, so its outputs may differ from the stored ones.

3. Run the unit tests:

   ```bash
   .venv/bin/python -m unittest discover -s tests/lib -p 'test_*.py'
   ```

   One test class, in `tests/lib/test_regime6_inputs.py`, reads the benchmark sources that the benchmark stage builds, so it fails if step 2 has not run. The other tests do not need the sources.

4. Run `investigate_output_exceptions.py` and, if needed, `rebuild_canonical.py` separately, as described in the table above.

The integrity check reads the build logs in `manuscript/build/`, which the manuscript build creates. Run the manuscript build before `verify_manuscript.py`, as step 2 does.

## Data notes

- `data/telemetry/master_sweeps_28800.csv` has one row per sweep: 28,800 rows and 26 columns.
- `data/telemetry/` holds the other outputs listed in the table above. The manuscript's numbers come from these files.
- `data/telemetry/archive_v1/` holds the outputs of an earlier campaign. They are kept for the record, and the manuscript does not draw on them.
- `data/benchmarks/` holds the manifests of the benchmark suites. Each manifest records the upstream source, its version, and the SHA-256 value of every file. The sources are third-party software and are not redistributed here. `task3_benchmark_scaffolder.py` rebuilds the kernels from the manifests.
- `data/literature/` holds the harvest and gap-mining outputs. `harvested_metadata.jsonl` holds the public metadata and abstracts that the overlap checks use. `references_2500.bib` is the earlier, larger harvest; the manuscripts cite `manuscript/references_curated.bib`.
- `data/literature/gap_precision_audit.json` records judgments that an AI assistant made, as its method field states. The statement is kept because it describes how the data were produced.
- `manuscript/generated/provenance.json` lists the SHA-256 checksum of each input that `task6_manuscript_author.py` reads.

## Edits made for this package

- This README was written for the package.
- The local root path in `config/global_config.yaml` and in the two benchmark manifests (`polybench_c_4.2.1` and `tsvc_coremark`) was replaced by a relative path or by `<repository root>`. The local path in `data/telemetry/archive_v1/sweep_audit.jsonl` was replaced by `<repository root>`. No values changed.
- Two limitation notes, in `task2_nlp_gap_miner.py` and in `data/literature/gap_mining_summary.json`, were reworded to remove references to files that are not in this package. No values changed.
- Comments and docstrings in nine source files were edited to remove references to internal decision numbers and to files that are not in this package.
- `src/build_overleaf_bundle.py` and `src/verify_manuscript.py` use repository-relative paths. The integrity report records whether the design dossier was present. A docstring in `task5_plot_generator.py` now gives the correct number of figures.
- `run_all_autonomous.sh` builds the manuscripts with `src/build_manuscripts.py`.

## Known limits

- Two files whose checksums are recorded in `manuscript/generated/provenance.json` keep details of the original machine. `config/llvm_newpm_pass_validity.json` contains local absolute paths in its error messages, and `config/llvm_newpm_crash_replacements.json` contains an internal decision number in one note. They are unchanged, so that the recorded checksums still hold.
- The design dossier and the project's working documents are not part of this package. The overlap check against the dossier is skipped when the dossier is absent, and `manuscript/integrity_report.json` records this.
- The timing measurements depend on the hardware and its load. The manuscript reports their noise.
- The IEEE PDF in `manuscript/` was built with the class's accent colour replaced by its CMYK fallback, because tectonic runs XeTeX and the class needs pdfTeX for its Pantone colour. Building with pdfLaTeX (for example, on Overleaf) uses the class's own colour. `src/build_manuscripts.py` describes the substitution.
- No licence file is included. The authors must choose one before publication.
