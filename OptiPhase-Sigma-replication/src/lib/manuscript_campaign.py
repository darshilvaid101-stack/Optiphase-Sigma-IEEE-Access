"""Macros for the campaign's failure history, read from the audit log (every attempt is recorded there)."""

import json

from lib.manuscript_macros import integer, macro


def campaign_macros(audit_text):
    attempts = {}
    for line in audit_text.splitlines():
        if line.strip():
            record = json.loads(line)
            attempts.setdefault(record["sweep_id"], []).append(record["status"])
    failed_sweeps = [sweep for sweep, statuses in attempts.items() if "failed" in statuses]
    recovered = [sweep for sweep in failed_sweeps if attempts[sweep][-1] == "ok"]
    return [
        macro("FirstPassFailures", integer(len(failed_sweeps))),
        macro("RecoveredByRerun", integer(len(recovered))),
        macro("UnresolvedFailures", integer(len(failed_sweeps) - len(recovered))),
    ]
