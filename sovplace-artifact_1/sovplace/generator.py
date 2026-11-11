"""Synthetic federations (Section VI-D)."""
from __future__ import annotations
import random
from .model import Component, Function, Hop, Instance, NodeType, TIERS
from .feasibility import UnionFind, Hosting

CAPS = {"edge": 4.0, "server": 16.0, "regional": 64.0}


def generate(n: int, seed: int = 0, hard: bool = False, feasible: bool = True,
             contract_frac: float = 0.05) -> Instance:
    rnd = random.Random(seed)
    P = [f"p{i}" for i in range(max(2, n // 8))]
    two = 0.6 if hard else 0.15
    comps = []
    home = []
    for i in range(n):
        p = rnd.choice(P)
        adm = {p}
        if rnd.random() < two:
            adm.add(rnd.choice(P))
        k = rnd.randint(1, 3)
        tiers = frozenset(rnd.sample(TIERS, k))
        comps.append(Component(f"c{i}", frozenset(adm), tiers, round(rnd.uniform(0.2, 3.0), 2)))
        home.append(p)
    by_p = {}
    for i, p in enumerate(home):
        by_p.setdefault(p, []).append(i)
    funcs = []
    intra_hops, all_hops = [], []
    for f in range(max(1, n // 3)):
        cur = rnd.randrange(n)
        hops = []
        for _ in range(rnd.randint(3, 6)):
            if rnd.random() < 0.7 and len(by_p[home[cur]]) > 1:
                nxt = rnd.choice(by_p[home[cur]])
            else:
                nxt = rnd.randrange(n)
            if nxt == cur:
                continue
            hops.append(Hop(cur, nxt, "data", rnd.randint(0, 3), True))
            (intra_hops if home[cur] == home[nxt] else all_hops).append((cur, nxt))
            cur = nxt
        if hops:
            funcs.append(Function(f"f{f}", hops, budget=len(hops) * rnd.uniform(5, 40), rate=1.0))
    cand = [(a, b, "tech") for a, b in intra_hops if rnd.random() < 0.10]
    cand += [(a, b, "contract") for a, b in intra_hops + all_hops if rnd.random() < contract_frac]
    seps = []
    for _ in range(int(0.02 * n)):
        p = rnd.choice(P)
        if len(by_p.get(p, ())) > 1:
            seps.append(tuple(rnd.sample(by_p[p], 2)))
    nts = [NodeType(f"{p}-{t}", p, t, CAPS[t]) for p in P for t in TIERS]
    inst = Instance(f"syn-{n}-{seed}", P, comps, funcs, nts, [], seps)
    rnd.shuffle(cand)
    if not feasible:
        inst.K = cand
        return inst
    # admit constraints in random order only while U_K stays admissible
    uf = UnionFind(n)
    members = {i: [i] for i in range(n)}
    hosting = Hosting(inst)
    for a, b, kind in cand:
        ra, rb = uf.find(a), uf.find(b)
        if ra == rb:
            inst.K.append((a, b, kind))
            continue
        merged = members[ra] + members[rb]
        if hosting.hosts(merged):
            uf.union(ra, rb)
            r = uf.find(ra)
            members[r] = merged
            inst.K.append((a, b, kind))
    return inst
