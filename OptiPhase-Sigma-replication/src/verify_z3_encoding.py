"""Check the Z3 encoder against the reference semantics on every case up to MAX_WIDTH bits.

Writes data/telemetry/z3_encoding_agreement.json. Any mismatch makes the run fail, because a refinement proof is only
as sound as the encoding it uses.
"""

import json
import sys

from lib.kernel_registry import REPO_ROOT
from lib.z3_encoding_agreement import run_agreement

MAX_WIDTH = 4
REPORT_PATH = REPO_ROOT / "data" / "telemetry" / "z3_encoding_agreement.json"


def main():
    result = run_agreement(MAX_WIDTH)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"widths 1..{MAX_WIDTH}: cases {result['total_cases']}, mismatches {result['total_mismatches']}")
    return 0 if result["total_mismatches"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
