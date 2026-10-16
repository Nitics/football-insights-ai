"""Shared data contracts: events in, moments and overlays out.

Everything downstream (stats, agents, overlays, UI) reads these shapes,
so they are kept small, flat and JSON-serialisable.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

PITCH_LENGTH = 105.0
PITCH_WIDTH = 68.0

EventType = Literal[
    "kickoff", "pass", "carry", "pressure", "tackle", "interception",
    "shot", "out", "recovery", "half_end", "full_time",
]


@dataclass
class Player:
    id: str
    name: str
    number: int
    position: str          # GK, DF, MF, FW
    base_x: float          # typical depth in own attacking frame (0..105)
    team: str


@dataclass
class Team:
    id: str
    name: str
    short: str
    color: str
    players: list[Player]
    attack: float = 1.0    # scales shot generation
    passing: float = 1.0   # scales pass success
    press: float = 1.0     # scales pressing intensity


@dataclass
class Event:
    """One synthetic match event. Coordinates are absolute pitch metres:
    home attacks towards x=105, away towards x=0 (no side switch, for
    simpler rendering)."""
    id: str
    match_id: str
    seq: int
    t: float                         # match clock, seconds
    period: int
    type: EventType
    team: str | None = None
    player: str | None = None
    x: float | None = None
    y: float | None = None
    end_x: float | None = None
    end_y: float | None = None
    outcome: str | None = None       # complete/incomplete/goal/saved/off_target/blocked/won/lost
    receiver: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def minute(self) -> int:
        return int(self.t // 60) + 1

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["minute"] = self.minute
        return d


MomentKind = Literal[
    "goal", "big_chance", "momentum_swing", "press_drop", "control_shift",
    "possession_spell", "milestone", "speed_trigger",
]


@dataclass
class Moment:
    """A detected moment worth telling, with the evidence that backs it.

    `facts` holds every number an agent is allowed to quote. The verifier
    rejects any generated text that cites a number not found here.
    """
    id: str
    t: float
    kind: MomentKind
    team: str | None
    players: list[str]
    importance: float
    facts: dict[str, Any]
    event_ids: list[str]

    @property
    def minute(self) -> int:
        return int(self.t // 60) + 1

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["minute"] = self.minute
        return d


@dataclass
class Overlay:
    """Timed, machine-readable graphic for a broadcast renderer."""
    id: str
    moment_id: str
    slot: Literal["lower_third", "stat_bug", "player_tag", "full_screen"]
    t_start: float
    t_end: float
    priority: float
    headline: str
    body: str
    persona: dict[str, Any]
    verified: bool
    evidence_event_ids: list[str]
    agent_trace: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
