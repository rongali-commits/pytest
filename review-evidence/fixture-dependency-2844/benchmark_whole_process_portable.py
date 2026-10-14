"""Portable adaptation of paired whole-process pytest timing workloads.

The default 3,000 items/five pairs match the historical workload sizes. Smaller
explicit values are for harness smoke checks, not comparable performance data.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import statistics
import subprocess
import sys
import time


CACHED = '''import pytest

@pytest.fixture(scope="session")
def base():
    return 3

@pytest.fixture(scope="session")
def left(base):
    return base * 2

@pytest.fixture(scope="session")
def right(base):
    return base * 3

@pytest.fixture(scope="session")
def combined(request, left, right):
    return left + right

@pytest.mark.parametrize("case", range(ITEM_COUNT))
def test_cached(case, base, left, right, combined):
    assert (base, left, right, combined) == (3, 6, 9, 15)
'''
MIXED = '''import pytest

@pytest.fixture(scope="session")
def base():
    return 3

@pytest.fixture(scope="module", params=[0, 1])
def mode(request):
    return request.param

@pytest.fixture(scope="module")
def parent(base, mode):
    yield base + mode

@pytest.fixture
def child(request, parent):
    value = [parent]
    yield value
    assert value == [parent]
    value.clear()

@pytest.mark.parametrize("case", range(ITEM_COUNT))
def test_mixed(case, base, mode, parent, child):
    assert parent == base + mode
    assert child == [parent]
'''


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-src", type=Path, required=True)
    parser.add_argument("--candidate-src", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--pairs", type=int, default=5)
    parser.add_argument("--items", type=int, default=3000)
    parser.add_argument("--timeout", type=float, default=90)
    args = parser.parse_args()
    if args.pairs < 1 or args.items < 2 or args.items % 2 or args.timeout <= 0:
        parser.error("pairs/timeout must be positive; items must be positive, even and at least 2")
    bench = args.output.resolve()
    bench.mkdir(parents=True, exist_ok=True)
    if any(bench.iterdir()):
        parser.error("output directory must be empty to protect existing files")
    (bench / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    (bench / "test_cached.py").write_text(
        CACHED.replace("ITEM_COUNT", str(args.items)), encoding="utf-8"
    )
    (bench / "test_mixed.py").write_text(
        MIXED.replace("ITEM_COUNT", str(args.items // 2)), encoding="utf-8"
    )
    versions = {
        "baseline": args.baseline_src.resolve(),
        "candidate": args.candidate_src.resolve(),
    }

    def environment(version: str) -> dict[str, str]:
        env = os.environ.copy()
        env.update(
            PYTHONPATH=str(versions[version]),
            PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",
            PYTHONHASHSEED="0",
            PYTHONIOENCODING="utf-8",
        )
        env.pop("PYTEST_ADDOPTS", None)
        env.pop("PYTHONWARNDEFAULTENCODING", None)
        return env

    for version, path in versions.items():
        probe = subprocess.run(
            [sys.executable, "-c", "import _pytest.fixtures; print(_pytest.fixtures.__file__)"],
            env=environment(version), capture_output=True, text=True,
            encoding="utf-8", check=True, timeout=args.timeout,
        )
        if Path(probe.stdout.strip()).resolve() != path / "_pytest" / "fixtures.py":
            raise RuntimeError("Imported fixture module is not the requested source")

    def run(version: str, workload: str, label: str, collect: bool = False):
        command = [
            sys.executable, "-m", "pytest", "-c", "pytest.ini", "--noconftest",
            "-p", "no:cacheprovider", "--color=no", "--no-header", "--tb=short",
            "-q", f"test_{workload}.py",
        ]
        if collect:
            command.append("--collect-only")
        start = time.perf_counter()
        result = subprocess.run(
            command, cwd=bench, env=environment(version), capture_output=True,
            text=True, encoding="utf-8", timeout=args.timeout,
        )
        elapsed = time.perf_counter() - start
        (bench / f"{workload}-{version}-{label}.log").write_text(
            result.stdout + result.stderr, encoding="utf-8"
        )
        if result.returncode:
            raise RuntimeError(f"{version}/{workload}/{label} failed; inspect its output log")
        if collect:
            nodes = [line for line in result.stdout.splitlines() if "::" in line]
            if len(nodes) != args.items:
                raise RuntimeError("Unexpected collection count")
            return hashlib.sha256("\n".join(nodes).encode()).hexdigest()
        if not re.search(rf"\b{args.items} passed\b", result.stdout):
            raise RuntimeError("Expected passing outcome count missing")
        return elapsed

    report = {
        "harness": "portable adaptation; this output is a new invocation",
        "python": sys.version,
        "pairs": args.pairs,
        "items_per_workload": args.items,
        "timing_scope": "entire pytest subprocess including startup and shutdown",
        "controls": [
            "same interpreter, packages, test workload and empty config",
            "external plugin autoload and cache provider disabled",
            "same ordered nodeids and successful outcomes",
            "alternating baseline/candidate order",
        ],
        "workloads": {},
    }
    for workload in ["cached", "mixed"]:
        original = run("baseline", workload, "collection", collect=True)
        changed = run("candidate", workload, "collection", collect=True)
        if original != changed:
            raise RuntimeError("Ordered collection differs between versions")
        for version in versions:
            run(version, workload, "warmup")
        measurements = []
        for pair in range(args.pairs):
            order = ["baseline", "candidate"] if pair % 2 == 0 else ["candidate", "baseline"]
            times = {version: run(version, workload, f"pair-{pair + 1}") for version in order}
            measurements.append(times)
            print(json.dumps({"workload": workload, "pair": pair + 1, **times}), flush=True)
        old = statistics.median(item["baseline"] for item in measurements)
        new = statistics.median(item["candidate"] for item in measurements)
        report["workloads"][workload] = {
            "ordered_nodeids_sha256": original,
            "pairs": measurements,
            "baseline_median_s": old,
            "candidate_median_s": new,
            "change_percent": 100 * (new / old - 1),
            "baseline_range_s": [
                min(x["baseline"] for x in measurements),
                max(x["baseline"] for x in measurements),
            ],
            "candidate_range_s": [
                min(x["candidate"] for x in measurements),
                max(x["candidate"] for x in measurements),
            ],
        }
        (bench / "results.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()
