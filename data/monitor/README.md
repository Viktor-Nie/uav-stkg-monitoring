# Frozen constructed monitor inputs

Run from the candidate repository root:

```text
python -B reproduce_monitor.py --output outputs/monitor_run_001
```

The output directory must be new. The run is offline and uses the formal
`uav_stkg.monitor.sampled_monitor` entry, not original-workspace imports or
precomputed monitor verdicts. It recomputes complete signatures, all eligible
prefixes and transformations from the bundled timestamp/value inputs. Frozen
expectations and independently executed reference algorithms are compared.

| Independent set | Included inputs and required comparisons |
|---|---|
| E5 numerical stress | 102 cases, 553 prefixes, 24 transformations; 12 original authored trace JSONs retain exact source bytes and their original hashes |
| Factorial numerical boundaries | 648 cases, 16,134 eligible prefixes, 12 separately counted invalid-contract controls |
| Local semantic comparison | 600 existing traces: 300 fixed-rate and 300 native-event-time; 436 positive-dwell configurations |

These are constructed computational inputs. They are not new flights, language
data, independently annotated gold labels or independent physical deployment
validation. Each denominator stays separate. Historical absolute-float failures
remain in the study's frozen archive; formal precision-aware outcomes are new
regression results on the same constructed inputs. The 600-row file is the
manuscript's `v4_semantic_differential_traces.csv`, not the separate historical
600-row variant with 431 positive-dwell configurations.

The two Decimal oracles are independently rescanned future-witness algorithms.
The 600-trace reference is a separate independent float future scan. None
imports the production FIFO monitor, predicates, input audit or adapter. Original
fixture hashes are checked before execution by `input_manifest.json`.

For interface and old-caller regression tests, with `src` on Python's path:

```text
python -B -m unittest uav_stkg.monitor.test_timestamp_precision uav_stkg.monitor.test_legacy_api_compatibility -v
```

The exact timestamp entry accepts string/Decimal seconds or exact integer ticks
with an explicit decimal seconds-per-tick scale. Decimal origin subtraction
precedes float conversion; source origin and exact event-coordinate mapping are
retained. Old callers passing floats keep the legacy absolute-time behaviour
and are explicitly marked as lacking recoverable original source precision.
Finite relative-span float rounding is still possible. No threshold, tolerance,
deadline, dwell or expiration--recovery--trigger order is changed.

The candidate does not redistribute raw flight archives, public document
snapshots or the four retained source replay groups. Their
original per-source conditions are separate from the constructed fixtures.
The local full-workspace integration has separately compared all 28,210
historical event rows. This default standalone command does not claim to replay
those unavailable real-source streams or download them automatically.

Source ownership and a public code/input license remain a release decision.
This local package has not been uploaded or declared publicly available.
