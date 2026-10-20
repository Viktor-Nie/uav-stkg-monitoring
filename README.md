# v35 research release

This v35 research release uses reference `human_review_20261019`. The author confirms that A and B completed all nineteen core reviews independently and C confirmed the final core judgments, completed on 2026-10-19 (day precision). Only the merged workbook was recovered in this intake; original independent files were not separately recovered. Hashes establish content integrity, not independent workflow authentication.

The 19 frozen Chinese model inputs, all raw model calls and historical predictions are unchanged. The current reference has five abstract in-scope descriptors and fourteen rejections, exactly matching the previous computational reference on all core fields. Eight Chinese renderings require source-fidelity revision; their proposed replacements remain a separate audit and are not substituted into the model inputs.

All original C physical-context cells P8:P26 remain empty. No C physical applicability or field validation is claimed. Editor technical reference material, if provided separately, is not C judgment. The physical frame compatibility of the five height descriptors remains unresolved.

`research/ablation/gold_reference_19_human_reviewed.csv` is the canonical current reference. Existing `v33` filenames remain compatibility names and do not identify the current reference version. Original historical annotation tables and v34 experiment inputs remain preserved.

The current provenance is in `data/provenance/human_review_20261019_receipt.json`; all-19 and eight-revision source-fidelity tables are in `data/annotation/`. `research/ablation/source_review_19.csv` retains legacy computational explanations separately from human core decisions and corrects the ICAROUS altitude locator to PDF page 5 (printed 27), Section 3.1.

Offline rescoring and statistics outputs are recorded under `outputs/human_review_20261019/`; no new model call, download, training, flight or timing experiment is part of this release. All copied prior `reference_statistics` and historical receipts remain versioned historical evidence.

## Retained v34 documentation (historical status below is superseded by the current receipt)

# Traceable UAV specification and offline monitoring

Research artifacts for *Traceable UAV requirement formalization and offline
monitoring with a knowledge graph*. The parent v34.1 release added the finite-policy proof, conditional language statistics, repeated workload records, raw-source adapters and verified IDF acquisition correction. In this current version, the author has confirmed completed independent A/B core review and C adjudication for the nineteen-item reference, with completion recorded at day precision. The separate source-fidelity audit retains eight required revisions, and original C physical-context cells remain empty.

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
The parent fixed research version is [v34.1](https://github.com/Viktor-Nie/uav-stkg-monitoring/tree/v34.1).
`data/provenance/manuscript_artifact_map.csv` maps manuscript identifiers to
supplied artifacts, current reproduction commands, or explicitly private historical
process records. This release records completed nineteen-item core human review as author-confirmed; source-fidelity revisions and physical applicability remain separate. It does not claim that all manuscript acceptance conditions are complete.

The default annotation driver also validates the current 19-item anonymous A/B/C core exports, canonical four-tuples, source-fidelity counts (11 consistent and 8 requiring revision), and all 19 empty original C physical-context fields. The separate editor notes are in `data/annotation/EDITOR_TECHNICAL_NOTES.md`. Completion at real day precision is accepted; no hour or minute is fabricated.

The v35 default offline reproduction has completed all eleven extensions, including the current nineteen-item human core review validation. Initial direct scoring/statistics validation and subsequent full reproduction are recorded separately in `outputs/human_review_20261019/validation_receipt.json`; `default_full_reproduction_summary.json` records the full result without local machine paths. No model call, download, training, flight or new timing experiment was performed. The validation summaries record the pre-publication testing state. The fixed research version is https://github.com/Viktor-Nie/uav-stkg-monitoring/tree/v35; older release tags remain unchanged.
