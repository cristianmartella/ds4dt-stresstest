"""Governance-aware placement search (Algorithm 1), with incremental evaluation."""
from __future__ import annotations
import heapq
from typing import Dict, List, Optional, Sequence, Set, Tuple
from .model import Instance
from .feasibility import Hosting, atoms_of, certificate
from .cost import class_matrix, hop_latency, CLASSES

EPS = 1e-9


class State:
    """A placement over the atoms of U_K with incrementally maintained cost."""

    def __init__(self, inst: Instance, atoms: List[List[int]]):
        self.inst = inst
        self.atoms = atoms
        self.hosting = Hosting(inst)
        n = len(atoms)
        atom_of = [0] * len(inst.components)
        for a, comps in enumerate(atoms):
            for c in comps:
                atom_of[c] = a
        self.atom_of = atom_of
        self.asum = [self.hosting.summary(comps) for comps in atoms]
        self.asep: List[Set[int]] = [set() for _ in range(n)]
        for x, y in inst.D:
            ax, ay = atom_of[x], atom_of[y]
            if ax != ay:
                self.asep[ax].add(ay)
                self.asep[ay].add(ax)
        cm = class_matrix(inst)
        self.cm = cm
        # latency tables: lat[plane_is_data][level][class] -> (l50, l99)
        self.tab = {}
        for plane in ("data", "other"):
            for lvl in range(4):
                self.tab[(plane == "data", lvl)] = [
                    hop_latency(inst, k, plane, lvl) for k in range(len(CLASSES))]
        # hops between different atoms (only those change with the placement)
        self.h_f: List[int] = []
        self.h_a: List[int] = []
        self.h_b: List[int] = []
        self.h_tab: List[list] = []
        self.atom_hops: List[List[int]] = [[] for _ in range(n)]
        self.rate = [f.rate for f in inst.functions]
        self.budget = [f.budget for f in inst.functions]
        self.L50 = [0.0] * len(inst.functions)
        self.L99 = [0.0] * len(inst.functions)
        intra = self.tab[(False, 0)][0]
        for fi, f in enumerate(inst.functions):
            for h in f.hops:
                if not h.sync:
                    continue
                a, b = atom_of[h.s], atom_of[h.t]
                if a == b:
                    self.L50[fi] += intra[0]
                    self.L99[fi] += intra[1]
                    continue
                k = len(self.h_f)
                self.h_f.append(fi)
                self.h_a.append(a)
                self.h_b.append(b)
                self.h_tab.append(self.tab[(h.plane == "data", h.level)])
                self.atom_hops[a].append(k)
                self.atom_hops[b].append(k)
        self.neigh: List[Set[int]] = [set() for _ in range(n)]
        for k in range(len(self.h_f)):
            self.neigh[self.h_a[k]].add(self.h_b[k])
            self.neigh[self.h_b[k]].add(self.h_a[k])
        # placement: every atom on its own node (the partition U_K)
        self.blk = list(range(n))                      # block id of each atom
        self.members: Dict[int, Set[int]] = {a: {a} for a in range(n)}
        self.alpha: Dict[int, int] = {}
        self.next_id = n
        self.h50 = [0.0] * len(self.h_f)
        self.h99 = [0.0] * len(self.h_f)

    # ---- hostability -------------------------------------------------
    def block_hosts(self, atoms: Sequence[int]) -> List[int]:
        s = set(atoms)
        for a in atoms:
            if self.asep[a] & s:
                return []
        it = iter(atoms)
        a0 = next(it)
        adm, tiers, dem = set(self.asum[a0][0]), set(self.asum[a0][1]), self.asum[a0][2]
        for a in it:
            adm &= self.asum[a][0]
            tiers &= self.asum[a][1]
            dem += self.asum[a][2]
            if not adm or not tiers:
                return []
        return self.hosting.hosts_from(adm, tiers, dem)

    # ---- cost --------------------------------------------------------
    def init_cost(self) -> None:
        for k in range(len(self.h_f)):
            a, b = self.h_a[k], self.h_b[k]
            ba, bb = self.blk[a], self.blk[b]
            cls = 0 if ba == bb else self.cm[self.alpha[ba]][self.alpha[bb]]
            l50, l99 = self.h_tab[k][cls]
            self.h50[k], self.h99[k] = l50, l99
            self.L50[self.h_f[k]] += l50
            self.L99[self.h_f[k]] += l99

    def objective(self) -> Tuple[int, float]:
        met = sum(1 for l, b in zip(self.L99, self.budget) if l <= b + EPS)
        W = sum(r * l for r, l in zip(self.rate, self.L50))
        return met, W

    def delta(self, over: Dict[int, Tuple[int, int]]):
        """Effect of re-assigning the atoms in `over` to (block, type).

        Returns (d_met, d_W, changes); only hops incident to those atoms are touched."""
        seen = set()
        d50: Dict[int, float] = {}
        d99: Dict[int, float] = {}
        changes = []
        blk, alpha, cm = self.blk, self.alpha, self.cm
        for a in over:
            for k in self.atom_hops[a]:
                if k in seen:
                    continue
                seen.add(k)
                x, y = self.h_a[k], self.h_b[k]
                bx, tx = over[x] if x in over else (blk[x], alpha[blk[x]])
                by, ty = over[y] if y in over else (blk[y], alpha[blk[y]])
                cls = 0 if bx == by else cm[tx][ty]
                n50, n99 = self.h_tab[k][cls]
                if n50 != self.h50[k] or n99 != self.h99[k]:
                    f = self.h_f[k]
                    d50[f] = d50.get(f, 0.0) + n50 - self.h50[k]
                    d99[f] = d99.get(f, 0.0) + n99 - self.h99[k]
                    changes.append((k, n50, n99))
        dW = sum(self.rate[f] * v for f, v in d50.items())
        dmet = 0
        for f, v in d99.items():
            b = self.budget[f]
            dmet += (self.L99[f] + v <= b + EPS) - (self.L99[f] <= b + EPS)
        return dmet, dW, changes

    def commit(self, over: Dict[int, Tuple[int, int]], changes) -> None:
        for k, n50, n99 in changes:
            f = self.h_f[k]
            self.L50[f] += n50 - self.h50[k]
            self.L99[f] += n99 - self.h99[k]
            self.h50[k], self.h99[k] = n50, n99
        for a, (b, t) in over.items():
            old = self.blk[a]
            if old != b:
                self.members[old].discard(a)
                if not self.members[old]:
                    del self.members[old]
                    self.alpha.pop(old, None)
                self.members.setdefault(b, set()).add(a)
                self.blk[a] = b
            self.alpha[b] = t

    # ---- export ------------------------------------------------------
    def component_placement(self):
        node_of = [self.blk[self.atom_of[c]] for c in range(len(self.inst.components))]
        return node_of, dict(self.alpha)


def better(dmet: int, dW: float) -> bool:
    return dmet > 0 or (dmet == 0 and dW < -1e-7)


def _reallocate(st: State, b: int) -> bool:
    """Single-block re-allocation: move block b to its best host."""
    atoms = list(st.members[b])
    best = None
    for t in st.block_hosts(atoms):
        if t == st.alpha[b]:
            continue
        over = {a: (b, t) for a in atoms}
        dmet, dW, ch = st.delta(over)
        if better(dmet, dW) and (best is None or (dmet, -dW) > (best[0], -best[1])):
            best = (dmet, dW, over, ch)
    if best:
        st.commit(best[2], best[3])
        return True
    return False


def _score_merge(st: State, b1: int, b2: int):
    atoms = list(st.members[b1]) + list(st.members[b2])
    best = None
    for t in st.block_hosts(atoms):
        over = {a: (b1, t) for a in atoms}
        dmet, dW, ch = st.delta(over)
        if better(dmet, dW) and (best is None or (dmet, -dW) > (best[0], -best[1])):
            best = (dmet, dW, over, ch)
    return best


def _linked_blocks(st: State, b: int) -> Set[int]:
    out = set()
    for a in st.members[b]:
        for x in st.neigh[a]:
            out.add(st.blk[x])
    out.discard(b)
    return out


def search(inst: Instance, atom_moves: bool = True, max_passes: int = 50):
    """Algorithm 1. Returns (state, None) or (None, certificate)."""
    atoms = atoms_of(inst)
    st = State(inst, atoms)
    for a, comps in enumerate(atoms):
        hosts = st.block_hosts([a])
        if not hosts:
            return None, certificate(inst, comps)
        st.alpha[a] = hosts[0]
    st.init_cost()
    for _ in range(max_passes):                       # initial allocation
        if not any([_reallocate(st, b) for b in list(st.members)]):
            break

    def push_pairs(heap, b):
        for o in _linked_blocks(st, b):
            m = _score_merge(st, b, o)
            if m:
                heapq.heappush(heap, (-m[0], m[1], min(b, o), max(b, o)))

    heap: list = []
    for b in list(st.members):
        for o in _linked_blocks(st, b):
            if o > b:
                m = _score_merge(st, b, o)
                if m:
                    heapq.heappush(heap, (-m[0], m[1], b, o))
    while heap:                                       # ascent over linked blocks
        _, _, b1, b2 = heapq.heappop(heap)
        if b1 in st.members and b2 in st.members:
            m = _score_merge(st, b1, b2)
            if m:
                key = (-m[0], m[1])
                if not heap or key <= (heap[0][0], heap[0][1]):
                    st.commit(m[2], m[3])
                    for o in [b1] + list(_linked_blocks(st, b1)):
                        _reallocate(st, o)
                    push_pairs(heap, b1)
                else:
                    heapq.heappush(heap, (key[0], key[1], b1, b2))
        if not heap:                                  # rescan: certify local optimum
            for b in list(st.members):
                for o in _linked_blocks(st, b):
                    if o > b:
                        m = _score_merge(st, b, o)
                        if m:
                            heapq.heappush(heap, (-m[0], m[1], b, o))
    if atom_moves:                                    # moves of atoms of U_K
        for _ in range(max_passes):
            improved = False
            for a in range(len(atoms)):
                src = st.blk[a]
                if len(st.members[src]) == 1 and not st.neigh[a]:
                    continue
                best = None
                cands = {st.blk[x] for x in st.neigh[a]} - {src}
                for tgt in cands:
                    grp = list(st.members[tgt]) + [a]
                    for t in st.block_hosts(grp):
                        over = {x: (tgt, t) for x in grp}
                        dmet, dW, ch = st.delta(over)
                        if better(dmet, dW) and (best is None or (dmet, -dW) > (best[0], -best[1])):
                            best = (dmet, dW, over, ch)
                if len(st.members[src]) > 1:          # move to a new node
                    nb = st.next_id
                    for t in st.block_hosts([a]):
                        over = {a: (nb, t)}
                        dmet, dW, ch = st.delta(over)
                        if better(dmet, dW) and (best is None or (dmet, -dW) > (best[0], -best[1])):
                            best = (dmet, dW, over, ch)
                if best:
                    if any(b == st.next_id for b, _ in best[2].values()):
                        st.next_id += 1
                    st.commit(best[2], best[3])
                    improved = True
            if not improved:
                break
    return st, None
