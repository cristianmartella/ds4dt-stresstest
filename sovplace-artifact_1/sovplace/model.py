"""Governed deployment model (Section III of the paper)."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, FrozenSet, List, Optional, Sequence, Tuple

TIERS = ("edge", "server", "regional")
PLANES = ("data", "control", "discovery", "audit")


@dataclass(frozen=True)
class Component:
    id: str
    adm: FrozenSet[str]           # participants admitted to host it
    tiers: FrozenSet[str]         # admissible tiers
    demand: float                 # cores
    role: str = ""                # "buffer", "cache" or ""


@dataclass(frozen=True)
class Hop:
    s: int                        # index of the sender component
    t: int                        # index of the receiver component
    plane: str = "data"
    level: int = 0                # usage-policy level P0..P3
    sync: bool = True


@dataclass
class Function:
    name: str
    hops: List[Hop]
    budget: float = float("inf")  # 99th-percentile budget (ms)
    rate: float = 1.0             # requests/s (weight w_f)


@dataclass(frozen=True)
class NodeType:
    id: str
    part: str
    tier: str
    cap: float                    # cores


@dataclass
class Params:
    """Round trips per hop class (ms) and data-space cost per policy level."""
    rho50: Dict[str, float] = field(default_factory=lambda: {
        "intra": 0.02, "site": 0.3, "wan-same": 8.0, "wan-cross": 12.0})
    rho99: Dict[str, float] = field(default_factory=lambda: {
        "intra": 0.05, "site": 0.8, "wan-same": 16.0, "wan-cross": 24.0})
    # One measured value for every policy level: the steady-state cost under a
    # single unconstrained permission (P1) at 100 requests per burst.
    tds50: Sequence[float] = (0.5, 0.5, 0.5, 0.5)
    tds99: Sequence[float] = (24.0, 24.0, 24.0, 24.0)

    def scaled(self, k: float) -> "Params":
        """Scale the wide-area round trips by k (sensitivity analysis)."""
        p = Params(dict(self.rho50), dict(self.rho99), self.tds50, self.tds99)
        for c in ("wan-same", "wan-cross"):
            p.rho50[c] *= k
            p.rho99[c] *= k
        return p


@dataclass
class Instance:
    name: str
    participants: List[str]
    components: List[Component]
    functions: List[Function]
    node_types: List[NodeType]
    K: List[Tuple[int, int, str]]          # (a, b, kind), kind in tech/contract/degr
    D: List[Tuple[int, int]] = field(default_factory=list)   # separation
    params: Params = field(default_factory=Params)

    def index(self, cid: str) -> int:
        if not hasattr(self, "_idx"):
            self._idx = {c.id: i for i, c in enumerate(self.components)}
        return self._idx[cid]

    def restricted(self, kinds: Sequence[str]) -> "Instance":
        """Copy of the instance keeping only the co-location kinds given."""
        return Instance(self.name, self.participants, self.components,
                        self.functions, self.node_types,
                        [k for k in self.K if k[2] in kinds], self.D, self.params)

    def with_params(self, params: Params) -> "Instance":
        return Instance(self.name, self.participants, self.components,
                        self.functions, self.node_types, self.K, self.D, params)
