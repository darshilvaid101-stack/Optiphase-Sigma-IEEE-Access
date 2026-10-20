"""Macros for the refinement analysis: coverage of the block fragment, flags added by SAT candidates, and outputs."""

from lib.manuscript_macros import integer, macro, percent

FLAG_WORDS = (("nuw", "Nuw"), ("nsw", "Nsw"), ("nneg", "Nneg"), ("samesign", "Samesign"), ("disjoint", "Disjoint"),
              ("exact", "Exact"))


def refinement_macros(report):
    totals = report["coverage"]["totals"]
    candidates = report["sat_candidates"]
    matched = totals["blocks_matched"]
    encodable = totals["blocks_compared"]
    lines = [
        macro("BlocksMatched", integer(matched)),
        macro("BlocksEncodable", integer(encodable)),
        macro("BlocksOutsideFragment", integer(totals["blocks_not_encodable"])),
        macro("BlocksEncodablePct", percent(encodable, matched)),
        macro("NamesRefine", integer(totals["names_refines"])),
        macro("NamesViolated", integer(totals["names_violated"])),
        macro("SatSweeps", integer(candidates["sweeps"])),
        macro("SatAddingFlagCount", integer(candidates["adding_wrap_or_exactness_flag"])),
        macro("SatAddingFlagPct", percent(candidates["adding_wrap_or_exactness_flag"], candidates["sweeps"])),
    ]
    for key, word in FLAG_WORDS:
        lines.append(macro(f"SatAdds{word}Count", integer(candidates["flags_added_by_sweep"][key])))
    verdicts = report["outputs_by_verdict"]
    agreeing = sum(row["sweeps"] for row in verdicts if row["output_matches_canonical"])
    total = sum(row["sweeps"] for row in verdicts)
    lines += [
        macro("OutputsAgreeing", integer(agreeing)),
        macro("OutputsChecked", integer(total)),
        macro("OutputsDiffering", integer(total - agreeing)),
        macro("BitcountRecheckChecked", integer(report["bitcount_recheck"]["sweeps_checked"])),
        macro("BitcountRecheckMatching", integer(report["bitcount_recheck"]["sweeps_matching_canonical"])),
    ]
    return lines


def certificate_macros(manifest):
    summary = manifest["summary"]
    return [
        macro("CertSweeps", integer(summary["sweeps"])),
        macro("CertQueries", integer(summary["queries"])),
        macro("CertSolverUnsat", integer(summary["solver_verdicts"].get("UNSAT", 0))),
        macro("CertSolverSat", integer(summary["solver_verdicts"].get("SAT", 0))),
        macro("CertCliAgreement", integer(summary["cli_agreement"])),
        macro("CertStatusDisagreements", integer(summary["sweep_status_disagreements_with_telemetry"])),
    ]
