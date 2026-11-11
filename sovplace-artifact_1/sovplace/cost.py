"""Cost model and partition semantics (Sections III-D and V-A)."""
from __future__ import annotations
from typing import Dict, List, Sequence, Tuple
from .model import Instance
from .feasibility import Hosting

CLASSES = ("intra", "site", "wan-same", "wan-cross")


def hop_class(ta, tb) -> str:
    """Class of a hop between two different nodes of types ta and tb."""
    if ta.part != tb.part:
        return "wan-cross"
    if ta.tier == "regional" or tb.tier == "regional":
        return "wan-same"
    return "site"


def class_matrix(inst: Instance) -> List[List[int]]:
    nt = inst.node_types
    return [[CLASSES.index(hop_class(a, b)) for b in nt] for a in nt]


def hop_latency(inst: Instance, cls: int, plane: str, level: int) -> Tuple[float, float]:
    """(median, 99th percentile) latency of a hop of class index cls."""
    p = inst.params
    name = CLASSES[cls]
    l50, l99 = p.rho50[name], p.rho99[name]
    if name == "wan-cross" and plane == "data":
        l50 += p.tds50[level]
        l99 += p.tds99[level]
    return l50, l99


def evaluate(inst: Instance, node_of: Sequence[int], type_of: Dict[int, int]) -> dict:
    """Evaluate any placement given at component level.

    node_of[c] is the node (block) of component c, type_of[node] its node type.
    Works for inadmissible placements too and counts their violations."""
    cm = class_matrix(inst)
    C = inst.components
    W = 0.0
    met = 0
    L = []
    for f in inst.functions:
        l50 = l99 = 0.0
        for h in f.hops:
            if not h.sync:
                continue
            bs, bt = node_of[h.s], node_of[h.t]
            cls = 0 if bs == bt else cm[type_of[bs]][type_of[bt]]
            a, b = hop_latency(inst, cls, h.plane, h.level)
            l50 += a
            l99 += b
        W += f.rate * l50
        met += l99 <= f.budget + 1e-9
        L.append((l50, l99))
    # violations
    viol = {"tech": 0, "contract": 0, "degr": 0}
    for a, b, kind in inst.K:
        if node_of[a] != node_of[b]:
            viol[kind] += 1
    blocks: Dict[int, List[int]] = {}
    for c, b in enumerate(node_of):
        blocks.setdefault(b, []).append(c)
    hosting = Hosting(inst)
    unhostable = sum(1 for b, comps in blocks.items()
                     if type_of[b] not in hosting.hosts(comps))
    # partition semantics
    has_buf = {b: any(C[c].role == "buffer" for c in comps) for b, comps in blocks.items()}
    has_cache = {b: any(C[c].role == "cache" for c in comps) for b, comps in blocks.items()}
    failstop = pairs = 0
    stopping_links = set()
    for f in inst.functions:
        links: Dict[Tuple[int, int], List] = {}
        for h in f.hops:
            bs, bt = node_of[h.s], node_of[h.t]
            if bs != bt:
                links.setdefault((min(bs, bt), max(bs, bt)), []).append(h)
        for link, hops in links.items():
            pairs += 1
            if all(h.plane == "audit" and has_buf[node_of[h.s]] for h in hops):
                continue                                   # defer
            if all(h.plane == "discovery" and has_cache[node_of[h.s]] for h in hops):
                continue                                   # degrade
            failstop += 1
            stopping_links.add(link)
    return {"W": W, "met": met, "functions": len(inst.functions), "latency": L,
            "violations": (viol["tech"], viol["contract"], viol["degr"], unhostable),
            "failstop": failstop, "pairs": pairs, "stopping_links": len(stopping_links),
            "nodes": len(blocks)}
