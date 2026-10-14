# Frozen source consistency and relational parity

Run `python reproduce_historical_audits.py --output NEW_DIRECTORY` from the
repository root. The default offline reproduction also invokes this check.

The source audit reconciles all 84 bindings against the frozen threshold,
runtime and signal catalogs and the original declared generation rules. A
deliberately changed threshold must fail. The relational audit projects the
same complete graph information into typed rows and verifies the same 354
targeted variants with both representations. This establishes decision parity
on the retained suite; it does not establish a graph advantage.

`portability_provenance.json` identifies the original file hashes and complete
function definitions retained from the historical audits. Only imports and
filesystem roots are adapted. Logical source identifiers remain unchanged.
Files under `source_inputs` are read statically for this audit; their historical
training, export or build entry points are not executed. The old semantic
design document is historical provenance. The current finite-observation
policy and its numerical assumptions are stated in the accompanying revision
and the separate semantics evidence.

These checks assess content consistency. They do not certify physical limits,
authenticate human annotation, or validate interpretations of source text.
