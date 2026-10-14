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
separately in `research/ablation/source_review_19.csv`. Its corrected labels have
not yet been independently reviewed by the classmates. Historical labels, model
outputs and scores are retained unchanged, and the provisional rescoring does not
become an independently adjudicated gold standard by being reproduced.

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
