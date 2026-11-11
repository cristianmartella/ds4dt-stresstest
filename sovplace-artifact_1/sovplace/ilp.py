"""Exact integer program over the atoms of U_K (Section V-C), solved with HiGHS."""
from __future__ import annotations
from typing import Dict, List, Tuple
import numpy as np
from scipy.optimize import milp, LinearConstraint, Bounds
from scipy.sparse import coo_matrix
from .model import Instance
from .feasibility import atoms_of
from .search import State


def solve_ilp(inst: Instance, time_limit: float = 900.0):
    """Returns dict(status, met, W, node_of, type_of) or None if infeasible."""
    atoms = atoms_of(inst)
    st = State(inst, atoms)
    n = len(atoms)
    T = [st.block_hosts([a]) for a in range(n)]
    if any(not t for t in T):
        return None
    nt = len(inst.node_types)
    cols: List[Tuple] = []
    idx: Dict[Tuple, int] = {}

    def var(key):
        idx[key] = len(cols)
        cols.append(key)
        return idx[key]

    # y[a, tau, i]: atom a on instance i of type tau; the k-th atom that tau can
    # host may use instances 0..k only (symmetry breaking)
    rank = [[-1] * nt for _ in range(n)]
    cnt = [0] * nt
    for a in range(n):
        for t in T[a]:
            rank[a][t] = cnt[t]
            cnt[t] += 1
            for i in range(rank[a][t] + 1):
                var(("y", a, t, i))
    ny = len(cols)
    # linked atom pairs with their aggregated cost coefficients
    pairs: Dict[Tuple[int, int], List[int]] = {}
    for k in range(len(st.h_f)):
        a, b = st.h_a[k], st.h_b[k]
        key, flip = ((a, b), False) if a < b else ((b, a), True)
        pairs.setdefault(key, []).append(k)
    fin = [f for f in range(len(inst.functions)) if inst.functions[f].budget != float("inf")]
    rows, cidx, vals, lo, hi = [], [], [], [], []
    r = 0

    def add(coefs, l, h):
        nonlocal r
        for c, v in coefs:
            rows.append(r)
            cidx.append(c)
            vals.append(v)
        lo.append(l)
        hi.append(h)
        r += 1

    obj: Dict[int, float] = {}
    bud: Dict[int, Dict[int, float]] = {f: {} for f in fin}
    const99 = {f: st.L99[f] for f in fin}          # intra-atom hops
    for (a, b), hs in pairs.items():
        for ta in T[a]:
            for tb in T[b]:
                p = var(("p", a, b, ta, tb))
                cls = st.cm[ta][tb]
                w = sum(st.rate[st.h_f[k]] * st.h_tab[k][cls][0] for k in hs)
                obj[p] = obj.get(p, 0.0) + w
                for k in hs:
                    f = st.h_f[k]
                    if f in bud:
                        bud[f][p] = bud[f].get(p, 0.0) + st.h_tab[k][cls][1]
                # p >= t_a,ta + t_b,tb - 1
                co = [(p, 1.0)]
                co += [(idx[("y", a, ta, i)], -1.0) for i in range(rank[a][ta] + 1)]
                co += [(idx[("y", b, tb, i)], -1.0) for i in range(rank[b][tb] + 1)]
                add(co, -1.0, np.inf)
        add([(idx[("p", a, b, ta, tb)], 1.0) for ta in T[a] for tb in T[b]], 1.0, 1.0)
        for t in set(T[a]) & set(T[b]):
            cls = st.cm[t][t]
            for i in range(min(rank[a][t], rank[b][t]) + 1):
                s = var(("s", a, b, t, i))
                add([(s, 1.0), (idx[("y", a, t, i)], -1.0)], -np.inf, 0.0)
                add([(s, 1.0), (idx[("y", b, t, i)], -1.0)], -np.inf, 0.0)
                w = sum(st.rate[st.h_f[k]] * (st.h_tab[k][cls][0] - st.h_tab[k][0][0]) for k in hs)
                obj[s] = obj.get(s, 0.0) - w
                for k in hs:
                    f = st.h_f[k]
                    if f in bud:
                        bud[f][s] = bud[f].get(s, 0.0) - (st.h_tab[k][cls][1] - st.h_tab[k][0][1])
    # assignment, capacity, separation
    for a in range(n):
        add([(idx[("y", a, t, i)], 1.0) for t in T[a] for i in range(rank[a][t] + 1)], 1.0, 1.0)
    by_inst: Dict[Tuple[int, int], List[int]] = {}
    for key, c in idx.items():
        if key[0] == "y":
            by_inst.setdefault((key[2], key[3]), []).append(key[1])
    for (t, i), members in by_inst.items():
        add([(idx[("y", a, t, i)], st.asum[a][2]) for a in members],
            -np.inf, inst.node_types[t].cap + 1e-9)
        ms = set(members)
        for a in members:
            for b in st.asep[a]:
                if b > a and b in ms:
                    add([(idx[("y", a, t, i)], 1.0), (idx[("y", b, t, i)], 1.0)], -np.inf, 1.0)
    # budgets: L99(f) <= B_f + M_f (1 - b_f)
    wmax = sum(max(v, 0.0) for v in obj.values()) + 1.0
    bvars = {}
    for f in fin:
        bf = var(("b", f))
        bvars[f] = bf
        M = const99[f] + sum(max(v, 0.0) for v in bud[f].values())
        add(list(bud[f].items()) + [(bf, M)], -np.inf, inst.functions[f].budget + M - const99[f])
        obj[bf] = -wmax
    nv = len(cols)
    c = np.zeros(nv)
    for k, v in obj.items():
        c[k] = v
    integrality = np.zeros(nv)
    integrality[:ny] = 1
    for bf in bvars.values():
        integrality[bf] = 1
    A = coo_matrix((vals, (rows, cidx)), shape=(r, nv)).tocsr()
    res = milp(c, constraints=LinearConstraint(A, np.array(lo), np.array(hi)),
               integrality=integrality, bounds=Bounds(0, 1),
               options={"time_limit": time_limit, "mip_rel_gap": 0.0})
    if res.x is None:
        return None
    blk = [0] * n
    alpha: Dict[int, int] = {}
    ids: Dict[Tuple[int, int], int] = {}
    for key, j in idx.items():
        if key[0] == "y" and res.x[j] > 0.5:
            b = ids.setdefault((key[2], key[3]), len(ids))
            blk[key[1]] = b
            alpha[b] = key[2]
    node_of = [blk[st.atom_of[cc]] for cc in range(len(inst.components))]
    return {"status": "optimal" if res.status == 0 else "time limit",
            "node_of": node_of, "type_of": alpha}
