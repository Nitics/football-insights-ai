"""Render: FastAPI service that streams a match live (Server-Sent Events)
with stats, game state and verified, personalised overlays.

  GET /api/live    -> SSE: meta, event, state, overlay, recap
  GET /api/recap   -> full-time recap JSON for a persona
  GET /api/dataset -> the synthetic match as JSON Lines (data innovation)
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, PlainTextResponse, StreamingResponse

from .agents import Director
from .intel import Engine, analyse
from .league import CLUBS
from .sim import simulate

app = FastAPI(title="Pitchside", version="0.1.0")
WEB = Path(__file__).resolve().parents[2] / "web"


def _persona(mode: str, lang: str, club: str | None, player: str | None) -> dict:
    p = {"mode": mode, "lang": lang}
    if club:
        p["club"] = club
    if player:
        p["player"] = player
    return p


def _sse(kind: str, data) -> str:
    return f"event: {kind}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.get("/")
def index():
    return FileResponse(WEB / "index.html")


@app.get("/healthz")
def health():
    return {"ok": True}


@app.get("/api/clubs")
def clubs():
    return [{"id": c[0], "name": c[1], "color": c[3]} for c in CLUBS]


@app.get("/api/live")
async def live(home: str = "KES", away: str = "MAR", seed: int = 7, speed: float = 40,
               mode: str = "casual", lang: str = "en", club: str | None = None,
               player: str | None = None):
    match = simulate(home, away, seed)
    persona = _persona(mode, lang, club, player)

    async def gen():
        eng = Engine(match)
        director = Director(eng)
        yield _sse("meta", {**match.meta(), "persona": persona, "brain": director.mode})
        prev_t = 0.0
        for i, e in enumerate(match.events):
            gap = max(0.0, e.t - prev_t) if e.t >= prev_t else 0.0
            prev_t = e.t
            await asyncio.sleep(min(gap / speed, 1.5))
            moments = eng.ingest(e)
            yield _sse("event", {k: v for k, v in e.to_dict().items() if k != "match_id"})
            if i % 15 == 0 or moments or e.type in ("shot", "half_end", "full_time"):
                st = eng.snapshot()
                if player:
                    st["focus_player"] = {"id": player, **eng.player_view(player)}
                st["minute"] = e.minute
                st["period"] = e.period
                yield _sse("state", st)
            for m in moments:
                ov = await director.overlay(m, persona)
                if ov:
                    yield _sse("overlay", ov.to_dict())
        yield _sse("recap", await director.recap(persona))

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/recap")
async def recap(home: str = "KES", away: str = "MAR", seed: int = 7, mode: str = "analyst",
                lang: str = "en", club: str | None = None):
    eng = analyse(simulate(home, away, seed))
    return await Director(eng).recap(_persona(mode, lang, club, None))


@app.get("/api/dataset", response_class=PlainTextResponse)
def dataset(home: str = "KES", away: str = "MAR", seed: int = 7):
    m = simulate(home, away, seed)
    lines = [json.dumps({"type": "match_meta", **m.meta()})]
    lines += [json.dumps(e.to_dict()) for e in m.events]
    return "\n".join(lines)
