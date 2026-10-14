# Neo4j snapshot and independent graph checks

All executable graph inputs come from `data/graph/nodes.csv`,
`data/graph/relationships.csv`, and `data/graph/bindings.csv`. No local machine
paths, saved credentials or browser authentication states are required.

Run the offline extension reproduction from the repository root:

```text
python -B reproduce_graph_extension.py
```

This reproduces 651 independently scoped structural/context variants (all
rejected), 88 positive/unknown controls (all accepted), and 14 unique N06
numerical-domain configurations (nine invalid rejected, five valid accepted).
It compares CSV outputs byte for byte with the retained reference CSVs and
checks that inputs and evidence remain unchanged. It makes no network requests,
model calls or database writes. The historical 354-variant experiment remains
a separate denominator.

`validation_extension.py` adds declared endpoint types, property types, Boolean
number rejection, Requirement--Formula bijection, single-owner/non-orphan
ParameterBinding checks and same-use execution-context conflict checks. The
historical validator functions in `frozen_validator_reference.py` preserve their
original source text; `frozen_reference_provenance.json` documents the source.
The source validator accepts 434 of the 651 new variants; the extension rejects
those as well. Module safeguards overlap and are not claimed to be independent.

Execution context is distinct from measurement-source context. Explicit
`execution_vehicle_context`, `execution_flight_mode_context`,
`execution_firmware_context`, and `execution_coordinate_frame` values are
compared only across the same use. Missing values and `not_recorded` or
`not_applicable` markers remain unknown. The frozen graph has zero fully known
execution-context matches. `TEST_ONLY_*` values are confined to constructed
variants/controls and are never inserted into the graph snapshot. Passing these
checks does not establish physical applicability, deployment calibration or
vehicle safety.

An actual optional Neo4j import can be performed against a **dedicated local
Neo4j instance** with the optional Neo4j driver dependency. Supply
`NEO4J_URI`, `NEO4J_USER`, and `NEO4J_PASSWORD` through the local environment, then
run:

```text
python -B research/neo4j/import_neo4j_snapshot.py
```

This creates a snapshot label/identifier namespace, imports the frozen graph,
checks repeated-import counts and round-trips every source label, endpoint and
typed property. It never deletes data, resets credentials or saves the password.
Use a separate instance rather than an existing database with incompatible
global ID constraints. Neo4j is optional for the default offline reproduction.
The original monitoring backend continues to read the verified CSV graph.

The retained actual database used Neo4j Community **2026.02.3**, with **158 nodes
and 350 relationships**. `n06_graph.cypher` returns 15 nodes/20 relationships;
`full_graph.cypher` uses `OPTIONAL MATCH` to preserve the isolated
`parameter:height_p95_train` source reference. No ParameterBinding is unowned.
The full and N06 graphs in `native_figures/` are native Neo4j Browser PNG
exports. Their PDF versions are lossless image containers, not vector diagrams;
RGB and alpha channels were verified exactly. The Browser version exposed PNG
export, not SVG export. `browser_style.json` preserves type colors and priority.

The sole added view property is `_display_caption`, derived deterministically
from the original logical ID, role, value and unit. View values use five
significant digits; original source precision and JSON are preserved. The
mapping for all 158 nodes and the final post-export read-only database roundtrip
are retained in `native_display_caption_mapping.json` and
`neo4j_final_after_export_receipt.json`.

The final N06 view was re-exported from the same-version native Windows instance
after Docker Desktop failed to restart. The original Docker database and first
receipt remain retained. Both instances independently match the same 158/350
CSV snapshot. The native Browser uses `n06_native_style.json` (48px fonts) and
`arrange_native_view.js` for fixed presentation coordinates. Those coordinates
change the view only. A normal pointer drag restarts the native layout; the
Browser's own PNG export supplies the unchanged image pixels. Relation numbers
1--8 map respectively to FORMALIZED_AS, USES_TEMPLATE, IMPLEMENTED_BY,
EXECUTED_BY, HAS_PARAMETER_BINDING, BINDS_PARAMETER, APPLIES_TO_SIGNAL,
and READS_SIGNAL. Labels and parameter values in the database remain unchanged.
The complete 158/350 inventory figure retains the earlier verified native
export. Internal IDs and derived display metadata are excluded from comparisons;
every source label, typed property and endpoint remains exactly compared.
