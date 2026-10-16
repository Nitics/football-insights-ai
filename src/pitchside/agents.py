"""Explain + Personalise: the multi-agent layer.

Roles (each a separate Microsoft Agent Framework agent in cloud mode):
  - Director        : decides which moments deserve screen time, for whom,
                      in which graphic slot (code; owns the shared state)
  - TacticalAnalyst : explains WHY a moment matters, from the evidence pack
  - Commentator     : turns that into a short broadcast headline + caption
  - Verifier        : deterministic fact-check of every number and name
  - Localiser       : rewrites for a persona (analyst/casual, club, language)
  - RecapWriter     : full-time recap from the moments + final stats

Shared state is the `MomentCard` cache: analysis is done once per moment and
reused by every persona. If a model output fails verification the agent
gets one retry with the verifier's notes; if it fails again the Director
falls back to the deterministic template, so the screen never shows an
unverified claim.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import time
from dataclasses import dataclass, field

from . import templates as T
from .intel import Engine
from .models import Moment, Overlay
from .verifier import verify

SLOT = {
    "goal": ("lower_third", 12), "big_chance": ("lower_third", 9),
    "momentum_swing": ("stat_bug", 10), "press_drop": ("lower_third", 10),
    "control_shift": ("stat_bug", 8), "possession_spell": ("lower_third", 8),
    "milestone": ("player_tag", 6), "speed_trigger": ("player_tag", 5),
}

ANALYST_PROMPT = """You are the Tactical Analyst on a live football broadcast.
You receive an evidence pack (JSON) about one detected match moment.
Explain in 1-3 sentences WHY it matters (tactics, game state, rhythm, control vs chaos),
not just what happened. Use ONLY numbers and names present in the evidence.
Never invent players, stats or history. Return JSON: {"why": "..."}"""

COMMENTATOR_PROMPT = """You are a broadcast graphics writer. Given an evidence pack and the
analyst's explanation, write a lower-third: a headline (max 48 characters) and a caption
(max 130 characters). Energetic but factual. Use ONLY numbers and names in the evidence.
Return JSON: {"headline": "...", "caption": "..."}"""

LOCALISER_PROMPT = """You adapt broadcast graphics for one viewer.
Persona fields: mode ("analyst" = keep the numbers and the tactical why; "casual" = plain words,
at most one number), favourite_club (address them as their team if it is the moment's team),
language (write entirely in that language, natural sports register).
Keep every number exactly as given; do not add new numbers or names.
Return JSON: {"headline": "...", "body": "..."}"""

RECAP_PROMPT = """You write the full-time recap for a football broadcast. You get final stats and
the key moments (each with evidence). Write 4-7 sentences: result, how the game was decided,
the tactical turning points and why they mattered, standout player. Use ONLY the numbers and
names provided. Match the persona's mode and language. Return JSON: {"recap": "..."}"""


@dataclass
class MomentCard:
    """Shared state for one moment, built once and reused across personas."""
    moment: Moment
    why: str = ""
    headline: str = ""
    caption: str = ""
    verified: bool = False
    source: str = "template"
    trace: list[dict] = field(default_factory=list)
    personalised: dict[str, tuple[str, str, bool]] = field(default_factory=dict)


def _json(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("no JSON in model output")
    return json.loads(m.group(0))


class FoundryBrain:
    """LLM agents on Microsoft Foundry via Microsoft Agent Framework."""

    def __init__(self):
        from agent_framework import Agent
        from agent_framework.foundry import FoundryChatClient
        from azure.identity import DefaultAzureCredential

        client = FoundryChatClient(credential=DefaultAzureCredential())  # reads FOUNDRY_* env
        self.analyst = Agent(client=client, name="TacticalAnalyst", instructions=ANALYST_PROMPT)
        self.commentator = Agent(client=client, name="Commentator", instructions=COMMENTATOR_PROMPT)
        self.localiser = Agent(client=client, name="Localiser", instructions=LOCALISER_PROMPT)
        self.recapper = Agent(client=client, name="RecapWriter", instructions=RECAP_PROMPT)

    async def ask(self, agent, payload: dict) -> dict:
        res = await agent.run(json.dumps(payload, ensure_ascii=False))
        return _json(res.text)


class Director:
    def __init__(self, engine: Engine, use_llm: bool | None = None):
        self.engine = engine
        self.cards: dict[str, MomentCard] = {}
        self.squad = [p.name for p in engine.match.home.players + engine.match.away.players]
        if use_llm is None:
            use_llm = bool(os.getenv("FOUNDRY_PROJECT_ENDPOINT"))
        self.brain = FoundryBrain() if use_llm else None
        self.mode = "foundry" if self.brain else "offline"
        self._last_slot_t: dict[str, float] = {}

    # ---------- selection ----------
    def wants(self, m: Moment, persona: dict) -> bool:
        focus = persona.get("player")
        if focus:
            return focus in m.players or m.kind in ("goal",)
        if persona.get("mode") == "casual":
            return m.importance >= 0.45
        return True

    def _team_name(self, club_id: str | None) -> str | None:
        if not club_id:
            return None
        try:
            return self.engine.match.team(club_id).name if club_id in (
                self.engine.match.home.id, self.engine.match.away.id) else None
        except Exception:
            return None

    # ---------- the pipeline ----------
    async def card(self, m: Moment) -> MomentCard:
        if m.id in self.cards:
            return self.cards[m.id]
        c = MomentCard(m)
        self.cards[m.id] = c
        if self.brain:
            await self._llm_card(c)
        if not c.verified:
            self._template_card(c)
        return c

    def _template_card(self, c: MomentCard) -> None:
        t0 = time.perf_counter()
        c.why = T.analyst_why(c.moment)
        c.headline = T.headline(c.moment)
        c.caption = T.casual(c.moment)
        v = verify(f"{c.why} {c.headline} {c.caption}", c.moment, self.squad)
        c.verified, c.source = v.ok, "template"
        c.trace.append({"agent": "Template", "ms": round(1000 * (time.perf_counter() - t0), 1),
                        "ok": v.ok, "note": v.note()})

    async def _llm_card(self, c: MomentCard) -> None:
        pack = {"kind": c.moment.kind, "minute": c.moment.minute, "facts": c.moment.facts,
                "game_state": {k: v for k, v in self.engine.snapshot().items() if k != "teams"}}
        feedback = None
        for attempt in (1, 2):
            try:
                t0 = time.perf_counter()
                a = await self.brain.ask(self.brain.analyst, {**pack, "verifier_feedback": feedback})
                c.trace.append({"agent": "TacticalAnalyst", "ms": round(1000 * (time.perf_counter() - t0)),
                                "ok": True, "note": f"attempt {attempt}"})
                t0 = time.perf_counter()
                b = await self.brain.ask(self.brain.commentator, {**pack, "why": a["why"],
                                                                 "verifier_feedback": feedback})
                c.trace.append({"agent": "Commentator", "ms": round(1000 * (time.perf_counter() - t0)),
                                "ok": True, "note": f"attempt {attempt}"})
            except Exception as ex:  # network, auth, bad JSON: recover via template
                c.trace.append({"agent": "Director", "ms": 0, "ok": False, "note": f"model error: {ex}"})
                return
            v = verify(f"{a['why']} {b['headline']} {b['caption']}", c.moment, self.squad,
                       extra=self.engine.snapshot()["score"])
            c.trace.append({"agent": "Verifier", "ms": 0, "ok": v.ok, "note": v.note()})
            if v.ok:
                c.why, c.headline, c.caption = a["why"], b["headline"], b["caption"]
                c.verified, c.source = True, "foundry"
                return
            feedback = v.problems
        c.trace.append({"agent": "Director", "ms": 0, "ok": False,
                        "note": "falling back to verified template"})

    async def personalise(self, c: MomentCard, persona: dict) -> tuple[str, str, bool]:
        pkey = json.dumps(persona, sort_keys=True)
        if pkey in c.personalised:
            return c.personalised[pkey]
        fav = self._team_name(persona.get("club"))
        out = None
        if self.brain and c.source == "foundry":
            try:
                t0 = time.perf_counter()
                r = await self.brain.ask(self.brain.localiser, {
                    "persona": {"mode": persona.get("mode", "casual"), "favourite_club": fav,
                                "language": T.LANGS.get(persona.get("lang", "en"), persona.get("lang", "en"))},
                    "facts": c.moment.facts, "headline": c.headline, "caption": c.caption, "why": c.why})
                v = verify(f"{r['headline']} {r['body']}", c.moment, self.squad)
                c.trace.append({"agent": "Localiser", "ms": round(1000 * (time.perf_counter() - t0)),
                                "ok": v.ok, "note": v.note()})
                if v.ok:
                    out = (r["headline"], r["body"], True)
            except Exception as ex:
                c.trace.append({"agent": "Localiser", "ms": 0, "ok": False, "note": str(ex)})
        if out is None:
            h, b = T.personalise(c.moment, c.why, persona, fav)
            out = (h, b, verify(f"{h} {b}", c.moment, self.squad).ok)
        c.personalised[pkey] = out
        return out

    async def overlay(self, m: Moment, persona: dict) -> Overlay | None:
        if not self.wants(m, persona):
            return None
        slot, dur = SLOT[m.kind]
        c = await self.card(m)
        head, body, ok = await self.personalise(c, persona)
        return Overlay(
            id=f"ov-{m.id}", moment_id=m.id, slot=slot, t_start=m.t, t_end=m.t + dur,
            priority=m.importance, headline=head, body=body, persona=persona,
            verified=ok and c.verified, evidence_event_ids=m.event_ids, agent_trace=list(c.trace),
        )

    async def recap(self, persona: dict) -> dict:
        eng = self.engine
        snap = eng.snapshot()
        home, away = eng.match.home.name, eng.match.away.name
        moments = eng.moments
        text, source, ok = None, "template", True
        if self.brain:
            try:
                key = sorted(moments, key=lambda m: -m.importance)[:8]
                r = await self.brain.ask(self.brain.recapper, {
                    "home": home, "away": away, "final": snap,
                    "moments": [{"minute": m.minute, "kind": m.kind, "facts": m.facts} for m in key],
                    "persona": persona})
                merged = Moment("recap", 0, "goal", None, [], 0, {
                    **{f"{k}_{i}": v for i, m in enumerate(key) for k, v in m.facts.items()},
                    **{f"{t}_{k}": v for t, s in snap["teams"].items() for k, v in s.items()},
                    **{f"poss_{k}": v for k, v in snap["possession_pct"].items()},
                    **{f"score_{k}": v for k, v in snap["score"].items()},
                    "home": home, "away": away,
                }, [])
                v = verify(r["recap"], merged, self.squad)
                if v.ok:
                    text, source = r["recap"], "foundry"
            except Exception:
                pass
        if text is None:
            text = T.recap(home, away, snap, moments, persona)
        return {"recap": text, "source": source, "verified": ok, "final": snap,
                "timeline": eng.timeline,
                "moments": [m.to_dict() for m in sorted(moments, key=lambda m: m.t)
                            if m.kind != "milestone"]}


async def run_match_offline(engine: Engine, persona: dict) -> list[Overlay]:
    d = Director(engine, use_llm=False)
    out = []
    for m in engine.moments:
        o = await d.overlay(m, persona)
        if o:
            out.append(o)
    return out


def run(coro):
    return asyncio.run(coro)
