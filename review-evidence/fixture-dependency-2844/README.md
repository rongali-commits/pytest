# Fixture dependency cache timing evidence

Reviewer utilities for [pytest PR #15177](https://github.com/pytest-dev/pytest/pull/15177), prepared 14 October 2026.

The isolated cached `FixtureDef.execute` measurements were **15–27% slower** with the proposed dependency checks. The two whole-process timing batches are noisy and **inconclusive**. These records establish neither a performance improvement nor zero overhead. A stable benchmark environment is needed to assess the cost precisely.

## Historical measurements

Baseline commit: `c9c19f8e62c12834ad83193a1869cc82fe9c700e`.
The candidate was the reviewed working-tree patch later submitted as commit `0cf8c08a0a10d47a12890a839e152cf0983844ce`. The current candidate is `ea869a278b8cfc6212dad5e343790afe8b754d47` after a commit-metadata update; its source tree remains `36ee241ffc74fe61022e3293aa7495cc38061824` and the reviewed patch is unchanged. The timings below remain historical records.
Reviewed patch SHA-256: `54afc118b882450e3e958120fc7b2e17f353ef3b3067be9816c986ee98571dde`.

The records below are earlier local measurements on Windows with Python 3.12.14. They have not been replaced by a new full-scale run for this package. This package does not report new platform or interpreter coverage.

### Isolated cached method

Five samples of 100,000 calls per version, synthetic request, median call cost:

| Declared dependencies | Baseline | Candidate | Rounded ratio |
| ---: | ---: | ---: | ---: |
| 0 | 1,392 ns | 1,629 ns | 1.17 |
| 1 | 1,641 ns | 1,894 ns | 1.15 |
| 3 | 2,845 ns | 3,626 ns | 1.27 |

`measurements/cached-method.json` preserves the recorded values. The baseline method was extracted from its AST and executed using the candidate module's namespace and a candidate fixture instance. This isolates the changed cached path; it is not a complete comparison of two independent pytest implementations or real application test suites. Each version's five samples were run as a group, not interleaved. The stored record contains medians and rounded ratios, not individual samples.

### Whole pytest subprocess

Each workload contains 3,000 collected items. Each batch has one warmup per version and five timing pairs with alternating execution order. Timings include startup, testing and shutdown.

| Batch/workload | Baseline median | Candidate median | Change |
| --- | ---: | ---: | ---: |
| Initial / cached session diamond | 6.186 s | 7.908 s | +27.84% |
| Initial / mixed scopes and teardown | 3.640 s | 3.626 s | −0.40% |
| Repeat / cached session diamond | 3.220 s | 3.156 s | −1.98% |
| Repeat / mixed scopes and teardown | 4.657 s | 4.820 s | +3.50% |

`measurements/whole-process-initial.json` and `measurements/whole-process-repeat.json` retain every timing pair, medians, ranges and ordered-collection hashes. The cached workload's result changed materially between batches, and individual pair durations varied. There is no confidence interval, calibrated noise threshold or statistical significance claim. Do not interpret the repeat's negative median difference as an improvement.

Both versions used the same interpreter, installed packages, workload and empty pytest config; external plugin autoload and cache-provider plugins were disabled. Successful outcome counts and identical ordered node IDs were checked. Generated version metadata was kept stable and identical in the historical source trees. These synthetic workloads are not a benchmark of the full configured pytest test suite.

## What's in this package

- `measurements/*.json`: historical timing records; measured numbers are unchanged.
- `historical-harnesses/benchmark_cache.py` and `historical-harnesses/benchmark_end_to_end.py`: byte-for-byte copies of the scripts used for those records. They depend on their original relative workspace layout and are included for provenance, not as the portable entry points.
- `benchmark_cached_portable.py`: adaptation with explicit source paths, output path and adjustable call/sample counts.
- `benchmark_whole_process_portable.py`: adaptation with explicit source paths, output path, adjustable item/pair counts, UTF-8 subprocess output and protection against overwriting a non-empty output directory.
- `provenance.json`: hashes linking packaged historical records/scripts to their sources.
- `smoke-validation.json`: small harness checks only, with no performance conclusion.
- `verify_records.py`: independently verifies the historical file hashes and whole-process JSON arithmetic with the standard library.

Only these utilities and evidence files were prepared. The production patch and regression tests were not edited. The small smoke checks validate harness operation, not the statistical quality of the earlier timings.

## Run the portable versions

Use Python and Git in a working directory outside the pytest source tree. These commands create two source worktrees; they do not modify either tracked fixture implementation:

```text
git clone https://github.com/pytest-dev/pytest.git pytest-repository
git -C pytest-repository fetch origin pull/15177/head
git -C pytest-repository worktree add --detach ../pytest-baseline c9c19f8e62c12834ad83193a1869cc82fe9c700e
git -C pytest-repository worktree add --detach ../pytest-candidate ea869a278b8cfc6212dad5e343790afe8b754d47
python -m venv .venv
```

Activate `.venv` using your shell's normal command (`.venv\Scripts\activate` on Windows Command Prompt, `.venv\Scripts\Activate.ps1` on PowerShell, or `source .venv/bin/activate` on macOS/Linux), then install both source trees in the same environment. The final editable install selects the candidate; each portable harness also verifies the explicitly requested imported source.

```text
python -m pip install -e ./pytest-baseline
python -m pip install -e ./pytest-candidate
python -c "from pathlib import Path; import shutil; shutil.copy2(Path('pytest-candidate/src/_pytest/_version.py'), Path('pytest-baseline/src/_pytest/_version.py'))"
```

The last command reproduces the identical generated-version-metadata control. It changes only an ignored generated version file in the baseline worktree; it does not change its fixture implementation. Avoid installs or metadata regeneration while measurements run. The historical measurements used a stable generated file; use a quiet machine and keep the same interpreter/packages for both versions.

From the directory containing these two portable scripts, adjust the source paths if needed:

```text
python benchmark_cached_portable.py --baseline-src pytest-baseline/src --candidate-src pytest-candidate/src --output cached-new.json
python benchmark_whole_process_portable.py --baseline-src pytest-baseline/src --candidate-src pytest-candidate/src --output whole-process-new
```

Default sizes are 100,000 calls × five samples for the isolated method and 3,000 items × five pairs for each whole-process workload. The whole-process output directory must be empty. Repeat on an idle machine and report all batches, including unfavorable results. New outputs are separate records, not replacements for the historical JSON files.

For a quick harness check instead of a performance run:

```text
python benchmark_cached_portable.py --baseline-src pytest-baseline/src --candidate-src pytest-candidate/src --iterations 100 --samples 1 --output cached-smoke.json
python benchmark_whole_process_portable.py --baseline-src pytest-baseline/src --candidate-src pytest-candidate/src --items 8 --pairs 1 --output whole-process-smoke
```

Only these reduced sizes were executed while preparing this package: 100 calls/one sample for each cached-method condition, and eight items/one pair per whole-process workload, plus collection and warmup checks. Both succeeded using the existing Python 3.12.14 environment. No new full-scale benchmark, broad test-suite run or public submission was performed.

`python verify_records.py` verifies the historical record/script hashes and recomputes recorded medians, ranges and percentages. The adapted workloads at their default sizes were also checked to match the original harness's workload text; this is a static equivalence check, not a full-scale run.

## Privacy and limits

The included timing JSON had no local user paths, host names or email values to retain; recorded numbers and relevant interpreter metadata are unchanged. Private working directories, console logs and account snapshots are excluded. Historical harnesses retain only generic relative workspace paths needed to explain their original layout. Fresh full-scale results may differ across operating systems, Python versions, dependencies and host load.
