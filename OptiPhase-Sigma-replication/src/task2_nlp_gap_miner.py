"""Task 2: mine limitation sentences from harvested abstracts and map them to clusters G1-G6.

Two tiers are mined from the same abstracts, and the union is written to mined_gaps_1000.csv:
  strict    the 30 patterns in config/gap_regex_patterns.json, applied as shipped (the Gate 2 definition);
  extended  limitation discourse markers plus cluster keyword rules (lib/gap_markers.py), which recover
            limitation sentences the strict patterns cannot express.
Each row keeps the 7 required columns; provenance per row goes to mined_gaps_audit.jsonl. Conclusions
were not available in the harvested metadata, so only abstracts are mined.
"""

import csv
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from lib.gap_markers import COMPILED_BROAD_CLUSTERS, assign_cluster, matched_markers
from lib.gap_patterns import count_patterns, load_gap_patterns
from lib.gap_remediation import REMEDIATION_BY_CLUSTER
from lib.sentence_splitter import split_sentences

REPO_ROOT = Path(__file__).resolve().parent.parent
LITERATURE_DIR = REPO_ROOT / "data" / "literature"
CONFIG_PATH = REPO_ROOT / "config" / "gap_regex_patterns.json"
METADATA_PATH = LITERATURE_DIR / "harvested_metadata.jsonl"
GAPS_PATH = LITERATURE_DIR / "mined_gaps_1000.csv"
STRICT_PATH = LITERATURE_DIR / "mined_gaps_strict.csv"
HIGH_CONFIDENCE_PATH = LITERATURE_DIR / "mined_gaps_high_confidence.csv"
HIGH_CONFIDENCE = ("strict", "refined")
AUDIT_PATH = LITERATURE_DIR / "mined_gaps_audit.jsonl"
SUMMARY_PATH = LITERATURE_DIR / "gap_mining_summary.json"
GAP_CSV_COLUMNS = (
    "gap_id",
    "bibtex_key",
    "year",
    "venue",
    "cluster_id",
    "extracted_limitation_sentence",
    "mathematical_remediation",
)
GATE_MIN_ROWS = 1000
GAP_ID_WIDTH = 5
DOCUMENTED_PATTERN_COUNT = 32
LIMITATIONS = (
    "Only abstracts were mined. Conclusions are not in the harvested metadata, and full text "
    "was not collected.",
    f"config/gap_regex_patterns.json defines {{pattern_count}} patterns, while the design notes "
    f"give {DOCUMENTED_PATTERN_COUNT}; the config was used as shipped for the strict tier.",
    "The extended tier's markers and cluster keywords are a documented heuristic. Its precision is "
    "estimated on a fixed sample and reported in the summary.",
    "mathematical_remediation is the cluster-level remedy for each gap cluster, "
    "not a sentence extracted from any paper.",
)


def log(message):
    timestamp = datetime.now(UTC).strftime("%H:%M:%S")
    print(f"[{timestamp}] {message}", file=sys.stderr, flush=True)


def load_records(path):
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


CONFIDENCE_RANK = {"candidate": 1, "refined": 2, "strict": 3}


def strict_hits(record, patterns):
    """Strict tier: one hit per (sentence, cluster), keeping the first pattern that matched it."""
    first_pattern_by_key = {}
    for sentence in split_sentences(record["abstract"]):
        for pattern in patterns:
            key = (pattern.cluster_id, sentence)
            if key not in first_pattern_by_key and pattern.compiled.search(sentence):
                first_pattern_by_key[key] = pattern.source
    return [
        {"cluster_id": cluster_id, "sentence": sentence, "pattern": source, "tier": "strict",
         "markers": [], "confidence": "strict"}
        for (cluster_id, sentence), source in first_pattern_by_key.items()
    ]


def extended_hits(record):
    """Extended tier: a limitation marker or contrast cue must match, and the sentence needs a cluster.

    Compiler-specific keywords give confidence "refined"; the broader candidate keywords give "candidate".
    """
    hits, seen = [], set()
    for sentence in split_sentences(record["abstract"]):
        markers = matched_markers(sentence)
        if not markers or sentence in seen:
            continue
        refined = assign_cluster(sentence)
        if refined is not None:
            cluster, confidence = refined, "refined"
        else:
            cluster = assign_cluster(sentence, COMPILED_BROAD_CLUSTERS)
            confidence = "candidate"
        if cluster is None:
            continue
        seen.add(sentence)
        hits.append({"cluster_id": cluster, "sentence": sentence, "pattern": None, "tier": "extended",
                     "markers": markers, "confidence": confidence})
    return hits


def merge_tiers(record, strict, extended):
    """One row per (paper, sentence). The most confident hit supplies the cluster and confidence."""
    merged = {}
    for hit in strict + extended:
        key = hit["sentence"]
        current = merged.get(key)
        if current is None:
            current = {"tiers": set()}
            merged[key] = current
        if current.get("confidence") is None or CONFIDENCE_RANK[hit["confidence"]] > CONFIDENCE_RANK[current["confidence"]]:
            current.update(cluster_id=hit["cluster_id"], pattern=hit["pattern"], markers=hit["markers"],
                           confidence=hit["confidence"], sentence=key)
        current["tiers"].add(hit["tier"])
    return [
        {
            "bibtex_key": record["bibtex_key"],
            "year": record["year"],
            "venue": record["venue"],
            "cluster_id": value["cluster_id"],
            "sentence": value["sentence"],
            "tiers": sorted(value["tiers"]),
            "confidence": value["confidence"],
            "pattern": value["pattern"],
            "markers": value["markers"],
            "compiler_topic": bool(record.get("compiler_topic", False)),
        }
        for value in merged.values()
    ]


def mine_all(records, patterns):
    strict_rows, merged_rows = [], []
    for record in records:
        if not record["abstract"]:
            continue
        strict = strict_hits(record, patterns)
        extended = extended_hits(record)
        strict_rows.extend({**hit, "bibtex_key": record["bibtex_key"], "year": record["year"],
                            "venue": record["venue"]} for hit in strict)
        merged_rows.extend(merge_tiers(record, strict, extended))
    key = lambda row: (row["year"], row["bibtex_key"], row["cluster_id"], row["sentence"])  # noqa: E731
    strict_rows.sort(key=key)
    merged_rows.sort(key=key)
    return strict_rows, merged_rows


def build_rows(merged_rows):
    return [
        {
            "gap_id": f"GAP-{index:0{GAP_ID_WIDTH}d}",
            "bibtex_key": row["bibtex_key"],
            "year": row["year"],
            "venue": row["venue"],
            "cluster_id": row["cluster_id"],
            "extracted_limitation_sentence": row["sentence"],
            "mathematical_remediation": REMEDIATION_BY_CLUSTER[row["cluster_id"]],
        }
        for index, row in enumerate(merged_rows, start=1)
    ]


def write_csv(path, rows):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=GAP_CSV_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_audit(path, rows, merged_rows):
    with path.open("w", encoding="utf-8") as handle:
        for gap, row in zip(rows, merged_rows, strict=True):
            audit = {
                "gap_id": gap["gap_id"],
                "tiers": row["tiers"],
                "confidence": row["confidence"],
                "strict_pattern": row["pattern"],
                "extended_markers": row["markers"],
                "compiler_topic": row["compiler_topic"],
            }
            handle.write(json.dumps(audit, ensure_ascii=False) + "\n")


def count_null_fields(rows):
    return sum(1 for row in rows for column in GAP_CSV_COLUMNS if row.get(column) in (None, ""))


def counter_dict(values):
    return dict(sorted(Counter(values).items()))


def build_summary(records, strict_rows, merged_rows, rows, patterns_count, null_fields):
    gate_passed = len(rows) >= GATE_MIN_ROWS and null_fields == 0
    return {
        "generated_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "records_total": len(records),
        "records_with_abstract": sum(1 for record in records if record["abstract"]),
        "abstract_sources": counter_dict(record["abstract_source"] or "none" for record in records),
        "patterns_in_config": patterns_count,
        "strict_tier_rows": len(strict_rows),
        "union_rows": len(rows),
        "rows_tier_strict_only": sum(1 for row in merged_rows if row["tiers"] == ["strict"]),
        "rows_tier_extended_only": sum(1 for row in merged_rows if row["tiers"] == ["extended"]),
        "rows_tier_both": sum(1 for row in merged_rows if row["tiers"] == ["extended", "strict"]),
        "rows_by_confidence": counter_dict(row["confidence"] for row in merged_rows),
        "rows_high_confidence": sum(1 for row in merged_rows if row["confidence"] in HIGH_CONFIDENCE),
        "rows_high_confidence_compiler_topic": sum(
            1 for row in merged_rows if row["confidence"] in HIGH_CONFIDENCE and row["compiler_topic"]
        ),
        "rows_compiler_topic": sum(1 for row in merged_rows if row["compiler_topic"]),
        "rows_by_cluster_compiler_topic": counter_dict(
            row["cluster_id"] for row in merged_rows if row["compiler_topic"]
        ),
        "rows_by_cluster": counter_dict(row["cluster_id"] for row in rows),
        "rows_by_venue": counter_dict(row["venue"] for row in rows),
        "rows_by_year": counter_dict(row["year"] for row in rows),
        "null_fields": null_fields,
        "gate_2": {"required_rows": GATE_MIN_ROWS, "rows": len(rows), "passed": gate_passed},
        "limitations": [text.replace("{pattern_count}", str(patterns_count)) for text in LIMITATIONS],
    }


def main():
    patterns = load_gap_patterns(CONFIG_PATH)
    records = load_records(METADATA_PATH)
    log(f"loaded {len(records)} records; {len(patterns)} strict patterns")
    strict_rows, merged_rows = mine_all(records, patterns)
    rows = build_rows(merged_rows)
    high_rows = [row for row in merged_rows if row["confidence"] in HIGH_CONFIDENCE]
    write_csv(GAPS_PATH, rows)
    write_csv(HIGH_CONFIDENCE_PATH, build_rows(high_rows))
    write_csv(STRICT_PATH, build_rows(strict_rows))
    write_audit(AUDIT_PATH, rows, merged_rows)
    null_fields = count_null_fields(rows)
    summary = build_summary(records, strict_rows, merged_rows, rows, count_patterns(CONFIG_PATH), null_fields)
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    log(f"union rows: {len(rows)} (strict tier {len(strict_rows)}); null fields: {null_fields}; "
        f"gate 2 passed: {summary['gate_2']['passed']}")
    return 0 if summary["gate_2"]["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
