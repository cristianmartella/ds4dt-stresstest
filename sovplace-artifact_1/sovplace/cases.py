"""The three case studies (Section VI-A), rebuilt from the description in the paper.

Sizes, participants, functions and constraint counts follow Table III. Details
that the paper does not state (exact hops of each function, tiers and demands
of minor components, request rates other than 1/s) are choices made here and
are marked in the README."""
from __future__ import annotations
from typing import Dict, List, Tuple
from .model import Component, Function, Hop, Instance, NodeType

INTERMEDIARIES = ("GOV", "CAT", "AUD")
ES = ("edge", "server")
SR = ("server", "regional")


class Builder:
    def __init__(self, name: str, participants: List[str]):
        self.name = name
        self.P = participants
        self.comps: List[Component] = []
        self.idx: Dict[str, int] = {}
        self.K: List[Tuple[int, int, str]] = []
        self.D: List[Tuple[int, int]] = []
        self.F: List[Function] = []

    def c(self, cid, part, tiers, demand, role=""):
        self.idx[cid] = len(self.comps)
        self.comps.append(Component(cid, frozenset([part]), frozenset(tiers), demand, role))

    def k(self, a, b, kind):
        self.K.append((self.idx[a], self.idx[b], kind))

    def stack(self, p, cache=True):
        """Connector stack of participant p: connector, wallet, audit buffer, catalog cache."""
        self.c(f"CON_{p}", p, ES, 2.0)
        self.c(f"IW_{p}", p, ES, 0.3)
        self.c(f"BUF_{p}", p, ES, 0.2, "buffer")
        self.k(f"CON_{p}", f"IW_{p}", "tech")
        self.k(f"CON_{p}", f"BUF_{p}", "degr")
        if cache:
            self.c(f"CACHE_{p}", p, ES, 0.3, "cache")
            self.k(f"CON_{p}", f"CACHE_{p}", "degr")

    def intermediaries(self):
        self.c("GA", "GOV", ["regional"], 1.0)
        self.c("TA", "GOV", ["regional"], 1.0)
        self.c("FCAT", "CAT", ["regional"], 2.0)
        self.c("VOC", "CAT", ["regional"], 1.0)
        self.c("CH", "AUD", ["regional"], 2.0)
        self.k("TA", "GA", "contract")       # the authority keeps the trust anchor in its enclave

    def f(self, name, path, budget, rate=1.0):
        """path: list of (sender, receiver[, plane[, level[, sync]]])."""
        hops = []
        for h in path:
            s, t = h[0], h[1]
            plane = h[2] if len(h) > 2 else "data"
            level = h[3] if len(h) > 3 else 0
            sync = h[4] if len(h) > 4 else True
            hops.append(Hop(self.idx[s], self.idx[t], plane, level, sync))
        self.F.append(Function(name, hops, budget, rate))

    def build(self) -> Instance:
        nts = []
        for p in self.P:
            if p in INTERMEDIARIES:
                nts.append(NodeType(f"{p}-regional", p, "regional", 64.0))
            else:
                nts += [NodeType(f"{p}-edge", p, "edge", 4.0),
                        NodeType(f"{p}-server", p, "server", 16.0),
                        NodeType(f"{p}-regional", p, "regional", 64.0)]
        return Instance(self.name, self.P, self.comps, self.F, nts, self.K, self.D)


def audit(p):       # usage log to the clearing house, asynchronous
    return (f"CON_{p}", "CH", "audit", 0, False)


def pv() -> Instance:
    b = Builder("PV", ["OP"] + list(INTERMEDIARIES))
    b.c("ADP_S", "OP", ["edge"], 0.3)            # sensor adapter on the gateway
    b.c("ADP_A", "OP", ["edge"], 0.3)            # tracker actuator adapter
    b.c("IOTA", "OP", ES, 0.5)
    b.c("CB", "OP", SR, 2.0)
    b.c("DM", "OP", SR, 1.0)
    b.c("AN", "OP", SR, 1.0)
    b.c("PLAN", "OP", SR, 1.0)
    b.c("FX", "OP", ES + ("regional",), 0.5)
    b.c("RCA", "OP", SR, 8.0)
    b.c("DASH", "OP", SR, 1.0)
    b.stack("OP", cache=False)
    b.intermediaries()
    b.k("ADP_S", "ADP_A", "tech")                # same field bus
    b.f("control-loop", [("ADP_S", "IOTA"), ("IOTA", "CB"), ("CB", "AN"), ("AN", "PLAN"),
                         ("PLAN", "FX"), ("FX", "ADP_A")], 15.0, 1.0)
    b.f("monitoring", [("CB", "DM"), ("DM", "DASH")], 2000.0, 0.2)
    b.f("root-cause", [("DM", "RCA"), ("RCA", "DASH")], 5000.0, 0.05)
    b.f("publication", [("DM", "CON_OP"), ("CON_OP", "GA", "control"),
                        ("CON_OP", "FCAT", "discovery"), audit("OP")], 1000.0, 0.01)
    return b.build()


def flood() -> Instance:
    b = Builder("FLOOD", ["ARPA", "MUN", "CP"] + list(INTERMEDIARIES))
    b.c("ADP_H", "ARPA", ["edge"], 0.3)          # hydrometric stations
    b.c("IOTA_ARPA", "ARPA", ES, 0.5)
    b.c("CB_ARPA", "ARPA", SR, 2.0)
    b.stack("ARPA", cache=False)
    b.c("ADP_U", "MUN", ["edge"], 0.3)           # urban sensors
    b.c("ACT", "MUN", ["edge"], 0.3)             # pumps and gates
    b.c("IOTA_MUN", "MUN", ES, 0.5)
    b.c("CB_MUN", "MUN", SR, 2.0)
    b.c("FX", "MUN", ES, 0.5)                    # feedback executor
    b.stack("MUN", cache=False)
    b.c("AN", "CP", SR, 2.0)
    b.c("SIM", "CP", SR, 16.0)                   # hydraulic simulator
    b.c("PLAN", "CP", SR, 1.0)
    b.c("MAP", "CP", SR, 1.0)
    b.c("CB_CP", "CP", SR, 2.0)
    b.stack("CP", cache=True)
    b.intermediaries()
    b.k("ADP_H", "IOTA_ARPA", "tech")
    b.k("AN", "CON_CP", "contract")              # raw streams only in CP's enforcement domain
    b.k("FX", "CON_MUN", "contract")             # commands run beside the connector that checked them
    b.f("alert-hydro", [("ADP_H", "IOTA_ARPA"), ("IOTA_ARPA", "CB_ARPA"), ("CB_ARPA", "CON_ARPA"),
                        ("CON_ARPA", "CON_CP", "data", 2), ("CON_CP", "AN"), ("AN", "PLAN"),
                        audit("CP")], 200.0, 1.0)
    b.f("alert-urban", [("ADP_U", "IOTA_MUN"), ("IOTA_MUN", "CB_MUN"), ("CB_MUN", "CON_MUN"),
                        ("CON_MUN", "CON_CP", "data", 1), ("CON_CP", "AN"), audit("CP")], 200.0, 1.0)
    b.f("actuation", [("PLAN", "CON_CP"), ("CON_CP", "CON_MUN", "data", 3), ("CON_MUN", "FX"),
                      ("FX", "ACT"), audit("MUN")], 100.0, 0.1)
    b.f("simulation", [("AN", "SIM"), ("SIM", "CB_CP")], 10000.0, 0.02)
    b.f("situational-map", [("CB_CP", "MAP")], 1000.0, 0.2)
    b.f("discovery", [("CON_CP", "FCAT", "discovery"), ("FCAT", "VOC", "discovery"),
                      ("CON_CP", "GA", "control")], 5000.0, 0.02)
    return b.build()


def _ed(name: str, federated: bool) -> Instance:
    H = ["H1", "H2", "H3"]
    b = Builder(name, H + ["RHA"] + list(INTERMEDIARIES))
    for h in H:
        b.stack(h)
        b.c(f"EHR_{h}", h, ["server"], 2.0)      # records system
        b.c(f"CB_{h}", h, SR, 2.0)
        b.c(f"DT_{h}", h, SR, 1.5)               # emergency-department twin
        b.k(f"EHR_{h}", f"CON_{h}", "contract")  # patient-level data leave only through the connector node
        if federated:
            b.c(f"LT_{h}", h, ["server"], 3.0)   # local trainer
            b.k(f"LT_{h}", f"CON_{h}", "contract")
    b.stack("RHA")
    b.c("PLAN", "RHA", SR, 1.0)
    b.c("DASH", "RHA", SR, 1.0)
    if federated:
        b.c("FC", "RHA", SR, 1.0)                # federated-learning coordinator
    else:
        b.c("PRED", "RHA", SR, 6.0)              # central predictor
        for h in H:
            b.k("PRED", f"CON_{h}", "contract")  # compute-to-data clause
    b.intermediaries()
    for h in H:
        b.f(f"load-{h}", [("PLAN", "CON_RHA"), ("CON_RHA", f"CON_{h}", "data", 1),
                          (f"CON_{h}", f"CB_{h}"), audit("RHA")], 500.0, 0.1)
    b.f("patient-transfer", [("DT_H1", "CON_H1"), ("CON_H1", "CON_H2", "data", 3),
                             ("CON_H2", "EHR_H2"), audit("H1")], 300.0, 0.05)
    b.f("hospital-dashboard", [("CB_H1", "DT_H1"), ("PLAN", "DASH")], 1000.0, 0.2)
    b.f("discovery", [("CON_RHA", "FCAT", "discovery"), ("FCAT", "VOC", "discovery"),
                      ("CON_RHA", "GA", "control")], 5000.0, 0.02)
    if federated:
        path = [("FC", "CON_RHA")]
        for h in H:
            path += [("CON_RHA", f"CON_{h}", "data", 2), (f"CON_{h}", f"LT_{h}"),
                     (f"LT_{h}", f"EHR_{h}")]
        b.f("fl-round", path + [audit("RHA")], 30000.0, 0.005)
    return b.build()


def ed_mono() -> Instance:
    return _ed("ED-mono", False)


def ed_fed() -> Instance:
    return _ed("ED-fed", True)


ALL = {"PV": pv, "FLOOD": flood, "ED-mono": ed_mono, "ED-fed": ed_fed}
