# Pitchside

**Explainable, personalised match intelligence from synthetic football events.**
Built for *Inside the Game: Developer Hackathon* (Microsoft × Premier League).

All data is synthetic. The league, clubs and players are fictional.

```
 Ingest ──▶ Interpret ──▶ Explain ──▶ Render ──▶ Personalise
 sim.py      intel.py      agents.py   api.py     agents.py + web/
 seeded      stats, xG,    Analyst →   SSE feed   casual / analyst,
 event       momentum,     Commentator timed      club, player focus,
 stream      press, control → Verifier overlay    language
             key moments   → Localiser JSON
```

## What it does

- **Synthetic data engine** (`sim.py`): seeded possession-chain simulator for a fictional league. Passes, carries, pressures, tackles, interceptions, recoveries, shots, restarts, with coordinates on a 105×68 pitch, ball speed, shot speed, carrier speed and pass difficulty. Game state matters: pressing fades after the hour, leading sides sit deeper, trailing sides push.
- **Measured realism** (`realism.py`): 10 league averages checked against real top-flight bands (goals, shots, on-target %, xG, passes, pass completion, tackles, interceptions, pressures, shot speed). A test enforces it.
- **Interpret** (`intel.py`): streaming engine. Live team and player stats, xG, momentum, a control-vs-chaos index, pressing intensity, and detection of goals, big chances, momentum swings, pressing drops, control shifts, long possession spells, pass milestones and speed triggers. Each moment carries an evidence pack (facts + event IDs).
- **Explain** (`agents.py`): specialised agents with distinct roles and shared state. A **deterministic Verifier** checks every number and player name an agent writes against the evidence; failures get one retry with feedback, then fall back to a verified template. Nothing unverified reaches the screen.
- **Render** (`api.py`, `web/`): Server-Sent Events stream of events, stats and timed overlay JSON (lower third, stat bug, player tag) drawn over a 2D match view.
- **Personalise**: casual vs analyst, favourite club framing, follow-one-player mode, four languages offline (any language in Foundry mode).

## Run it

```bash
pip install -e ".[dev]"
python -m pitchside serve          # open http://localhost:8000
python -m pitchside realism        # realism report
python -m pitchside recap --seed 7 --mode analyst
python -m pitchside simulate --seed 7 --out match.jsonl
pytest
```

With no cloud settings it runs fully offline (template agents). To use LLM agents on Microsoft Foundry through Microsoft Agent Framework:

```bash
pip install -e ".[foundry]"
az login
cp .env.example .env   # fill FOUNDRY_PROJECT_ENDPOINT and FOUNDRY_MODEL
python -m pitchside serve
```

The header pill shows `agents: Foundry` when the cloud agents are active.

## API

| Endpoint | What |
|---|---|
| `GET /api/live?home=KES&away=MAR&seed=7&speed=40&mode=casual&lang=en&club=KES&player=KES-9` | SSE: `meta`, `event`, `state`, `overlay`, `recap` |
| `GET /api/recap?seed=7&mode=analyst&lang=es` | Full-time recap JSON |
| `GET /api/dataset?seed=7` | The synthetic match as JSON Lines |

## Overlay contract

```json
{"id": "ov-goal-14", "slot": "lower_third", "t_start": 51.5, "t_end": 63.5, "priority": 1.0,
 "headline": "GOAL! Zane Galloway · 1-0", "body": "...", "verified": true,
 "evidence_event_ids": ["M0007-KES-MAR-00014"], "agent_trace": [{"agent": "Verifier", "ok": true}]}
```

## Deploy

The `Dockerfile` builds a container for Azure Container Apps:

```bash
az containerapp up -n pitchside -g pitchside-rg --source . --ingress external --target-port 8000
```

## Honest limits

Event-level simulation, not full player tracking. Speed and distance figures come from the simulator. Offline analyst text is English-only beyond headlines.
