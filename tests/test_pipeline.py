import asyncio

from pitchside.agents import Director
from pitchside.intel import analyse
from pitchside.models import Moment
from pitchside.realism import report
from pitchside.sim import simulate, xg_model
from pitchside.verifier import verify


def test_simulation_is_deterministic():
    a, b = simulate("KES", "MAR", 3), simulate("KES", "MAR", 3)
    assert [e.to_dict() for e in a.events] == [e.to_dict() for e in b.events]


def test_league_averages_inside_real_bands():
    bad = {k: v for k, v in report(40).items() if not v["ok"]}
    assert not bad, bad


def test_xg_model_is_sane():
    assert xg_model(94, 34) > xg_model(80, 34) > xg_model(80, 5)
    assert 0.6 < xg_model(103, 34) <= 0.95


def test_score_matches_goal_events():
    m = simulate("HAL", "SOL", 11)
    eng = analyse(m)
    goals = [e for e in m.events if e.type == "shot" and e.outcome == "goal"]
    assert sum(eng.snapshot()["score"].values()) == len(goals)
    assert len([x for x in eng.moments if x.kind == "goal"]) == len(goals)


def test_every_moment_has_evidence():
    eng = analyse(simulate("KES", "DUN", 5))
    assert eng.moments
    for m in eng.moments:
        assert m.event_ids or m.kind in ("momentum_swing", "press_drop", "control_shift")
        assert "minute" in m.facts


def test_verifier_blocks_invented_numbers_and_players():
    m = Moment("x", 600, "goal", "KES", ["KES-9"], 1.0,
               {"scorer": "Luca Brandt", "xg": 0.31, "minute": 11, "score_home": 1, "score_away": 0}, [])
    squad = ["Luca Brandt", "Hugo Farrow"]
    assert verify("Luca Brandt scores, 1-0, a 31% chance (0.31 xG).", m, squad).ok
    assert not verify("Luca Brandt's 14th goal of the season.", m, squad).ok
    assert not verify("Farrow set it up.", m, squad).ok


def test_offline_overlays_are_all_verified_in_every_language():
    eng = analyse(simulate("KES", "MAR", 7))
    d = Director(eng, use_llm=False)

    async def go():
        out = []
        for lang in ("en", "es", "pt", "fr"):
            for mode in ("casual", "analyst"):
                for m in eng.moments:
                    o = await d.overlay(m, {"mode": mode, "lang": lang, "club": "KES"})
                    if o:
                        out.append(o)
        return out

    ovs = asyncio.run(go())
    assert ovs and all(o.verified for o in ovs)


def test_player_focus_mode_only_shows_that_player_or_goals():
    eng = analyse(simulate("KES", "MAR", 7))
    d = Director(eng, use_llm=False)
    pid = "KES-10"
    persona = {"mode": "casual", "lang": "en", "player": pid}
    for m in eng.moments:
        if d.wants(m, persona):
            assert pid in m.players or m.kind == "goal"
