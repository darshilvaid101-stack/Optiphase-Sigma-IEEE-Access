"""Macros for the lowering pilot: how many pass effects on object size survive each lowering level."""

from lib.manuscript_macros import decimal, integer, macro


def mean_absolute(values):
    return sum(abs(value) for value in values) / len(values) if values else 0.0


def sign_flips(cases):
    return sum(
        1 for case in cases
        if case["delta_O0_bytes"] and case["delta_O2_bytes"]
        and (case["delta_O0_bytes"] > 0) != (case["delta_O2_bytes"] > 0)
    )


def lowering_macros(pilot):
    cases = pilot["cases"]
    o0 = [case["delta_O0_bytes"] for case in cases]
    o2 = [case["delta_O2_bytes"] for case in cases]
    return [
        macro("LoweringPilotCases", integer(len(cases))),
        macro("LoweringPilotNonzeroOZero", integer(sum(1 for value in o0 if value))),
        macro("LoweringPilotNonzeroOTwo", integer(sum(1 for value in o2 if value))),
        macro("LoweringPilotMeanAbsOZero", decimal(mean_absolute(o0), 1)),
        macro("LoweringPilotMeanAbsOTwo", decimal(mean_absolute(o2), 1)),
        macro("LoweringPilotSignFlips", integer(sign_flips(cases))),
    ]
