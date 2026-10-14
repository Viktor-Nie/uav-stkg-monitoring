# Traceable UAV specification and offline monitoring

Research artifacts for **Traceable UAV requirement formalization and offline monitoring with a knowledge graph**.

The workflow separates a typed language candidate, an admissible configuration and a verdict on recorded observations. Numerical values are resolved from a frozen catalog through explicit parameter roles. The monitor supports scalar upper-bound invariants and bounded recovery under declared finite-observation contracts.

## Reproduce the frozen results

Use Python 3.11 or later in a fresh environment:

```sh
python -m pip install -r requirements.txt
python reproduce.py --output outputs/reproduction
```

This command does not call a language model, train a model or download data. It validates the supplied graph, re-executes 2,832 decisions on 354 targeted graph variants, checks them against the retained decisions, recomputes the five methods' scope metrics on 215 records and eight source families, rescores the 20 retained controlled language runs and historical methods, redraws three ablation figures, executes the 102/648/600 constructed monitor suites, and checks the new graph constraints. Use a fresh output directory for each run. F1 uses the fixed three-label set, with absent classes contributing zero; family scores receive equal weight.

The historical 19-item language results, source-reviewed reference and new controlled prompt experiments remain separate. Repeated model runs do not increase the number of independent requirements. A passed structural gate does not prove that a candidate correctly interprets its text.

## Artifacts and provenance

- `data/graph/`: the frozen 158-node, 350-relationship graph and 84 role bindings.
- `data/structural_ablation/`: targeted mutations, component decisions and coarse-adjacency ambiguity counts.
- `data/language/`: source pointers, retained predictions and fixed-denominator scores.
- `src/uav_stkg/`: executable configuration checks and monitoring tools.

Source pointers in the graph are logical identifiers retained from the frozen experiment. The release's `data/provenance/source_identifier_index.csv` maps these identifiers to the supplied artifact or upstream acquisition location. Submitted annotation tables are evidence files; their hashes do not by themselves authenticate independent human labeling.

The role-binding test deliberately weakens several kinds of information at once. It is an ambiguity stress test, rather than a single-factor removal of binding nodes. Targeted configuration changes and constructed traces are not additional flight samples.

## Neo4j visualization

The same frozen export can be loaded into an isolated local Neo4j database to inspect its actual nodes, relationships and properties. The canonical N06 neighborhood contains 15 nodes and 20 relationships. Neo4j provides query inspection and visualization; the offline monitor continues to use the verified graph export. Database deployment latency and onboard real-time execution are outside this evaluation.

## External data and limitations

Original flight archives and full third-party document snapshots are obtained from their cited upstream sources. They are not redistributed here. Data references, versions, hashes and acquisition instructions identify the inputs required for optional flight replay. Research reference thresholds have not been physically calibrated for deployment. Recorded observations cannot exclude excursions between samples.

Language-model identity, prompts, output schema and structured experimental outputs are part of the research record. They describe the actual method and are retained for reproducibility. Unrelated local development materials and authentication information are excluded.

The fixed research artifact version is `v33` in [Viktor-Nie/uav-stkg-monitoring](https://github.com/Viktor-Nie/uav-stkg-monitoring/tree/v33). A project-wide public code license has not been assigned.

## Individual offline checks

```sh
python reproduce.py --core-only --output outputs/core_run_001
python reproduce_ablation.py --output outputs/ablation_run_001
python reproduce_monitor.py --output outputs/monitor_run_001
python reproduce_graph_extension.py --output outputs/graph_run_001
```

The ablation driver verifies eight retained CSV results exactly and draws the
structural-module, equal-vocabulary language, and binding-ambiguity figures.
The numeric candidate entry in `research/ablation/validate_candidate.py` checks
the original text before returning catalog bindings; conflicts stop before the
structural gate. Chinese/English number words outside its limited grammar are
refused rather than silently replaced. The historical generation runner remains
archived; this new entry does not overwrite old experiment decisions.

The formal monitor suite includes 102 cases/553 prefixes/24 transformations,
648 cases/16,134 prefixes/12 separate contract controls, and the 600-trace
semantic comparison (436 positive-dwell configurations). These are constructed
tests, not additional flight samples. The default package excludes the four
source-specific replay groups. Their acquisition pointers and frozen
derived-input hashes are in `data/monitor/optional_real_replay_sources.json`;
the release does not promise that downloading a current upstream file will
recreate an old derived CSV without the versioned adapter and profile.

`data/provenance/upstream_document_sources.json` records source snapshot hashes,
versions/access dates, and upstream links. Historical hashes identify the exact
retained input, rather than guaranteeing that a changing website still serves
those bytes. Short curated requirement strings are supplied; full third-party
archives/documents remain upstream. Annotation-table independence is unverified.

The source-reviewed 19-item reference contains five abstract height descriptors
and fourteen unsupported items. Correct scope/tuple selection is distinct from
physical frame alignment; none of these five is certified as an executable AGL,
relative-height, or closest-surface monitor binding. Removing prompt skeletons
loses all positive gate coverage, and all 24 legal semantic-error challenges
pass the structural gate. These limitations are part of the reported results.
