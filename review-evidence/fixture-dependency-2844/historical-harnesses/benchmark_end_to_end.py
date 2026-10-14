"""Paired whole-process pytest timings with identical outcome/collection checks."""
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

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--baseline-src", type=Path, required=True)
parser.add_argument("--candidate-src", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--pairs", type=int, default=5)
args = parser.parse_args()
bench = args.output.resolve()
bench.mkdir(parents=True, exist_ok=True)
(bench / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
cached = '''import pytest

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

@pytest.mark.parametrize("case", range(3000))
def test_cached(case, base, left, right, combined):
    assert (base, left, right, combined) == (3, 6, 9, 15)
'''
mixed = '''import pytest

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

@pytest.mark.parametrize("case", range(1500))
def test_mixed(case, base, mode, parent, child):
    assert parent == base + mode
    assert child == [parent]
'''
for name, source in [("cached", cached), ("mixed", mixed)]:
    (bench / f"test_{name}.py").write_text(source, encoding="utf-8")

versions = {"baseline": args.baseline_src.resolve(), "candidate": args.candidate_src.resolve()}

def environment(version):
    env = os.environ.copy()
    env.update(PYTHONPATH=str(versions[version]), PYTEST_DISABLE_PLUGIN_AUTOLOAD="1", PYTHONHASHSEED="0")
    env.pop("PYTEST_ADDOPTS", None)
    env.pop("PYTHONWARNDEFAULTENCODING", None)
    return env

for name, path in versions.items():
    probe = subprocess.run([sys.executable, "-c", "import _pytest.fixtures; print(_pytest.fixtures.__file__)"], env=environment(name), capture_output=True, text=True, check=True)
    assert Path(probe.stdout.strip()).resolve() == path / "_pytest/fixtures.py"

def run(version, workload, label, collect=False):
    command = [sys.executable, "-m", "pytest", "-c", "pytest.ini", "--noconftest", "-p", "no:cacheprovider", "--color=no", "--no-header", "--tb=short", "-q", f"test_{workload}.py"]
    if collect:
        command.append("--collect-only")
    start = time.perf_counter()
    result = subprocess.run(command, cwd=bench, env=environment(version), capture_output=True, text=True, timeout=90)
    elapsed = time.perf_counter() - start
    (bench / f"{workload}-{version}-{label}.log").write_text(result.stdout + result.stderr, encoding="utf-8")
    assert result.returncode == 0, (version, workload, label, result.stdout[-1800:], result.stderr)
    if collect:
        nodes = [line for line in result.stdout.splitlines() if "::" in line]
        assert len(nodes) == 3000
        return hashlib.sha256("\n".join(nodes).encode()).hexdigest()
    assert re.search(r"\b3000 passed\b", result.stdout), result.stdout[-800:]
    return elapsed

report = {"python": sys.version, "pairs": args.pairs, "items_per_workload": 3000, "timing_scope": "entire pytest subprocess including startup and shutdown", "controls": ["same interpreter, packages, test workload and empty config", "external plugin autoload and cache provider disabled", "same ordered nodeids and successful outcomes", "alternating baseline/candidate order"], "workloads": {}}
for workload in ["cached", "mixed"]:
    original = run("baseline", workload, "collection", collect=True)
    changed = run("candidate", workload, "collection", collect=True)
    assert original == changed
    for version in versions:
        run(version, workload, "warmup")
    measurements = []
    for pair in range(args.pairs):
        order = ["baseline", "candidate"] if pair % 2 == 0 else ["candidate", "baseline"]
        times = {version: run(version, workload, f"pair-{pair + 1}") for version in order}
        measurements.append(times)
        print(json.dumps({"workload": workload, "pair": pair + 1, **{k: round(v, 4) for k, v in times.items()}}), flush=True)
    old_median = statistics.median(item["baseline"] for item in measurements)
    new_median = statistics.median(item["candidate"] for item in measurements)
    report["workloads"][workload] = {"ordered_nodeids_sha256": original, "pairs": measurements, "baseline_median_s": old_median, "candidate_median_s": new_median, "change_percent": 100 * (new_median / old_median - 1), "baseline_range_s": [min(x["baseline"] for x in measurements), max(x["baseline"] for x in measurements)], "candidate_range_s": [min(x["candidate"] for x in measurements), max(x["candidate"] for x in measurements)]}
    (bench / "results.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2), flush=True)
