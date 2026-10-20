"""Load the cluster-tagged contrastive regex patterns that flag limitation sentences."""

import json
import re
from dataclasses import dataclass
from pathlib import Path

WORD_BOUNDARY = r"\b"


@dataclass(frozen=True)
class GapPattern:
    """One compiled limitation pattern and the structural cluster it evidences."""

    cluster_id: str
    cluster_name: str
    source: str
    compiled: re.Pattern


def load_gap_patterns(config_path):
    """Compile every pattern in the config; word boundaries stop short tokens such as UB matching inside words."""
    config = json.loads(Path(config_path).read_text(encoding="utf-8"))
    patterns = []
    for cluster_id, cluster in config["clusters"].items():
        for source in cluster["patterns"]:
            compiled = re.compile(WORD_BOUNDARY + source + WORD_BOUNDARY, re.IGNORECASE)
            patterns.append(GapPattern(cluster_id, cluster["name"], source, compiled))
    return patterns


def count_patterns(config_path):
    config = json.loads(Path(config_path).read_text(encoding="utf-8"))
    return sum(len(cluster["patterns"]) for cluster in config["clusters"].values())
