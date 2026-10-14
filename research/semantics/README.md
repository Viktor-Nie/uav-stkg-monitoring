# Finite-observation policy and implementation evidence

`python reproduce_semantics.py --output NEW_DIRECTORY` runs the independent
exact witness enumerator and checks the frozen core on a finite dyadic grid.
It retains nineteen boundary examples, three differences from nominal sampled
STL, and two deliberately characterized floating-point disagreements. A passed
receipt means these expected outcomes are reproduced, not that the floating-point
limitations have been removed.

The four TeX fragments state the exact-arithmetic induction proof and its
comparison-fidelity premise for floating execution. Positive dwell uses an
observed completed-segment policy. Terminal equality is an observed-expiry
reporting convention. Origin subtraction does not guarantee fidelity of all
relative-time or value-threshold arithmetic. Neither the proof nor the finite
checks establish general STL or continuous-time equivalence.

`frozen_v2` retains the earlier core for separate comparison; the current formal
entry remains in `src/uav_stkg/monitor`. No frozen monitoring algorithm, tolerance,
graph value, historical label or experiment output is changed by this check.
