"""Figure 3: sensitivity to the wide-area round trip. python3 scripts/run_sensitivity.py"""
import json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from sovplace import cases, baselines
from sovplace.search import search
from sovplace.cost import evaluate

out = {}
print("case    scale  wan-cross  Alg.1 W (met)   Practice W (met)   Cloud-first W (met)")
for name in ("PV", "FLOOD", "ED-fed"):
    base = cases.ALL[name]()
    for k in (0.25, 0.5, 1, 2, 3, 4, 5, 6):
        inst = base.with_params(base.params.scaled(k))
        st, _ = search(inst)
        rows = {"alg": evaluate(inst, *st.component_placement()),
                "practice": evaluate(inst, *baselines.practice(inst)),
                "cloud": evaluate(inst, *baselines.cloud_first(inst))}
        out[f"{name}@{k}"] = {l: (r["W"], r["met"]) for l, r in rows.items()}
        f = rows["alg"]["functions"]
        print(f"{name:7} {k:5}  {12*k:8.0f}  " + "   ".join(
            f"{r['W']:8.2f} ({r['met']}/{f})" for r in rows.values()))
os.makedirs("results", exist_ok=True)
json.dump(out, open("results/sensitivity.json", "w"), indent=1)
