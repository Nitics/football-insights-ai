"""Interpret: a streaming engine that turns events into stats, game states
and detected moments, each carrying an evidence pack.

Feed it one event at a time with `ingest()`; it returns any new Moments.
All detection is deterministic code, so every claim an agent later makes
can be traced back to numbers computed here.
"""
from __future__ import annotations

import math
from collections import defaultdict, deque
from dataclasses import dataclass, field

from .models import Event, Moment
from .sim import Match

COOLDOWN = {
    "momentum_swing": 600, "press_drop": 900, "control_shift": 600,
    "possession_spell": 300, "speed_trigger": 420,
}
SPEED_TRIGGER_KMH = 33.0
PASS_MILESTONES = (50, 75)


@dataclass
class TeamStats:
    passes: int = 0
    passes_complete: int = 0
    progressive_passes: int = 0
    final_third_entries: int = 0
    shots: int = 0
    shots_on_target: int = 0
    goals: int = 0
    xg: float = 0.0
    tackles: int = 0
    interceptions: int = 0
    recoveries: int = 0
    pressures: int = 0
    possession_s: float = 0.0
    max_shot_speed: float = 0.0

    def view(self) -> dict:
        return {
            "passes": self.passes,
            "pass_accuracy": round(100 * self.passes_complete / self.passes) if self.passes else 0,
            "progressive_passes": self.progressive_passes,
            "final_third_entries": self.final_third_entries,
            "shots": self.shots, "shots_on_target": self.shots_on_target,
            "goals": self.goals, "xg": round(self.xg, 2),
            "tackles": self.tackles, "interceptions": self.interceptions,
            "pressures": self.pressures, "max_shot_speed_kmh": self.max_shot_speed,
        }


@dataclass
class PlayerStats:
    passes: int = 0
    passes_complete: int = 0
    pass_distance: float = 0.0
    hardest_pass: float = 0.0
    shots: int = 0
    goals: int = 0
    xg: float = 0.0
    tackles: int = 0
    top_speed: float = 0.0
    carry_distance: float = 0.0

    def view(self) -> dict:
        return {
            "passes": self.passes,
            "pass_accuracy": round(100 * self.passes_complete / self.passes) if self.passes else 0,
            "avg_pass_m": round(self.pass_distance / self.passes, 1) if self.passes else 0,
            "hardest_pass": self.hardest_pass, "shots": self.shots, "goals": self.goals,
            "xg": round(self.xg, 2), "tackles": self.tackles,
            "top_speed_kmh": self.top_speed, "carry_m": round(self.carry_distance),
        }


@dataclass
class Engine:
    match: Match
    team_stats: dict[str, TeamStats] = field(default_factory=lambda: defaultdict(TeamStats))
    player_stats: dict[str, PlayerStats] = field(default_factory=lambda: defaultdict(PlayerStats))
    moments: list[Moment] = field(default_factory=list)
    timeline: list[dict] = field(default_factory=list)   # sampled game-state series

    def __post_init__(self):
        self.home = self.match.home.id
        self.away = self.match.away.id
        self.score = {self.home: 0, self.away: 0}
        self.last: Event | None = None
        self.poss_team: str | None = None
        self.chain: list[Event] = []          # current possession's events
        self.recent: deque[Event] = deque()   # last 10 match-minutes
        self.threat = {self.home: 0.0, self.away: 0.0}   # decayed attacking threat
        self.momentum = 0.0
        self.control = 0.0
        self._last_fire: dict[tuple, float] = {}
        self._press_hist: dict[str, deque] = {self.home: deque(), self.away: deque()}
        self._mom_extreme = 0.0
        self._ctrl_state = 0
        self._milestones: set[tuple] = set()
        self._next_sample = 0.0

    # ---------- public ----------
    def ingest(self, e: Event) -> list[Moment]:
        new: list[Moment] = []
        self._clock(e)
        self._possession(e, new)
        self._stats(e, new)
        self._windows(e)
        self._game_state(e, new)
        self.last = e
        self.moments.extend(new)
        return new

    def snapshot(self) -> dict:
        return {
            "score": dict(self.score),
            "momentum": round(self.momentum, 2),
            "control_index": round(self.control, 2),
            "press": {t: round(self._ppda_like(t), 2) for t in (self.home, self.away)},
            "possession_pct": self._possession_pct(),
            "teams": {t: self.team_stats[t].view() for t in (self.home, self.away)},
        }

    def player_view(self, pid: str) -> dict:
        return self.player_stats[pid].view()

    # ---------- internals ----------
    def name(self, pid: str | None) -> str:
        return self.match.player(pid).name if pid else ""

    def tname(self, tid: str | None) -> str:
        return self.match.team(tid).name if tid else ""

    def _fire(self, key: tuple, t: float, cooldown: float) -> bool:
        last = self._last_fire.get(key)
        if last is not None and t - last < cooldown:
            return False
        self._last_fire[key] = t
        return True

    def _moment(self, e: Event, kind, team, players, importance, facts, ids) -> Moment:
        return Moment(
            id=f"{kind}-{e.seq}", t=e.t, kind=kind, team=team, players=[p for p in players if p],
            importance=importance, facts=facts, event_ids=ids,
        )

    def _clock(self, e: Event) -> None:
        if self.last and self.poss_team and e.period == self.last.period:
            self.team_stats[self.poss_team].possession_s += max(0.0, e.t - self.last.t)

    def _possession_pct(self) -> dict[str, int]:
        h = self.team_stats[self.home].possession_s
        a = self.team_stats[self.away].possession_s
        tot = h + a or 1
        return {self.home: round(100 * h / tot), self.away: round(100 * a / tot)}

    def _possession(self, e: Event, new: list[Moment]) -> None:
        owner = e.team if e.type in ("pass", "carry", "shot", "kickoff", "interception",
                                     "recovery", "tackle") else None
        if owner is None:
            return
        if owner != self.poss_team:
            self._close_chain(e, new)
            self.poss_team = owner
            self.chain = []
        self.chain.append(e)

    def _close_chain(self, e: Event, new: list[Moment]) -> None:
        passes = [c for c in self.chain if c.type == "pass" and c.outcome == "complete"]
        if len(passes) >= 15 and self.poss_team:
            if self._fire(("spell", self.poss_team), e.t, COOLDOWN["possession_spell"]):
                players = {p.player for p in passes}
                dur = round(self.chain[-1].t - self.chain[0].t)
                new.append(self._moment(
                    e, "possession_spell", self.poss_team, list(players)[:3], 0.45,
                    {"team": self.tname(self.poss_team), "passes": len(passes),
                     "players_involved": len(players), "seconds": dur,
                     "minute": e.minute},
                    [c.id for c in passes],
                ))

    def _stats(self, e: Event, new: list[Moment]) -> None:
        if not e.team:
            return
        ts = self.team_stats[e.team]
        ps = self.player_stats[e.player] if e.player else None
        if e.type == "pass":
            ts.passes += 1
            ps.passes += 1
            ps.pass_distance += e.extra["distance_m"]
            if e.outcome == "complete":
                ts.passes_complete += 1
                ps.passes_complete += 1
                ps.hardest_pass = max(ps.hardest_pass, e.extra["difficulty"])
                if e.extra.get("progressive"):
                    ts.progressive_passes += 1
                ax_end = e.end_x if e.team == self.home else 105 - e.end_x
                ax_start = e.x if e.team == self.home else 105 - e.x
                if ax_end > 70 >= ax_start:
                    ts.final_third_entries += 1
                    self._add_threat(e.team, e.t, 0.03)
                n = ps.passes_complete
                if n in PASS_MILESTONES and (e.player, n) not in self._milestones:
                    self._milestones.add((e.player, n))
                    acc = round(100 * ps.passes_complete / ps.passes)
                    new.append(self._moment(
                        e, "milestone", e.team, [e.player], 0.3,
                        {"player": self.name(e.player), "team": self.tname(e.team),
                         "completed_passes": n, "pass_accuracy": acc, "minute": e.minute},
                        [e.id],
                    ))
        elif e.type == "carry":
            ps.carry_distance += e.extra["distance_m"]
            spd = e.extra["carrier_speed_kmh"]
            ps.top_speed = max(ps.top_speed, spd)
            if spd >= SPEED_TRIGGER_KMH and self._fire(("speed", e.team), e.t, COOLDOWN["speed_trigger"]):
                new.append(self._moment(
                    e, "speed_trigger", e.team, [e.player], 0.25,
                    {"player": self.name(e.player), "team": self.tname(e.team),
                     "speed_kmh": spd, "distance_m": e.extra["distance_m"], "minute": e.minute},
                    [e.id],
                ))
        elif e.type == "tackle":
            ts.tackles += 1
            ps.tackles += 1
        elif e.type == "interception":
            ts.interceptions += 1
        elif e.type == "recovery":
            ts.recoveries += 1
        elif e.type == "pressure":
            ts.pressures += 1
        elif e.type == "shot":
            self._shot(e, ts, ps, new)

    def _shot(self, e: Event, ts: TeamStats, ps: PlayerStats, new: list[Moment]) -> None:
        xg = e.extra["xg"]
        ts.shots += 1
        ts.xg += xg
        ts.max_shot_speed = max(ts.max_shot_speed, e.extra["shot_speed_kmh"])
        ps.shots += 1
        ps.xg += xg
        self._add_threat(e.team, e.t, xg)
        if e.outcome in ("goal", "saved"):
            ts.shots_on_target += 1
        build = [c for c in self.chain if c.type == "pass" and c.outcome == "complete"]
        dist = round(math.hypot(105 - (e.x if e.team == self.home else 105 - e.x), 34 - e.y))
        if e.outcome == "goal":
            ts.goals += 1
            ps.goals += 1
            self.score[e.team] += 1
            opp = self.away if e.team == self.home else self.home
            facts = {
                "scorer": self.name(e.player), "team": self.tname(e.team),
                "assist": self.name(e.extra.get("assist")), "xg": round(xg, 2),
                "shot_speed_kmh": e.extra["shot_speed_kmh"], "distance_m": dist,
                "body_part": e.extra["body_part"], "passes_in_move": len(build),
                "score_home": self.score[self.home], "score_away": self.score[self.away],
                "momentum_for_team_before": round(self.momentum if e.team == self.home else -self.momentum, 2),
                "minute": e.minute,
                "team_xg_total": round(ts.xg, 2), "opponent_xg_total": round(self.team_stats[opp].xg, 2),
            }
            new.append(self._moment(e, "goal", e.team, [e.player, e.extra.get("assist")], 1.0,
                                    facts, [c.id for c in build[-6:]] + [e.id]))
        elif xg >= 0.28:
            new.append(self._moment(
                e, "big_chance", e.team, [e.player], 0.7,
                {"player": self.name(e.player), "team": self.tname(e.team), "xg": round(xg, 2),
                 "outcome": e.outcome, "distance_m": dist,
                 "shot_speed_kmh": e.extra["shot_speed_kmh"], "minute": e.minute},
                [e.id],
            ))

    def _add_threat(self, team: str, t: float, v: float) -> None:
        self._decay(t)
        self.threat[team] += v

    def _decay(self, t: float) -> None:
        dt = t - getattr(self, "_threat_t", t)
        if dt > 0:
            k = math.exp(-dt / 240)   # ~4 minute memory
            for k_ in self.threat:
                self.threat[k_] *= k
        self._threat_t = t

    def _windows(self, e: Event) -> None:
        if self.last and e.period != self.last.period:
            self.recent.clear()
            for h in self._press_hist.values():
                h.clear()
        self.recent.append(e)
        while self.recent and e.t - self.recent[0].t > 600:
            self.recent.popleft()

    def _ppda_like(self, team: str) -> float:
        """Pressures by `team` per opponent pass over the last 10 minutes."""
        opp = self.away if team == self.home else self.home
        pr = sum(1 for r in self.recent if r.type == "pressure" and r.team == team)
        op = sum(1 for r in self.recent if r.type == "pass" and r.team == opp)
        return pr / op if op >= 10 else 0.0

    def _control_index(self) -> float:
        win = [r for r in self.recent if self.recent[-1].t - r.t <= 300]
        if len(win) < 20 or win[-1].t - self.recent[0].t < 290:
            return 0.0
        turnovers = sum(1 for r in win if r.type in ("interception", "recovery", "tackle"))
        passes = sum(1 for r in win if r.type == "pass" and r.outcome == "complete")
        minutes = max((win[-1].t - win[0].t) / 60, 1)
        chain = passes / max(turnovers, 1)
        return math.tanh((chain - 5.5) / 3 - (turnovers / minutes - 2.4) / 1.2)

    def _game_state(self, e: Event, new: list[Moment]) -> None:
        self._decay(e.t)
        h, a = self.threat[self.home], self.threat[self.away]
        self.momentum = (h - a) / (h + a + 0.15)
        self.control = self._control_index()

        if e.t >= self._next_sample:
            self._next_sample = e.t + 60
            self.timeline.append({"t": e.t, "minute": e.minute, **{
                "momentum": round(self.momentum, 2), "control": round(self.control, 2),
                "press_home": round(self._ppda_like(self.home), 2),
                "press_away": round(self._ppda_like(self.away), 2),
            }})

        # momentum swing: from one side's strong spell to the other's
        m = self.momentum
        if abs(m) >= 0.45 and m * self._mom_extreme < 0:
            tid = self.home if m > 0 else self.away
            if self._fire(("swing",), e.t, COOLDOWN["momentum_swing"]):
                new.append(self._moment(
                    e, "momentum_swing", tid, [], 0.6,
                    {"team": self.tname(tid),
                     # team-relative: -1 = opponent dominant, +1 = this team dominant
                     "momentum_from": round(-abs(self._mom_extreme), 2),
                     "momentum_to": round(abs(m), 2),
                     "team_xg_last_10": round(self._xg_window(tid), 2),
                     "final_third_entries_last_10": self._entries_window(tid),
                     "window_minutes": 10, "minute": e.minute},
                    [r.id for r in self.recent if r.type == "shot" and r.team == tid][-5:],
                ))
            self._mom_extreme = m
        elif abs(m) >= 0.45 and abs(m) > abs(self._mom_extreme):
            self._mom_extreme = m

        # pressing drop: compare last 10 minutes with the 10 before
        if e.type == "pass" and e.seq % 25 == 0:
            for team in (self.home, self.away):
                now = self._ppda_like(team)
                hist = self._press_hist[team]
                hist.append((e.t, now))
                while hist and e.t - hist[0][0] > 660:
                    hist.popleft()
                if hist and e.t - hist[0][0] >= 540:
                    before = hist[0][1]
                    if before >= 0.28 and now <= before * 0.6 and self._fire(("press", team), e.t, COOLDOWN["press_drop"]):
                        lead = self.score[team] - self.score[self.away if team == self.home else self.home]
                        new.append(self._moment(
                            e, "press_drop", team, [], 0.55,
                            {"team": self.tname(team), "press_before": round(before, 2),
                             "press_now": round(now, 2),
                             "drop_pct": round(100 * (1 - now / before)),
                             "goal_difference": lead, "window_minutes": 10, "minute": e.minute},
                            [r.id for r in self.recent if r.type == "pressure" and r.team == team][-5:],
                        ))

        # control vs chaos crossings
        state = 1 if self.control > 0.55 else (-1 if self.control < -0.55 else 0)
        if state != 0 and state != self._ctrl_state and self._fire(("ctrl",), e.t, COOLDOWN["control_shift"]):
            tid = self.poss_team if state == 1 else None
            win = [r for r in self.recent if self.recent[-1].t - r.t <= 300]
            new.append(self._moment(
                e, "control_shift", tid, [], 0.5,
                {"state": "control" if state == 1 else "chaos",
                 "team": self.tname(tid) if tid else "",
                 "control_index": round(self.control, 2),
                 "turnovers_last_5": sum(1 for r in win if r.type in ("interception", "recovery", "tackle")),
                 "completed_passes_last_5": sum(1 for r in win if r.type == "pass" and r.outcome == "complete"),
                 "window_minutes": 5, "minute": e.minute},
                [r.id for r in win if r.type in ("interception", "recovery", "tackle")][-5:],
            ))
        if state != 0:
            self._ctrl_state = state

    def _xg_window(self, team: str) -> float:
        return sum(r.extra["xg"] for r in self.recent if r.type == "shot" and r.team == team)

    def _entries_window(self, team: str) -> int:
        n = 0
        for r in self.recent:
            if r.type == "pass" and r.team == team and r.outcome == "complete":
                ax_s = r.x if team == self.home else 105 - r.x
                ax_e = r.end_x if team == self.home else 105 - r.end_x
                n += ax_e > 70 >= ax_s
        return n


def analyse(match: Match) -> Engine:
    eng = Engine(match)
    for e in match.events:
        eng.ingest(e)
    return eng
