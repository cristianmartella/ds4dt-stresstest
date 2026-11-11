"""Exhaustive enumeration of the admissible region with down-set pruning."""
from __future__ import annotations
import itertools
from typing import List, Optional
from .model import Instance
from .feasibility import atoms_of
from .search import State


def enumerate_admissible(inst: Instance, optimum: bool = False, max_alloc: int = 4096):
    """Counts the admissible partitions above U_K by restricted-growth strings.

    A partial block that is not hostable cannot become hostable when atoms are
    added (Lemma 2), so its subtree is pruned. With optimum=True, every admissible
    partition is also costed under its best allocation (exhaustive over hosts)."""
    atoms = atoms_of(inst)
    st = State(inst, atoms)
    n = len(atoms)
    blocks: List[List[int]] = []
    hosts: List[List[int]] = []
    stats = {"admissible": 0, "prefixes": 0, "best": None}

    def cost(assign, types):
        met, W = 0, 0.0
        L50 = [0.0] * len(st.rate)
        L99 = [0.0] * len(st.rate)
        intra = st.tab[(False, 0)][0]
        for fi, f in enumerate(inst.functions):
            for h in f.hops:
                if h.sync and st.atom_of[h.s] == st.atom_of[h.t]:
                    L50[fi] += intra[0]
                    L99[fi] += intra[1]
        for k in range(len(st.h_f)):
            ba, bb = assign[st.h_a[k]], assign[st.h_b[k]]
            cls = 0 if ba == bb else st.cm[types[ba]][types[bb]]
            l50, l99 = st.h_tab[k][cls]
            L50[st.h_f[k]] += l50
            L99[st.h_f[k]] += l99
        met = sum(1 for l, b in zip(L99, st.budget) if l <= b + 1e-9)
        W = sum(r * l for r, l in zip(st.rate, L50))
        return met, W

    def rec(i: int):
        if i == n:
            stats["admissible"] += 1
            if optimum:
                assign = [0] * n
                for b, blk in enumerate(blocks):
                    for a in blk:
                        assign[a] = b
                combos = 1
                for h in hosts:
                    combos *= len(h)
                if combos > max_alloc:
                    raise RuntimeError("too many allocations; raise max_alloc")
                for types in itertools.product(*hosts):
                    met, W = cost(assign, types)
                    key = (-met, W)
                    if stats["best"] is None or key < stats["best"][0]:
                        stats["best"] = (key, [list(b) for b in blocks], types)
            return
        for b in range(len(blocks) + 1):
            if b == len(blocks):
                blocks.append([i])
                hosts.append(st.block_hosts([i]))
            else:
                blocks[b].append(i)
                old = hosts[b]
                hosts[b] = st.block_hosts(blocks[b])
            ok = bool(hosts[b])
            if ok:
                stats["prefixes"] += 1
                rec(i + 1)
            if b == len(blocks) - 1 and len(blocks[b]) == 1:
                blocks.pop()
                hosts.pop()
            else:
                blocks[b].pop()
                hosts[b] = old

    rec(0)
    out = {"admissible": stats["admissible"], "prefixes": stats["prefixes"], "atoms": n}
    if optimum and stats["best"]:
        out["met"] = -stats["best"][0][0]
        out["W"] = stats["best"][0][1]
    return out


def bell(n: int) -> int:
    row = [1]
    for _ in range(n):
        new = [row[-1]]
        for x in row:
            new.append(new[-1] + x)
        row = new
    return row[0]
