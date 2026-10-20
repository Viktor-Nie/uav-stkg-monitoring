# v35 research release

This v35 research release uses reference `human_review_20261019`. The author confirms that A and B completed all nineteen core reviews independently and C confirmed the final core judgments, completed on 2026-10-19 (day precision). Only the merged workbook was recovered in this intake; original independent files were not separately recovered. Hashes establish content integrity, not independent workflow authentication.

The 19 frozen Chinese model inputs, all raw model calls and historical predictions are unchanged. The current reference has five abstract in-scope descriptors and fourteen rejections, exactly matching the previous computational reference on all core fields. Eight Chinese renderings require source-fidelity revision; their proposed replacements remain a separate audit and are not substituted into the model inputs.

All original C physical-context cells P8:P26 remain empty. No C physical applicability or field validation is claimed. Editor technical reference material, if provided separately, is not C judgment. The physical frame compatibility of the five height descriptors remains unresolved.

`research/ablation/gold_reference_19_human_reviewed.csv` is the canonical current reference. Existing `v33` filenames remain compatibility names and do not identify the current reference version. Original historical annotation tables and v34 experiment inputs remain preserved.

The current provenance is in `data/provenance/human_review_20261019_receipt.json`; all-19 and eight-revision source-fidelity tables are in `data/annotation/`. `research/ablation/source_review_19.csv` retains legacy computational explanations separately from human core decisions and corrects the ICAROUS altitude locator to PDF page 5 (printed 27), Section 3.1.

Offline rescoring and statistics outputs are recorded under `outputs/human_review_20261019/`; no new model call, download, training, flight or timing experiment is part of this release. All copied prior `reference_statistics` and historical receipts remain versioned historical evidence.

## Retained v34 documentation (historical status below is superseded by the current receipt)

# Annotation provenance and current review status

The author reports that two different classmates completed A and B without
seeing each other's decisions, and that a third classmate adjudicated differences
in C. The supplied anonymous historical tables retain the submitted decisions
on nineteen items and the 215-item scope collection. Original-file hashes and
the author's account are recorded in `workflow_provenance.json`. They establish
content provenance and the reported process; hashes do not authenticate that
process independently.

The historical nineteen-item reference has eight supported and eleven unsupported
items. A later computational source reassessment proposes five abstract supported
descriptors and fourteen unsupported items. That reassessment is retained
separately in `research/ablation/source_review_19.csv`. The current same-label reference human_review_20261019 now records completed independent A/B core review and C adjudication as confirmed by the author. Only the merged workbook was received; separate independent original submissions were not recovered. Historical labels, model outputs and scores remain unchanged; reproducing a score does not authenticate the reported independent workflow.

The new review protocol asks A and B to assess all nineteen source statements
independently for scope, signal, template, parameter roles, negation/conditions
and rationale. C then reviews their disagreements against the cited sources.
An abstract height upper bound does not settle its physical reference frame or
provide a deployment-calibrated value. Sustained exceedance detection is not
bounded recovery, and groundspeed is not automatically three-dimensional speed.
Unspecified conditions and values must not be invented.

The nineteen-item historical task includes formula descriptors. The 215-item
collection has scope labels only. `research/annotation/reproduce_annotation.py`
recomputes historical scope agreement and family counts from these six tables;
it neither generates human decisions nor certifies semantic correctness.
