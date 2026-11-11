"""Placement lattice: U_K, hostability, feasibility test, certificate (Section IV)."""
from __future__ import annotations
from collections import deque
from typing import Dict, List, Optional, Sequence, Tuple
from .model import Instance


class UnionFind:
    def __init__(self, n: int):
        self.p = list(range(n))
        self.r = [0] * n

    def find(self, x: int) -> int:
        p = self.p
        while p[x] != x:
            p[x] = p[p[x]]
            x = p[x]
        return x

    def union(self, a: int, b: int) -> None:
        a, b = self.find(a), self.find(b)
        if a == b:
            return
        if self.r[a] < self.r[b]:
            a, b = b, a
        self.p[b] = a
        if self.r[a] == self.r[b]:
            self.r[a] += 1


def atoms_of(inst: Instance) -> List[List[int]]:
    """U_K: connected components of (C, K), as lists of component indices."""
    uf = UnionFind(len(inst.components))
    for a, b, _ in inst.K:
        uf.union(a, b)
    groups: Dict[int, List[int]] = {}
    for c in range(len(inst.components)):
        groups.setdefault(uf.find(c), []).append(c)
    return list(groups.values())


class Hosting:
    """Evaluates hosts(B) for blocks given as collections of component indices."""

    def __init__(self, inst: Instance):
        self.inst = inst
        self.sep = {}
        for a, b in inst.D:
            self.sep.setdefault(a, set()).add(b)
            self.sep.setdefault(b, set()).add(a)

    def separated(self, comps: Sequence[int]) -> Optional[Tuple[int, int]]:
        if not self.sep:
            return None
        s = set(comps)
        for a in comps:
            for b in self.sep.get(a, ()):
                if b in s:
                    return (a, b)
        return None

    def summary(self, comps: Sequence[int]):
        """(admitted participants, admissible tiers, total demand) of a block."""
        C = self.inst.components
        adm = set(C[comps[0]].adm)
        tiers = set(C[comps[0]].tiers)
        dem = 0.0
        for c in comps:
            adm &= C[c].adm
            tiers &= C[c].tiers
            dem += C[c].demand
        return adm, tiers, dem

    def hosts_from(self, adm, tiers, dem) -> List[int]:
        return [i for i, t in enumerate(self.inst.node_types)
                if t.part in adm and t.tier in tiers and dem <= t.cap + 1e-9]

    def hosts(self, comps: Sequence[int]) -> List[int]:
        if self.separated(comps) is not None:
            return []
        return self.hosts_from(*self.summary(comps))


def certificate(inst: Instance, block: Sequence[int]) -> dict:
    """Conflict certificate of a non-hostable block of U_K (Proposition 1)."""
    C = inst.components
    h = Hosting(inst)
    adj: Dict[int, List[Tuple[int, str]]] = {}
    for a, b, kind in inst.K:
        adj.setdefault(a, []).append((b, kind))
        adj.setdefault(b, []).append((a, kind))
    sepset = {frozenset(p) for p in inst.D}
    best = None
    for i, a in enumerate(block):
        for b in block[i + 1:]:
            if frozenset((a, b)) in sepset:
                why = "separation"
            elif not (C[a].adm & C[b].adm):
                why = "participants"
            elif not (C[a].tiers & C[b].tiers):
                why = "tiers"
            else:
                continue
            prev = {a: None}
            q = deque([a])
            while q and b not in prev:
                x = q.popleft()
                for y, kind in adj.get(x, ()):
                    if y not in prev:
                        prev[y] = (x, kind)
                        q.append(y)
            path = []
            x = b
            while prev[x] is not None:
                px, kind = prev[x]
                path.append((C[px].id, C[x].id, kind))
                x = px
            path.reverse()
            if best is None or len(path) < len(best["path"]):
                best = {"type": "pairwise", "reason": why, "pair": (C[a].id, C[b].id),
                        "adm": (sorted(C[a].adm), sorted(C[b].adm)), "path": path}
    if best:
        return best
    adm, tiers, dem = h.summary(block)
    return {"type": "collective", "block": [C[c].id for c in block],
            "adm": sorted(adm), "tiers": sorted(tiers), "demand": dem}


def feasibility(inst: Instance):
    """Theorem 1: a compliant placement exists iff every block of U_K is hostable.

    Returns (feasible, atoms, certificate or None)."""
    atoms = atoms_of(inst)
    h = Hosting(inst)
    for blk in atoms:
        if not h.hosts(blk):
            return False, atoms, certificate(inst, blk)
    return True, atoms, None
