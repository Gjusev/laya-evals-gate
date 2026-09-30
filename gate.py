"""laya-evals regression gate: fail the build when accuracy or calibration regresses.

Standalone runner for the laya-evals-gate GitHub Action. The metric logic is
vendored verbatim from laya_evals.baseline (laya-evals v0.1.0, Apache 2.0,
https://github.com/Gjusev/laya-evals) so the gate runs on any runner with
Python 3.10+ and nothing else - no laya, no torch, no network.

Metric specs are PATH:GOAL[:TOLERANCE]: a dotted path into the JSON (keys
containing dots are matched first), goal max (accuracy-like, fails on drops)
or min (ECE-like, fails on rises), tolerance defaults to 0.02. Wall-clock
fields are refused - they drift between runners and only make CI flaky.

Exits 0 pass, 1 regression, 2 usage error.
"""

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from typing import NamedTuple

# ---- vendored from laya_evals/baseline.py (laya-evals v0.1.0) ----

DEFAULT_TOLERANCE = 0.02
DRIFTING_FIELDS = frozenset({"wall_seconds", "decisions_per_second"})


class Metric(NamedTuple):
    path: str
    goal: str = "max"
    tolerance: float = DEFAULT_TOLERANCE


class MetricResult(NamedTuple):
    path: str
    goal: str
    baseline: float
    current: float
    delta: float
    ok: bool


class RegressionCheck(NamedTuple):
    regressed: bool
    results: list

    def summary(self) -> str:
        return "\n".join(
            f"{'OK ' if r.ok else 'REGRESS'} {r.path}: "
            f"{r.baseline:.4f} -> {r.current:.4f} (delta {r.delta:+.4f}, goal {r.goal})"
            for r in self.results
        )


def _resolve(document: Mapping, path: str, source: str) -> float:
    parts = path.split(".")
    node = document
    i = 0
    while i < len(parts):
        for end in range(len(parts), i, -1):
            candidate = ".".join(parts[i:end])
            if isinstance(node, Mapping) and candidate in node:
                node = node[candidate]
                i = end
                break
        else:
            raise ValueError(
                f"{source} is missing {path} (failed at {'.'.join(parts[:i + 1])})"
            )
    if isinstance(node, bool) or not isinstance(node, (int, float)):
        raise ValueError(f"{source} metric {path} is not numeric, got {node!r}")
    return float(node)


def check_regression(current, baseline, metrics: Sequence) -> RegressionCheck:
    if not metrics:
        raise ValueError("at least one metric is required")
    results = []
    for metric in metrics:
        if metric.goal not in ("max", "min"):
            raise ValueError(
                f"metric {metric.path!r}: goal must be 'max' or 'min', got {metric.goal!r}"
            )
        if metric.tolerance < 0:
            raise ValueError(
                f"metric {metric.path!r}: tolerance must be >= 0, got {metric.tolerance}"
            )
        if metric.path.rsplit(".", 1)[-1] in DRIFTING_FIELDS:
            raise ValueError(
                f"metric {metric.path!r}: wall-clock fields drift between "
                "runs and are never gateable"
            )
        current_value = _resolve(current, metric.path, "current report")
        baseline_value = _resolve(baseline, metric.path, "baseline")
        delta = current_value - baseline_value
        ok = (
            delta >= -metric.tolerance if metric.goal == "max" else delta <= metric.tolerance
        )
        results.append(
            MetricResult(metric.path, metric.goal, baseline_value, current_value, delta, ok)
        )
    return RegressionCheck(regressed=any(not r.ok for r in results), results=results)

# ---- end vendored ----


def parse_metric(spec: str) -> Metric:
    parts = spec.split(":")
    if len(parts) not in (2, 3):
        raise ValueError(f"metric spec must be path:goal[:tolerance], got {spec!r}")
    if len(parts) == 3:
        tolerance = float(parts[2])
        if tolerance < 0:
            raise ValueError(f"tolerance must be >= 0, got {spec!r}")
        return Metric(path=parts[0], goal=parts[1], tolerance=tolerance)
    return Metric(path=parts[0], goal=parts[1])


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--current", required=True, help="fresh measurement JSON")
    parser.add_argument("--baseline", required=True, help="committed baseline JSON")
    parser.add_argument("--metric", action="append", required=True,
                        metavar="PATH:GOAL[:TOL]",
                        help="e.g. accuracy_vs_gold:max or ece_15_bins:min:0.01")
    args = parser.parse_args(argv)
    try:
        with open(args.current, encoding="utf-8") as handle:
            current = json.load(handle)
        with open(args.baseline, encoding="utf-8") as handle:
            baseline = json.load(handle)
        metrics = [parse_metric(spec) for spec in args.metric]
        check = check_regression(current, baseline, metrics)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(check.summary())
    return 1 if check.regressed else 0


if __name__ == "__main__":
    sys.exit(main())
