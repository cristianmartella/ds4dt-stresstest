"""Regression tests: python3 tests/test_core.py"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from sovplace.generator import generate
from sovplace.feasibility import feasibility, atoms_of
from sovplace.search import search
from sovplace.cost import evaluate
from sovplace.ilp import solve_ilp
from sovplace.enumerate import enumerate_admissible, bell


def test_bell():
    assert bell(14) == 190899322 and bell(18) == 682076806159


def test_feasibility_matches_enumeration():
    """Theorem 1, checked independently: the test agrees with exhaustive search."""
    for seed in range(40):
        inst = generate(9, seed=seed, feasible=False, contract_frac=0.3)
        ok, _, cert = feasibility(inst)
        n_adm = enumerate_admissible(inst)["admissible"]
        assert ok == (n_adm > 0), (seed, ok, n_adm)
        assert ok or cert is not None


def test_incremental_cost_matches_full_evaluation():
    for seed in range(10):
        inst = generate(60, seed=seed)
        st, cert = search(inst)
        assert cert is None
        node_of, type_of = st.component_placement()
        ev = evaluate(inst, node_of, type_of)
        met, W = st.objective()
        assert ev["met"] == met and abs(ev["W"] - W) < 1e-6, seed
        assert ev["violations"] == (0, 0, 0, 0), seed          # invariant: admissible


def test_ilp_matches_enumeration_and_bounds_search():
    for seed in range(12):
        inst = generate(7, seed=seed)
        en = enumerate_admissible(inst, optimum=True, max_alloc=10**6)
        sol = solve_ilp(inst)
        ev = evaluate(inst, sol["node_of"], sol["type_of"])
        assert ev["violations"] == (0, 0, 0, 0)
        assert ev["met"] == en["met"] and abs(ev["W"] - en["W"]) < 1e-6, (seed, ev["W"], en["W"])
        st, _ = search(inst)
        met, W = st.objective()
        assert (met, -W) <= (en["met"], -en["W"] + 1e-6), seed   # search never beats the optimum


if __name__ == "__main__":
    n = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("PASS", name)
            n += 1
    print(f"{n}/{n} passed")
