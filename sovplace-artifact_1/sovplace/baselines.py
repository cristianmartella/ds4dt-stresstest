"""Baseline layouts of Section VI-A: Practice, Cloud-first, Tech-only."""
from __future__ import annotations
from typing import Dict, List, Tuple
from .model import Instance
from .search import search
from .cases import INTERMEDIARIES


def _layout(inst: Instance, tier_of) -> Tuple[List[int], Dict[int, int]]:
    """One node per (participant, label); tier_of(component) -> (label, tier)."""
    nt = {(t.part, t.tier): i for i, t in enumerate(inst.node_types)}
    ids: Dict[Tuple[str, str], int] = {}
    node_of, type_of = [], {}
    for c in inst.components:
        part = next(iter(c.adm))
        label, tier = tier_of(c, part)
        b = ids.setdefault((part, label), len(ids))
        node_of.append(b)
        type_of[b] = nt[(part, tier)]
    return node_of, type_of


def practice(inst: Instance):
    """Connector and wallet on an edge node, applications on a premises server,
    edge-only components on the gateway, each intermediary on one regional node."""
    def rule(c, part):
        if part in INTERMEDIARIES:
            return "regional", "regional"
        if c.id.startswith(("CON_", "IW_")):
            return "edge-connector", "edge"
        if c.tiers == frozenset(["edge"]):
            return "gateway", "edge"
        return "server", "server"
    return _layout(inst, rule)


def cloud_first(inst: Instance):
    """Everything that may run regionally on one regional node per participant."""
    def rule(c, part):
        if "regional" in c.tiers:
            return "regional", "regional"
        if "server" in c.tiers:
            return "server", "server"
        return "gateway", "edge"
    return _layout(inst, rule)


def tech_only(inst: Instance):
    """Performance-optimal placement that ignores contracts and degradation commitments."""
    st, cert = search(inst.restricted(["tech"]))
    return st.component_placement()
