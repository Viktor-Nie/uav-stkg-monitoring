# Traceable UAV specification and offline monitoring

Research artifacts for *Traceable UAV requirement formalization and offline
monitoring with a knowledge graph*. This v34.1 research version adds the finite-policy
proof, conditional language statistics, complete repeated workload records,
raw-source adapters, and a verified IDF acquisition correction. Renewed human
review of the nineteen source-corrected labels remains pending. Reproducing their
provisional scores does not turn them into a new human-adjudicated gold standard.

## Default offline reproduction

Use Python 3.11 or later with the pinned scientific packages:

```sh
python -m pip install -r requirements.txt
python reproduce.py --output outputs/reproduction_001
```

Use a new output directory. This path makes no model call, performs no training,
and downloads nothing. It reconstructs the 2,832 decisions on 354 graph variants;
recomputes English scores on 215 strings/eight source families; rescores the
retained nineteen-item historical outputs and twenty controlled prompt contexts;
redraws ablation figures; executes the 102/648/600 constructed monitor suites;
checks the graph-constraint extensions and numeric conflicts; reruns relational
parity and the 84-binding source audit; checks 24 finite-screen records/six
refusal probes; runs the exact finite semantics checks and counterexamples;
recalculates historical annotation agreement and conditional language intervals;
verifies all nine complete workload records; checks HIL source composition; and
independently replays the three supplied verified IDF native streams plus speed.

The default workload step recomputes medians/quartiles from 45 actual timings,
18 warm-ups and nine allocation passes. It does not repeat the timing experiment.
The HIL default verifies the previously executed raw-reconstruction receipt and
composition, rather than claiming to recompute quantiles without telemetry.
The complete raw-HIL and four-source commands below provide that separate path.

```sh
python reproduce.py --core-only --output outputs/core_001
python reproduce_historical_audits.py --output outputs/source_parity_001
python reproduce_semantics.py --output outputs/semantics_001
python reproduce_idf_verified.py --output outputs/idf_001
python research/statistics_performance/performance.py --output outputs/new_timings_001
```

The last command is explicitly opt-in and runs the full nine-cell workload;
desktop batch cost is not onboard latency. Six original complete cells and three
later complete cells form the retained run, with both clock periods and ambient
load disclosed. Original 60-second partial results remain separately identified.

## Optional raw-source reproduction

Install `requirements-replay.txt` for the existing source-specific adapter
dependencies. `research/real_replay/SOURCE_INPUTS.md` specifies exact archive
versions, member identities, hashes, upstream links and preparation commands.
The raw entry points import only this package and never import an external
historical workspace as executable code.

```sh
python research/threshold_reproduction/reproduce_thresholds.py --raw-state-root EXTERNAL_HIL_ROOT --reference-split research/threshold_reproduction/frozen_case_split.csv --workers 1 --output outputs/hil_raw_001
python research/real_replay/reproduce_real_replays.py --input-root EXTERNAL_MATERIALS_ROOT --output outputs/raw_replay_001
```

The actual full HIL reconstruction covers 2,613 cases/201,026 endpoint windows,
including 141,508 training windows. Seven consumed columns, the split and the
executed quantile CSV match exactly. Normal cases contribute 8,296 training
windows; fault-type missions contribute 133,212, including pre-injection periods.
These are mixed research reference quantiles, not certified healthy safety limits.

The four replay groups retain 68 formula--trace evaluations and 28,210 event
rows. RflyMAD has three correlated logs and nine distinct configurations per
log; its 20-Hz held-grid adapter is separate from the native single-signal
profiles. No event count is an independent flight or labeled fault sample count.

Re-acquiring IDF_DS v1.0 uncovered two truncated historical CSV tails. The
complete official inputs add ten native observations (25,773 to 25,783), changing
no configuration verdict or event row. Three verified complete members are
supplied under the record's CC BY 4.0 license, with author attribution in
`data/external/idf_ds_lap120_verified_v34/ATTRIBUTION.md`. `historical_v33` is a
separate explicit profile that reconstructs the old byte prefixes for regression.
Other upstream archives and full third-party document snapshots stay upstream.

## Interpretation boundaries

The graph contains 158 nodes, 350 relationships and 84 parameter bindings.
Neo4j provides actual materialization and native display (N06: 15 nodes/20
relationships); the CSV runtime remains. Source pointers are resolved through
`data/provenance/source_identifier_index.csv` and source-specific manifests.

The author reports that distinct classmates A and B independently annotated the
historical tables and a third classmate C adjudicated differences. Anonymous
decisions and the reported process are in `data/annotation`. File hashes do not
independently authenticate that process. The new nineteen-label review is pending;
original labels, computational revisions and retained predictions remain separate.

Conditional resampling describes empirical source-family/context reweighting;
it is not population inference. Repeats do not increase the number of unique
requirements. All 24 legal semantic-error challenges pass the structural gate,
so compatibility does not prove correct interpretation. The binding-adjacency
comparison weakens multiple safeguards and remains an ambiguity stress test.

The FIFO proof concerns the declared completed-segment reporting policy under
exact arithmetic or comparison fidelity. Positive dwell is not a general sampled
STL expansion. Terminal equality and two floating-point counterexamples are
explicitly retained. Recorded data do not establish continuous physical safety,
height-frame compatibility, threshold calibration or airborne execution.

LLM model settings, necessary prompts, schemas and structured outputs are part
of the actual research method and remain supplied. Unrelated writing-process
materials, local development history, local machine paths and credentials are
excluded. A project-wide code license has not been assigned; the separately
identified IDF source files retain their CC BY 4.0 terms.

The prior sealed research release remains [v33](https://github.com/Viktor-Nie/uav-stkg-monitoring/tree/v33).
The fixed research version is [v34.1](https://github.com/Viktor-Nie/uav-stkg-monitoring/tree/v34.1).
`data/provenance/manuscript_artifact_map.csv` maps manuscript identifiers to
supplied artifacts, current reproduction commands, or explicitly private historical
process records. This research version preserves the pending nineteen-label human
review; it is not a claim that all manuscript acceptance conditions are complete.
