"""Verify this package's historical file hashes and recorded JSON arithmetic."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import statistics


root = Path(__file__).resolve().parent
provenance = json.loads((root / "provenance.json").read_text(encoding="utf-8"))
for record in provenance["historical_records"]:
    path = (root / record["packaged_file"]).resolve()
    if not path.is_relative_to(root):
        raise ValueError("Manifest path escapes evidence directory")
    raw = path.read_bytes()
    assert len(raw) == record["bytes"]
    assert hashlib.sha256(raw).hexdigest() == record["sha256"]
    if path.suffix != ".json":
        continue
    data = json.loads(raw)
    for workload in data.get("workloads", {}).values():
        baseline = [pair["baseline"] for pair in workload["pairs"]]
        candidate = [pair["candidate"] for pair in workload["pairs"]]
        old = statistics.median(baseline)
        new = statistics.median(candidate)
        assert old == workload["baseline_median_s"]
        assert new == workload["candidate_median_s"]
        assert 100 * (new / old - 1) == workload["change_percent"]
        assert [min(baseline), max(baseline)] == workload["baseline_range_s"]
        assert [min(candidate), max(candidate)] == workload["candidate_range_s"]
print("Five historical file hashes and all recorded whole-process arithmetic verified.")
