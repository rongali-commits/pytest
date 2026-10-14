"""Portable adaptation of the historical cached FixtureDef.execute microbenchmark.

This measures an isolated cached method with a synthetic request, not pytest's
whole-process speed. Use corresponding baseline/candidate source checkouts.
"""
from __future__ import annotations

import __future__
import argparse
import ast
import json
from pathlib import Path
import statistics
import sys
import timeit
from types import SimpleNamespace


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-src", type=Path, required=True)
    parser.add_argument("--candidate-src", type=Path, required=True)
    parser.add_argument("--iterations", type=int, default=100_000)
    parser.add_argument("--samples", type=int, default=5)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.iterations < 1 or args.samples < 1:
        parser.error("iterations and samples must be positive")

    baseline = args.baseline_src.resolve()
    candidate = args.candidate_src.resolve()
    sys.path.insert(0, str(candidate))
    import _pytest.fixtures as fixtures

    if Path(fixtures.__file__).resolve() != candidate / "_pytest" / "fixtures.py":
        raise RuntimeError("Imported fixture module is not the requested candidate source")
    source = (baseline / "_pytest" / "fixtures.py").read_text(encoding="utf-8")
    fixture_class = next(
        node for node in ast.parse(source).body
        if isinstance(node, ast.ClassDef) and node.name == "FixtureDef"
    )
    method = next(
        node for node in fixture_class.body
        if isinstance(node, ast.FunctionDef) and node.name == "execute"
    )
    namespace = vars(fixtures).copy()
    exec(
        compile(
            ast.Module(body=[method], type_ignores=[]),
            "baseline_execute.py",
            "exec",
            flags=__future__.annotations.compiler_flag,
        ),
        namespace,
    )
    baseline_execute = namespace["execute"]
    candidate_execute = fixtures.FixtureDef.execute
    results = []
    for count in [0, 1, 3]:
        instance = object.__new__(fixtures.FixtureDef)
        instance.argnames = tuple(f"dependency{i}" for i in range(count))
        dependencies = {
            name: object.__new__(fixtures.FixtureDef) for name in instance.argnames
        }
        instance._cached_dependencies = list(dependencies.values())
        instance.cached_result = (42, None, None)
        request = SimpleNamespace(_get_active_fixturedef=dependencies.__getitem__)
        assert baseline_execute(instance, request) == candidate_execute(instance, request) == 42
        old = statistics.median(timeit.repeat(
            lambda: baseline_execute(instance, request),
            number=args.iterations, repeat=args.samples,
        ))
        new = statistics.median(timeit.repeat(
            lambda: candidate_execute(instance, request),
            number=args.iterations, repeat=args.samples,
        ))
        results.append({
            "dependencies": count,
            "baseline_ns": round(old / args.iterations * 1_000_000_000),
            "candidate_ns": round(new / args.iterations * 1_000_000_000),
            "ratio": round(new / old, 2),
        })
    report = {
        "harness": "portable adaptation; this output is a new invocation",
        "iterations_per_sample": args.iterations,
        "samples": args.samples,
        "scope": "cached execute method with minimal request, not end-to-end pytest",
        "results": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
