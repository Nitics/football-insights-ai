"""Seeded synthetic match simulator.

Produces a football-realistic event stream (passes, carries, pressures,
tackles, interceptions, shots, restarts) for two fictional clubs. It is a
possession-chain model rather than full tracking, tuned so league-wide
averages land near real top-flight bands (see `realism.py`).

Game-state effects are built in on purpose, so the explain layer has real
stories to find: pressing fades after the hour, a leading side sits deeper
and presses less, and a trailing side pushes on.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Iterator

from .league import build_team
from .models import PITCH_LENGTH as L
from .models import PITCH_WIDTH as W
from .models import Event, Player, Team

GOAL_W = 7.32


def xg_model(ax: float, y: float, header: bool = False) -> float:
    """Distance/angle logistic xG in the attacking frame (goal at x=105)."""
    dx = max(L - ax, 0.5)
    dy = abs(y - W / 2)
    dist = math.hypot(dx, dy)
    angle = math.atan2(GOAL_W * dx, dx * dx + dy * dy - (GOAL_W / 2) ** 2)
    if angle < 0:
        angle += math.pi
    logit = -1.45 + 1.6 * angle - 0.10 * dist
    xg = 1 / (1 + math.exp(-logit))
    if header:
        xg *= 0.6
    return round(min(max(xg, 0.01), 0.95), 3)


@dataclass
class _Ball:
    team: str           # team id in possession
    holder: str         # player id
    ax: float           # attacking-frame x for the team in possession
    y: float


@dataclass
class Match:
    match_id: str
    home: Team
    away: Team
    seed: int
    events: list[Event] = field(default_factory=list)

    def team(self, tid: str) -> Team:
        return self.home if tid == self.home.id else self.away

    def opp(self, tid: str) -> Team:
        return self.away if tid == self.home.id else self.home

    def player(self, pid: str) -> Player:
        for p in self.home.players + self.away.players:
            if p.id == pid:
                return p
        raise KeyError(pid)

    def meta(self) -> dict:
        def t(team: Team) -> dict:
            return {
                "id": team.id, "name": team.name, "short": team.short, "color": team.color,
                "players": [
                    {"id": p.id, "name": p.name, "number": p.number, "position": p.position}
                    for p in team.players
                ],
            }
        return {"match_id": self.match_id, "seed": self.seed, "home": t(self.home), "away": t(self.away)}


class Simulator:
    def __init__(self, home_id: str = "KES", away_id: str = "MAR", seed: int = 7):
        self.rng = random.Random(seed)
        self.match = Match(
            match_id=f"M{seed:04d}-{home_id}-{away_id}",
            home=build_team(home_id, seed),
            away=build_team(away_id, seed),
            seed=seed,
        )
        self.t = 0.0
        self.period = 1
        self.seq = 0
        self.score = {home_id: 0, away_id: 0}

    # ---------- helpers ----------
    def _abs(self, tid: str, ax: float, y: float) -> tuple[float, float]:
        if tid == self.match.home.id:
            return round(ax, 1), round(y, 1)
        return round(L - ax, 1), round(W - y, 1)

    def _emit(self, type_: str, team: str | None = None, player: str | None = None,
              ax: float | None = None, y: float | None = None,
              end: tuple[float, float] | None = None, **kw) -> Event:
        self.seq += 1
        x = yy = ex = ey = None
        if team is not None and ax is not None:
            x, yy = self._abs(team, ax, y)
            if end is not None:
                ex, ey = self._abs(team, end[0], end[1])
        ev = Event(
            id=f"{self.match.match_id}-{self.seq:05d}", match_id=self.match.match_id,
            seq=self.seq, t=round(self.t, 1), period=self.period, type=type_,  # type: ignore[arg-type]
            team=team, player=player, x=x, y=yy, end_x=ex, end_y=ey,
            outcome=kw.pop("outcome", None), receiver=kw.pop("receiver", None), extra=kw,
        )
        self.match.events.append(ev)
        return ev

    def _pick(self, team: Team, ax: float, exclude: str | None = None, allow_gk: bool = False) -> Player:
        cands = [p for p in team.players if p.id != exclude and (allow_gk or p.position != "GK")]
        weights = [math.exp(-abs(p.base_x - ax) / 18) for p in cands]
        return self.rng.choices(cands, weights=weights)[0]

    def press_intensity(self, tid: str) -> float:
        """How hard team `tid` presses right now (game-state aware)."""
        team = self.match.team(tid)
        minute = self.t / 60
        fatigue = 1.0 if minute < 60 else max(0.6, 1.0 - (minute - 60) * 0.013)
        lead = self.score[tid] - self.score[self.match.opp(tid).id]
        state = 0.72 if lead >= 1 else (1.15 if lead <= -1 and minute > 55 else 1.0)
        return team.press * fatigue * state

    def _turnover(self, to_team: str, ax_from_attacker: float, y: float, player: Player | None = None) -> _Ball:
        team = self.match.team(to_team)
        nax, ny = L - ax_from_attacker, W - y
        holder = player or self._pick(team, nax)
        return _Ball(to_team, holder.id, nax, ny)

    def _restart(self, tid: str, ax: float, y: float, allow_gk: bool = False) -> _Ball:
        team = self.match.team(tid)
        return _Ball(tid, self._pick(team, ax, allow_gk=allow_gk).id, ax, y)

    # ---------- main loop ----------
    def run(self) -> Match:
        for period, start, kick_team in ((1, 0.0, self.match.home.id), (2, 2700.0, self.match.away.id)):
            self.period = period
            self.t = start
            end = start + 2700 + self.rng.uniform(60, 300 if period == 2 else 180)
            ball = _Ball(kick_team, self._pick(self.match.team(kick_team), 50).id, 52.5, 34.0)
            self._emit("kickoff", kick_team, ball.holder, ball.ax, ball.y)
            while self.t < end:
                ball = self._step(ball)
            self._emit("half_end" if period == 1 else "full_time", extra_score=dict(self.score))
        return self.match

    def _step(self, b: _Ball) -> _Ball:
        team = self.match.team(b.team)
        opp = self.match.opp(b.team)
        rng = self.rng

        # pressure before acting
        zone = 1.25 if b.ax < 52 else 0.85
        pressed = rng.random() < min(0.6, 0.24 * self.press_intensity(opp.id) * zone)
        if pressed:
            presser = self._pick(opp, L - b.ax)
            self._emit("pressure", opp.id, presser.id, L - b.ax, W - b.y, pressed_player=b.holder)
            self.t += rng.uniform(0.3, 1.0)

        # shot?
        central = abs(b.y - W / 2) < 20
        if b.ax > 78 and central:
            p_shot = 0.06 if b.ax < 88 else (0.14 if b.ax < 98 else 0.22)
            lead = self.score[team.id] - self.score[opp.id]
            if lead < 0 and self.t > 3300:
                p_shot *= 1.25
            if rng.random() < p_shot * team.attack:
                return self._shot(b, team, opp)

        if rng.random() < 0.82:
            return self._pass(b, team, opp, pressed)
        return self._carry(b, team, opp, pressed)

    def _pass(self, b: _Ball, team: Team, opp: Team, pressed: bool) -> _Ball:
        rng = self.rng
        dist = min(rng.lognormvariate(math.log(14), 0.55), 60)
        if rng.random() < 0.3:
            theta = rng.uniform(-math.pi, math.pi)
        else:
            theta = rng.gauss(0, 0.85)
        ex = min(max(b.ax + dist * math.cos(theta), 1), 104)
        ey = min(max(b.y + dist * math.sin(theta), 1), 67)
        dist = math.hypot(ex - b.ax, ey - b.y)
        forward = max(0.0, ex - b.ax)
        difficulty = (
            0.25 * min(dist / 40, 1) + 0.25 * min(forward / 30, 1)
            + 0.15 * (ex > 70) + 0.25 * pressed + 0.10 * (ex > 88)
        )
        difficulty = round(min(max(difficulty, 0.02), 1.0), 2)
        p_ok = min(max(0.985 - 0.62 * difficulty, 0.3), 0.985) * team.passing ** 0.5
        flight = 0.5 + dist / 18
        speed = round(dist / flight * 3.6, 1)
        receiver = self._pick(team, ex, exclude=b.holder, allow_gk=ex < 18)
        ok = rng.random() < p_ok
        self._emit(
            "pass", team.id, b.holder, b.ax, b.y, end=(ex, ey),
            outcome="complete" if ok else "incomplete",
            receiver=receiver.id if ok else None,
            distance_m=round(dist, 1), difficulty=difficulty, ball_speed_kmh=speed,
            under_pressure=pressed, progressive=forward >= 10,
        )
        self.t += 1.4 + dist / 14 + rng.uniform(0, 1.8)
        if ok:
            return _Ball(team.id, receiver.id, ex, ey)
        r = rng.random()
        if r < 0.82:
            winner = self._pick(opp, L - ex)
            kind = "interception" if r < 0.2 else "recovery"
            self._emit(kind, opp.id, winner.id, L - ex, W - ey)
            self.t += rng.uniform(0.5, 1.5)
            return _Ball(opp.id, winner.id, L - ex, W - ey)
        self._emit("out", team.id, b.holder, ex, ey, restart="throw_in")
        self.t += rng.uniform(8, 22)
        return self._restart(opp.id, L - ex, W - ey)

    def _carry(self, b: _Ball, team: Team, opp: Team, pressed: bool) -> _Ball:
        rng = self.rng
        dist = rng.uniform(3, 14)
        theta = rng.gauss(0, 0.6)
        ex = min(max(b.ax + dist * math.cos(theta), 1), 103)
        ey = min(max(b.y + dist * math.sin(theta), 1), 67)
        sprint = rng.random() < 0.07
        speed = round(rng.uniform(26, 35.5) if sprint else rng.uniform(12, 24), 1)
        p_tackle = 0.12 * self.press_intensity(opp.id) * (1.5 if pressed else 1.0)
        if rng.random() < p_tackle:
            tackler = self._pick(opp, L - b.ax)
            self._emit("carry", team.id, b.holder, b.ax, b.y, end=((b.ax + ex) / 2, (b.y + ey) / 2),
                       outcome="lost", carrier_speed_kmh=speed, distance_m=round(dist / 2, 1))
            self._emit("tackle", opp.id, tackler.id, L - b.ax, W - b.y, outcome="won",
                       tackled_player=b.holder)
            self.t += dist / (speed / 3.6) / 2 + rng.uniform(0.5, 1.5)
            return _Ball(opp.id, tackler.id, L - b.ax, W - b.y)
        self._emit("carry", team.id, b.holder, b.ax, b.y, end=(ex, ey), outcome="kept",
                   carrier_speed_kmh=speed, distance_m=round(dist, 1), sprint=sprint)
        self.t += dist / (speed / 3.6) + rng.uniform(0.3, 1.2)
        return _Ball(team.id, b.holder, ex, ey)

    def _shot(self, b: _Ball, team: Team, opp: Team) -> _Ball:
        rng = self.rng
        # Real shots cluster 10-25m out; sample range so deep possessions
        # do not all become tap-ins (cut-backs, blocked lanes, etc).
        depth = max(L - b.ax, min(rng.gammavariate(3.2, 5.2), 35))
        b = _Ball(b.team, b.holder, L - depth, W / 2 + (b.y - W / 2) * min(1, depth / 18))
        header = rng.random() < 0.2 and depth < 12
        xg = xg_model(b.ax, b.y, header)
        last_pass = next((e for e in reversed(self.match.events)
                          if e.type == "pass" and e.team == team.id), None)
        assist = last_pass.player if last_pass and last_pass.receiver == b.holder else None
        r = rng.random()
        if r < xg:
            outcome = "goal"
        else:
            outcome = rng.choices(["saved", "off_target", "blocked"], weights=[0.30, 0.45, 0.25])[0]
        speed = round(rng.uniform(55, 80) if header else rng.uniform(70, 118), 1)
        self._emit("shot", team.id, b.holder, b.ax, b.y, end=(L, W / 2 + rng.uniform(-3.5, 3.5)),
                   outcome=outcome, xg=xg, body_part="head" if header else "foot",
                   shot_speed_kmh=speed, assist=assist,
                   score_before=dict(self.score))
        if outcome == "goal":
            self.score[team.id] += 1
            self.t += rng.uniform(45, 75)
            ball = _Ball(opp.id, self._pick(opp, 50).id, 52.5, 34.0)
            self._emit("kickoff", opp.id, ball.holder, ball.ax, ball.y, score=dict(self.score))
            return ball
        if outcome == "saved":
            if rng.random() < 0.4:  # corner
                self.t += rng.uniform(20, 35)
                return self._restart(team.id, 101, rng.choice([2.0, 66.0]))
            self.t += rng.uniform(4, 10)
            gk = next(p for p in opp.players if p.position == "GK")
            return _Ball(opp.id, gk.id, 6, 34)
        if outcome == "off_target":
            self.t += rng.uniform(20, 32)
            gk = next(p for p in opp.players if p.position == "GK")
            return _Ball(opp.id, gk.id, 6, 34)
        # blocked
        self.t += rng.uniform(1, 3)
        if rng.random() < 0.5:
            return _Ball(team.id, self._pick(team, b.ax - 8).id, b.ax - 8, b.y)
        return self._turnover(opp.id, b.ax, b.y)


def simulate(home: str = "KES", away: str = "MAR", seed: int = 7) -> Match:
    return Simulator(home, away, seed).run()


def iter_events(match: Match) -> Iterator[Event]:
    yield from match.events
