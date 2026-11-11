# SovPlace — governance-aware placement for data spaces

Reference implementation of the model, the feasibility test, the placement
search, the exact integer program and the experiments of

> *Sovereign by Placement: A Lattice Model for Governance-Aware Deployment of
> Data Spaces in the Edge–Cloud Continuum.*

## Status of this package

Independent implementation written from the definitions in the paper. It
produces the case-study results of the paper (Tables III and IV, Figure 3):
run `scripts/run_cases.py` and `scripts/run_sensitivity.py`; their output is in
`results/`. The scalability experiments of the paper (Figure 4, Table V) were
run with an earlier implementation and other seeds; `scripts/run_scaling.py`
reproduces them in kind, not instance by instance (see `results/scaling.log`).

The data-space cost per boundary data request is one measured value for every
policy level: 0.5 ms at the median and 24.0 ms at the 99th percentile
(`sovplace/model.py`).

## Contents

```
sovplace/model.py         components, hops, functions, node types, parameters (Sec. III)
sovplace/feasibility.py   U_K by union-find, hosts(B), feasibility test, conflict certificate (Sec. IV)
sovplace/cost.py          hop classes, latency, budgets, violations, partition semantics (Sec. III-D, V-A)
sovplace/search.py        Algorithm 1 with incremental evaluation (Sec. V-D)
sovplace/ilp.py           exact integer program over the atoms of U_K, HiGHS via SciPy (Sec. V-C)
sovplace/enumerate.py     enumeration of the admissible region with down-set pruning
sovplace/baselines.py     Practice, Cloud-first, Tech-only
sovplace/cases.py         PV, FLOOD, ED-mono, ED-fed
sovplace/generator.py     synthetic federations (base and hard)
scripts/run_cases.py        Tables III and IV
scripts/run_sensitivity.py  Figure 3
scripts/run_scaling.py      Figure 4 and Table V (--full for the largest sizes)
tests/test_core.py          regression tests
results/                    output of the three scripts
```

## Running

```
pip install -r requirements.txt        # Python 3.10+, NumPy, SciPy (bundles HiGHS)
python3 tests/test_core.py             # 4/4 expected, under 5 s
python3 scripts/run_cases.py           # a few seconds
python3 scripts/run_sensitivity.py     # a few seconds
python3 scripts/run_scaling.py         # a few minutes; --full takes much longer
```

No network access and no data files are needed.

## What the tests establish

* **Theorem 1, independently of its proof.** On 40 random instances the
  feasibility test and exhaustive enumeration give the same answer.
* **Invariant.** Every placement returned by the search is admissible, and the
  incrementally maintained cost equals a full re-evaluation.
* **Exactness of the integer program.** On small instances its optimum equals
  the optimum found by enumerating every admissible partition under every
  allocation; the search never beats it.

## Parameters

`sovplace/model.py` holds the data-space cost per policy level (Table I) and the
assumed round trips and envelopes (Table II). Component demands follow
Section VI-A.

## Limitations

* One resource dimension (cores); node types are elastic, including edge
  gateways (see the paper's threats to validity).
* `enumerate.py` with `optimum=True` tries every allocation of every admissible
  partition and is meant for small instances only; on the case studies the
  optimum is taken from the integer program.
* The enumeration timings in `run_scaling.py` use down-set pruning; the paper's
  Figure 4 reports enumeration of all partitions without pruning.
