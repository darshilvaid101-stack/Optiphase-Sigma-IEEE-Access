"""Apply the block-local Z3 refinement check across a canonical listing and an optimized listing.

Blocks are matched by function name and block label. A block pair is compared only when both are
encodable and their live-ins agree; everything else is counted, never silently dropped.
"""

from lib.telemetry_metrics import defined_functions
from lib.z3_validator import (
    NotEncodable,
    STATUS_REFINES,
    STATUS_UNKNOWN,
    STATUS_VIOLATED,
    blocks_of_function,
    check_refinement,
)

STATUS_NOT_COMPARABLE = "NOT_COMPARABLE"
COUNTER_BY_NAME_STATUS = {
    STATUS_REFINES: "names_refines",
    STATUS_VIOLATED: "names_violated",
    STATUS_UNKNOWN: "names_unknown",
}


def empty_summary():
    return {
        "blocks_matched": 0,
        "blocks_compared": 0,
        "blocks_not_encodable": 0,
        "names_refines": 0,
        "names_violated": 0,
        "names_unknown": 0,
    }


def compare_block_pair(canonical_block, optimized_block, timeout_ms, summary):
    summary["blocks_matched"] += 1
    try:
        statuses, _ = check_refinement(canonical_block, optimized_block, timeout_ms)
    except NotEncodable:
        summary["blocks_not_encodable"] += 1
        return
    summary["blocks_compared"] += 1
    for status in statuses.values():
        summary[COUNTER_BY_NAME_STATUS[status]] += 1


def validate_listings(canonical_listing, optimized_listing, timeout_ms):
    """Return the summary counts for every function present in both listings."""
    summary = empty_summary()
    shared_functions = set(defined_functions(canonical_listing)) & set(defined_functions(optimized_listing))
    for function_name in sorted(shared_functions):
        canonical_blocks = {block.label: block for block in blocks_of_function(canonical_listing, function_name)}
        optimized_blocks = {block.label: block for block in blocks_of_function(optimized_listing, function_name)}
        for label in sorted(canonical_blocks.keys() & optimized_blocks.keys()):
            compare_block_pair(canonical_blocks[label], optimized_blocks[label], timeout_ms, summary)
    return summary


def sweep_status(summary):
    """Collapse the counts into one status: any refutation wins, then any timeout, then full refinement."""
    if summary["names_violated"]:
        return STATUS_VIOLATED
    if summary["names_unknown"]:
        return STATUS_UNKNOWN
    if summary["names_refines"]:
        return STATUS_REFINES
    return STATUS_NOT_COMPARABLE
