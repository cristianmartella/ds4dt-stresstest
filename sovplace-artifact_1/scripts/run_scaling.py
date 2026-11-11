"""Figure 4 and Table V: scalability and optimality on synthetic federations.

python3 scripts/run_scaling.py [--full]
Default sizes finish in a few minutes; --full adds the largest sizes."""
import json, os, statistics, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from sovplace.generator import generate
from sovplace.feasibility import feasibility
from sovplace.search import search
from sovplace.ilp import solve_ilp
from sovplace.cost import evaluate
from sovplace.enumerate import enumerate_admissible

FULL = "--full" in sys.argv
out = {"feasibility": [], "enumeration": [], "quality": []}

print("== Figure 4: feasibility test vs exhaustive enumeration ==")
for n in [100, 1000, 10_000, 100_000] + ([1_000_000] if FULL else []):
    inst = generate(n, seed=1, feasible=False)
    t0 = time.perf_counter(); ok, _, _ = feasibility(inst); t = (time.perf_counter() - t0) * 1e3
    out["feasibility"].append((n, t, ok))
    print(f"test   n={n:<8} {t:10.2f} ms  feasible={ok}")
agree = total = 0
for n in range(6, 12 if FULL else 11):
    worst = 0.0
    for seed in range(4):
        inst = generate(n, seed=seed, feasible=False, contract_frac=0.3)
        ok, _, _ = feasibility(inst)
        t0 = time.perf_counter(); en = enumerate_admissible(inst); t = (time.perf_counter() - t0) * 1e3
        total += 1
        agree += ok == (en["admissible"] > 0)
        if not ok:
            worst = max(worst, t)
    out["enumeration"].append((n, worst))
    print(f"enum   n={n:<8} {worst:10.2f} ms (worst infeasible instance; down-set pruning on)")
print(f"test and enumeration agree on {agree}/{total} instances")

print("\n== Table V: search against the ILP ==")
print("kind  n      inst  search(s)  ILP(s)   ILP status   dW(%)    dB")
LIMIT = 900.0 if FULL else 120.0
plan = [("base", n, 10) for n in (8, 12, 16, 20)] + [("base", n, 3) for n in (50, 100, 200, 400)]
plan += [("base", 1000, 1), ("hard", 1000, 1)]
if FULL:
    plan += [("base", 2000, 1), ("base", 5000, 1), ("hard", 2000, 1)]
for kind, n, reps in plan:
    ts, ti, dW, dB, status = [], [], [], [], set()
    for seed in range(reps):
        inst = generate(n, seed=seed, hard=(kind == "hard"))
        t0 = time.perf_counter(); st, _ = search(inst); ts.append(time.perf_counter() - t0)
        es = evaluate(inst, *st.component_placement())
        t0 = time.perf_counter(); sol = solve_ilp(inst, time_limit=LIMIT); ti.append(time.perf_counter() - t0)
        ei = evaluate(inst, sol["node_of"], sol["type_of"])
        assert es["violations"] == (0, 0, 0, 0) and ei["violations"] == (0, 0, 0, 0)
        status.add(sol["status"])
        dW.append(100.0 * (es["W"] - ei["W"]) / ei["W"] if ei["W"] else 0.0)
        dB.append(es["met"] - ei["met"])
    row = {"kind": kind, "n": n, "instances": reps, "search_s": statistics.median(ts),
           "ilp_s": statistics.median(ti), "status": sorted(status), "dW_worst": max(dW, key=abs),
           "dB_worst": min(dB)}
    out["quality"].append(row)
    print(f"{kind:5} {n:<6} {reps:<5} {row['search_s']:8.4f}  {row['ilp_s']:7.2f}  "
          f"{'/'.join(row['status']):12} {row['dW_worst']:+7.3f}  {row['dB_worst']:+d}")
print("\n== Search scalability ==")
for kind in ("base", "hard"):
    for n in [1000, 10_000] + ([100_000] if FULL else []):
        inst = generate(n, seed=0, hard=(kind == "hard"))
        t0 = time.perf_counter(); st, _ = search(inst); t = time.perf_counter() - t0
        out.setdefault("search", []).append((kind, n, t))
        print(f"{kind:5} n={n:<7} {t:8.2f} s")
os.makedirs("results", exist_ok=True)
json.dump(out, open("results/scaling.json", "w"), indent=1)
