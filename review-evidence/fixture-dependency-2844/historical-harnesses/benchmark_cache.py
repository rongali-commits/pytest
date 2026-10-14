"""Compare the unchanged and candidate cached execute paths, not end-to-end speed."""
import ast
import __future__
import json
from pathlib import Path
import statistics
import subprocess
import timeit
from types import SimpleNamespace

import _pytest.fixtures as fixtures

root = Path(__file__).resolve().parents[2]
repo = root / "work/day-1/pytest-upstream"
base = "c9c19f8e62c12834ad83193a1869cc82fe9c700e"
source = subprocess.run(["git", "show", f"{base}:src/_pytest/fixtures.py"], cwd=repo, capture_output=True, text=True, check=True).stdout
cls = next(node for node in ast.parse(source).body if isinstance(node, ast.ClassDef) and node.name == "FixtureDef")
method = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == "execute")
namespace = vars(fixtures).copy()
exec(compile(ast.Module(body=[method], type_ignores=[]), "baseline_execute.py", "exec", flags=__future__.annotations.compiler_flag), namespace)
baseline_execute = namespace["execute"]
candidate_execute = fixtures.FixtureDef.execute
results = []
for count in [0, 1, 3]:
    instance = object.__new__(fixtures.FixtureDef)
    instance.argnames = tuple(f"dependency{i}" for i in range(count))
    dependencies = {name: object.__new__(fixtures.FixtureDef) for name in instance.argnames}
    instance._cached_dependencies = list(dependencies.values())
    instance.cached_result = (42, None, None)
    request = SimpleNamespace(_get_active_fixturedef=dependencies.__getitem__)
    assert baseline_execute(instance, request) == candidate_execute(instance, request) == 42
    old = statistics.median(timeit.repeat(lambda: baseline_execute(instance, request), number=100_000, repeat=5))
    new = statistics.median(timeit.repeat(lambda: candidate_execute(instance, request), number=100_000, repeat=5))
    results.append({"dependencies": count, "baseline_ns": round(old * 10_000), "candidate_ns": round(new * 10_000), "ratio": round(new / old, 2)})
result = {"base_commit": base, "iterations_per_sample": 100000, "samples": 5, "scope": "cached execute method with minimal request, not end-to-end pytest", "results": results}
(root / "work/day-2/cache-benchmark.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
print(json.dumps(result, indent=2))
