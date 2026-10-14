# Conditional language uncertainty and complete desktop workloads

This directory adds two offline analyses for v34. It does not call a model,
train a model, acquire flight data, or claim independent human verification.

Run the light language analysis from any working directory:

```powershell
python -B -X utf8 research/statistics_performance/conditional_statistics.py --output outputs/conditional_statistics
```

The output directory must be new. `receipt.json` reports `status: passed` only
after verifying the eight-family English scores and re-scoring all 380 saved
Chinese output rows. Seed 2026101404 and 20,000 resamples are fixed. The
reference result is in `reference_statistics`. Intervals describe empirical
family/context reweighting, conditional on these documents, saved calls and
the provisional reference. They are not population confidence intervals.
Repeated contexts do not create additional independent texts. Publisher and
training-fold overlap, the five-context limit, and reference uncertainty are
explicit limitations. The three Chinese interval variants, all paired
contrasts, draw indices, and family/context count vectors are retained.

`main_statistics_insert.tex` and `supplementary_statistics_insert.tex` provide
editable manuscript text. The two generated row files are in
`reference_statistics`. `reference_plot` contains the PDF/PNG contrasts plot;
`plot_intervals.py` redraws that plot from saved interval rows without resampling.

The formal performance experiment is an explicit, potentially long command:

```powershell
python -B -X utf8 research/statistics_performance/performance.py --output outputs/complete_performance
```

Run it in a coordinated CPU window. It executes nine cells serially, ordered
by 1,000/10,000/100,000 samples then quiescent/sparse/dense pattern. Every cell
receives two warmups, five timings without tracemalloc, and one separate
allocation pass. The fixed maximum is 7,200 seconds for the whole cell,
including startup and allocation. All partial records and failures are kept;
the program never substitutes old timings or reports a five-run median for
an incomplete cell. `--smoke` is only a 1,000-point interface check with one
warmup and one timing and cannot produce a formal reference result.

The workload CSVs are byte copies of the original constructed inputs. The
24 graph-bound parameter specifications are checked for exact numerical
equality with the original bound specifications before running. The frozen
core is copied from the v34 candidate precision-aware production entry;
the monitoring algorithm is unchanged. Explicit graph-directory arguments
adapt paths without changing its implementation. `frozen_configuration.json`
binds the input/core hashes. This is a new run of the current entry and
environment, so differences from the historical v2 timings cannot be read
as algorithmic speedups.

Timing includes CSV parsing, graph-bound replay of all 24 formulas, and summary
CSV serialization. Full ledger serialization, telemetry and actuation are
excluded. The separate tracemalloc peak measures Python allocation, not RSS.
Working-set snapshots and total-system CPU samples are retained separately;
ambient OS/application activity is not assumed absent. `environment.json`
records the actual Python/package/Windows/CPU configuration and thread-related
environment variables. Results describe ground desktop offline batch cost,
not aircraft real-time latency or new physical coverage.

The default reproduction path must use the light verifier after the complete
reference records have been retained:

```powershell
python -B -X utf8 research/statistics_performance/verify_performance.py --output outputs/performance_verification
```

It verifies 18 warmups, 45 timings, nine allocation passes, all count signatures,
the source/configuration hashes, and recalculated medians, quartiles and ranges.
It performs zero timing runs. `reference_performance` is populated only from
the completed formal execution, and smoke or historical partial records are
explicitly rejected.

`historical_60s_budget` preserves the earlier partial timings. Only the public
copy of its environment's local `executable` path is redacted; the processor,
Windows, Python and package fields remain. `portable_redaction.json` records
both original and portable SHA-256 values. This file is a declared portable
copy, not the original bytes; original bytes remain in the private audit and
the unchanged earlier experiment.
