"""Tables III and IV: python3 scripts/run_cases.py"""
import json, os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from sovplace import cases, baselines
from sovplace.feasibility import feasibility
from sovplace.search import search
from sovplace.ilp import solve_ilp
from sovplace.cost import evaluate
from sovplace.enumerate import enumerate_admissible, bell

out = {}
print("== Table III: case studies ==")
print(f"{'case':8} |C| |P| |F| K t/c/d  |U_K|  Bell(|C|)  Bell(|U_K|)  |A|     prefixes  test(ms) enum(s)")
for name, make in cases.ALL.items():
    inst = make()
    t0 = time.perf_counter()
    ok, atoms, cert = feasibility(inst)
    t_test = (time.perf_counter() - t0) * 1e3
    kc = [sum(1 for k in inst.K if k[2] == x) for x in ("tech", "contract", "degr")]
    row = {"C": len(inst.components), "P": len(inst.participants), "F": len(inst.functions),
           "K": kc, "UK": len(atoms), "feasible": ok, "test_ms": t_test}
    if ok:
        t0 = time.perf_counter()
        en = enumerate_admissible(inst)
        row.update(admissible=en["admissible"], prefixes=en["prefixes"],
                   enum_s=time.perf_counter() - t0)
    else:
        row.update(admissible=0, certificate=cert)
    out[name] = row
    print(f"{name:8} {row['C']:3} {row['P']:3} {row['F']:3} {kc[0]}/{kc[1]}/{kc[2]:<3} {row['UK']:5}  "
          f"{bell(row['C']):.1e}  {bell(row['UK']):.1e}  {row['admissible']:<7} "
          f"{row.get('prefixes', '-'):<9} {t_test:.3f}   {row.get('enum_s', 0):.2f}")
    if not ok:
        print("   certificate:", cert)

print("\n== Table IV: placement quality ==")
print(f"{'case':7} {'placement':12} {'W':>7} budgets viol t/c/d/a  exposure  links nodes  time(ms)")
for name in ("PV", "FLOOD", "ED-fed"):
    inst = cases.ALL[name]()
    res = {}
    t0 = time.perf_counter(); st, _ = search(inst); ts = (time.perf_counter() - t0) * 1e3
    res["Algorithm 1"] = (st.component_placement(), ts)
    t0 = time.perf_counter(); sol = solve_ilp(inst); ti = (time.perf_counter() - t0) * 1e3
    res["ILP (optimal)"] = ((sol["node_of"], sol["type_of"]), ti)
    res["Practice"] = (baselines.practice(inst), 0)
    res["Cloud-first"] = (baselines.cloud_first(inst), 0)
    res["Tech-only"] = (baselines.tech_only(inst), 0)
    out[name]["placements"] = {}
    for label, ((node_of, type_of), t) in res.items():
        ev = evaluate(inst, node_of, type_of)
        out[name]["placements"][label] = {k: ev[k] for k in
            ("W", "met", "functions", "violations", "failstop", "pairs", "stopping_links", "nodes")}
        v = "/".join(map(str, ev["violations"]))
        print(f"{name:7} {label:12} {ev['W']:7.2f} {ev['met']}/{ev['functions']}    {v:10}  "
              f"{ev['failstop']:2}/{ev['pairs']:<2}     {ev['stopping_links']:3}  {ev['nodes']:3}   {t:8.2f}")
os.makedirs("results", exist_ok=True)
json.dump(out, open("results/cases.json", "w"), indent=1, default=str)
