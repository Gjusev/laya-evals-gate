# laya-evals regression gate

Fail the build when **accuracy drops or calibration worsens**. Compare a fresh
measurement JSON against a committed baseline; any metric outside its
tolerance fails the step.

Pure Python 3 on the runner: no model downloads, no `laya`, no `torch`. The
metric logic is vendored from
[laya-evals](https://github.com/Gjusev/laya-evals) (Apache 2.0), the
calibration-first evaluation toolkit for
[laya](https://github.com/NandhaKishorM/laya).

## Usage

```yaml
- uses: gjusev/laya-evals-gate@v1
  with:
    current: results/current.json
    baseline: results/baselines/current.json
    metrics: |
      accuracy_vs_gold:max
      ece_15_bins:min:0.01
```

Metric specs are `path:goal[:tolerance]`:

- `path` - a dotted path into the JSON; keys containing dots (like
  `suites.xnli.en` stored as one key) are matched first.
- `goal` - `max` for accuracy-like metrics (fails on drops beyond
  tolerance), `min` for error-like metrics such as ECE (fails on rises).
- `tolerance` - defaults to `0.02`.

The step exits non-zero on regression and sets a `regressed` output. Re-run
the same gate locally with the
[`check_regression.py` CLI](https://github.com/Gjusev/laya-evals/blob/main/scripts/check_regression.py)
or `pip install laya-evals` and `from laya_evals import check_regression`.

## What it will not gate

Wall-clock and throughput fields (`wall_seconds`, `decisions_per_second`)
are rejected outright: they drift between runners and would only make CI
flaky. Accuracy held on the same data is what matters.

## Example workflow

```yaml
name: evals
on:
  push:
    branches: [main]
  pull_request:
  workflow_dispatch:

jobs:
  tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install -e ".[dev]" && pytest   # your eval suite

  regression-gate:
    if: github.event_name == 'workflow_dispatch'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: python produce_measurement.py --out results/current.json
      - uses: gjusev/laya-evals-gate@v1
        with:
          current: results/current.json
          baseline: results/baselines/current.json
          metrics: |
            accuracy_vs_gold:max
            ece_15_bins:min
```

Re-baseline after an accepted change by copying the fresh artifact over the
baseline file and committing it.

## License

Apache 2.0. The gate logic originates from
[laya-evals](https://github.com/Gjusev/laya-evals), an unofficial community
companion to laya.
