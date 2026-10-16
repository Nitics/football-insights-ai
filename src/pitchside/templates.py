"""Offline 'brain': deterministic templates with the same interface as the
LLM agents. Lets the whole pipeline run with no cloud access (dev, tests,
CI, and as the verified fallback when a model output fails the checker).
Every number comes straight from the moment's facts.
"""
from __future__ import annotations

from .models import Moment

LANGS = {"en": "English", "es": "Español", "pt": "Português", "fr": "Français"}

HEAD = {
    "en": {
        "goal": "GOAL! {scorer} · {score_home}-{score_away}",
        "big_chance": "Big chance · {player}",
        "momentum_swing": "{team} seize momentum",
        "press_drop": "{team} stop pressing",
        "control": "{team} take control",
        "chaos": "Game turns chaotic",
        "possession_spell": "{passes}-pass spell · {team}",
        "milestone": "{player} · {completed_passes} passes",
        "speed_trigger": "{player} · {speed_kmh} km/h",
    },
    "es": {
        "goal": "¡GOL! {scorer} · {score_home}-{score_away}",
        "big_chance": "Ocasión clara · {player}",
        "momentum_swing": "{team} toma el impulso",
        "press_drop": "{team} deja de presionar",
        "control": "{team} toma el control",
        "chaos": "El partido se rompe",
        "possession_spell": "{passes} pases seguidos · {team}",
        "milestone": "{player} · {completed_passes} pases",
        "speed_trigger": "{player} · {speed_kmh} km/h",
    },
    "pt": {
        "goal": "GOL! {scorer} · {score_home}-{score_away}",
        "big_chance": "Chance clara · {player}",
        "momentum_swing": "{team} assume o domínio",
        "press_drop": "{team} para de pressionar",
        "control": "{team} assume o controle",
        "chaos": "Jogo fica caótico",
        "possession_spell": "{passes} passes seguidos · {team}",
        "milestone": "{player} · {completed_passes} passes",
        "speed_trigger": "{player} · {speed_kmh} km/h",
    },
    "fr": {
        "goal": "BUT ! {scorer} · {score_home}-{score_away}",
        "big_chance": "Grosse occasion · {player}",
        "momentum_swing": "{team} prend l'ascendant",
        "press_drop": "{team} arrête de presser",
        "control": "{team} prend le contrôle",
        "chaos": "Le match s'emballe",
        "possession_spell": "{passes} passes d'affilée · {team}",
        "milestone": "{player} · {completed_passes} passes",
        "speed_trigger": "{player} · {speed_kmh} km/h",
    },
}

CASUAL = {
    "en": {
        "goal": "{scorer} scores for {team}! It's {score_home}-{score_away}.",
        "big_chance": "{player} really should have scored there.",
        "momentum_swing": "{team} are on top now and pushing forward.",
        "press_drop": "{team} have stopped chasing the ball, so their opponents have more time.",
        "control": "{team} are keeping the ball and calling the tune.",
        "chaos": "End to end now: nobody can keep the ball.",
        "possession_spell": "{team} kept the ball for {passes} passes in a row.",
        "milestone": "{player} is running the show with {completed_passes} passes.",
        "speed_trigger": "{player} flies past at {speed_kmh} km/h!",
    },
    "es": {
        "goal": "¡Marca {scorer} para {team}! {score_home}-{score_away}.",
        "big_chance": "{player} tuvo que marcar ahí.",
        "momentum_swing": "{team} manda ahora y empuja hacia arriba.",
        "press_drop": "{team} ya no presiona y el rival tiene más tiempo.",
        "control": "{team} tiene el balón y marca el ritmo.",
        "chaos": "Ida y vuelta: nadie retiene el balón.",
        "possession_spell": "{team} encadenó {passes} pases seguidos.",
        "milestone": "{player} lleva {completed_passes} pases: el que dirige.",
        "speed_trigger": "¡{player} vuela a {speed_kmh} km/h!",
    },
    "pt": {
        "goal": "{scorer} marca para o {team}! {score_home}-{score_away}.",
        "big_chance": "{player} tinha que ter marcado.",
        "momentum_swing": "{team} domina agora e vai para cima.",
        "press_drop": "{team} parou de pressionar e o rival ganha tempo.",
        "control": "{team} fica com a bola e dita o ritmo.",
        "chaos": "Lá e cá: ninguém segura a bola.",
        "possession_spell": "{team} trocou {passes} passes seguidos.",
        "milestone": "{player} já tem {completed_passes} passes: é o maestro.",
        "speed_trigger": "{player} voa a {speed_kmh} km/h!",
    },
    "fr": {
        "goal": "{scorer} marque pour {team} ! {score_home}-{score_away}.",
        "big_chance": "{player} devait marquer là.",
        "momentum_swing": "{team} domine et pousse maintenant.",
        "press_drop": "{team} ne presse plus : l'adversaire respire.",
        "control": "{team} garde le ballon et dicte le tempo.",
        "chaos": "Ça va d'un but à l'autre : personne ne garde le ballon.",
        "possession_spell": "{team} a enchaîné {passes} passes.",
        "milestone": "{player} compte déjà {completed_passes} passes : le chef d'orchestre.",
        "speed_trigger": "{player} file à {speed_kmh} km/h !",
    },
}

YOUR_TEAM = {"en": "Your team · ", "es": "Tu equipo · ", "pt": "Seu time · ", "fr": "Ton équipe · "}
DANGER = {"en": "Danger · ", "es": "Peligro · ", "pt": "Perigo · ", "fr": "Danger · "}


def key(m: Moment) -> str:
    return m.facts.get("state", m.kind) if m.kind == "control_shift" else m.kind


def fmt(tpl: str, facts: dict) -> str:
    safe = {k: ("" if v is None else v) for k, v in facts.items()}
    return tpl.format(**safe)


def analyst_why(m: Moment) -> str:
    f = m.facts
    k = key(m)
    if k == "goal":
        parts = [f"{f['scorer']} finished from {f['distance_m']}m with a chance worth {f['xg']} xG"
                 + (f", set up by {f['assist']}." if f["assist"] else ".")]
        if f["xg"] < 0.1:
            parts.append("That is a low-percentage finish: individual quality, not chance volume.")
        elif f["xg"] >= 0.35:
            parts.append("The build-up created a high-quality look; this was coming.")
        if f["passes_in_move"] >= 6:
            parts.append(f"It ended a {f['passes_in_move']}-pass move.")
        elif f["passes_in_move"] <= 1:
            parts.append("It came from a direct attack rather than sustained pressure.")
        if f["momentum_for_team_before"] <= -0.3:
            parts.append("It came against the run of play.")
        if f["team_xg_total"] < f["opponent_xg_total"]:
            parts.append(f"{f['team']} still trail on xG, {f['team_xg_total']} to {f['opponent_xg_total']}.")
        return " ".join(parts)
    if k == "big_chance":
        verb = {"saved": "was denied by the keeper", "off_target": "missed the target",
                "blocked": "was blocked"}.get(f["outcome"], "could not convert")
        return (f"{f['player']} {verb} from {f['distance_m']}m. Chances like that are scored "
                f"about {round(f['xg'] * 100)}% of the time ({f['xg']} xG), so this is a big let-off.")
    if k == "momentum_swing":
        return (f"{f['team']} have flipped the game: their momentum moved from {f['momentum_from']} to "
                f"{f['momentum_to']}, built on {f['final_third_entries_last_10']} final-third entries "
                f"and {f['team_xg_last_10']} xG in the last 10 minutes.")
    if k == "press_drop":
        why = ("Protecting a lead, they are sitting deeper." if f["goal_difference"] > 0
               else "Fatigue is the likely cause after the hour." if f["minute"] >= 60
               else "The opponent now gets time on the ball to build.")
        return (f"{f['team']}'s pressing is down {f['drop_pct']}%: {f['press_before']} pressures per "
                f"opponent pass a few minutes ago, {f['press_now']} now. {why}")
    if k == "control":
        return (f"{f['team']} have taken control: {f['completed_passes_last_5']} completed passes against "
                f"just {f['turnovers_last_5']} turnovers in the last 5 minutes.")
    if k == "chaos":
        return (f"The game has broken up: {f['turnovers_last_5']} turnovers in 5 minutes. Transitions, "
                f"not structure, will decide the next chance.")
    if k == "possession_spell":
        return (f"{f['team']} kept the ball for {f['passes']} straight passes, {f['players_involved']} "
                f"players involved over {f['seconds']} seconds, pulling the opposition shape around.")
    if k == "milestone":
        return (f"{f['player']} has completed {f['completed_passes']} passes at {f['pass_accuracy']}% "
                f"accuracy: the hub of {f['team']}'s build-up.")
    if k == "speed_trigger":
        return (f"{f['player']} hit {f['speed_kmh']} km/h on a carry: top-end pace that stretches "
                f"the back line.")
    return ""


def headline(m: Moment, lang: str = "en") -> str:
    return fmt(HEAD.get(lang, HEAD["en"])[key(m)], m.facts)


def casual(m: Moment, lang: str = "en") -> str:
    return fmt(CASUAL.get(lang, CASUAL["en"])[key(m)], m.facts)


def personalise(m: Moment, why: str, persona: dict, team_name_of_fav: str | None) -> tuple[str, str]:
    lang = persona.get("lang", "en") if persona.get("lang") in LANGS else "en"
    head = headline(m, lang)
    body = why if persona.get("mode") == "analyst" else casual(m, lang)
    if persona.get("mode") == "analyst" and lang != "en":
        body = casual(m, lang) + " " + why   # offline analyst detail is English-only
    team = m.facts.get("team")
    if team_name_of_fav and team:
        if team == team_name_of_fav:
            head = YOUR_TEAM.get(lang, "") + head
        elif m.kind in ("goal", "big_chance", "momentum_swing"):
            head = DANGER.get(lang, "") + head
    return head, body


def recap(home: str, away: str, snap: dict, moments: list[Moment], persona: dict) -> str:
    th, ta = snap["teams"].values()
    sh, sa = snap["score"].values()
    goals = [m for m in moments if m.kind == "goal"]
    lines = [f"{home} {sh}-{sa} {away}."]
    if goals:
        lines.append("Goals: " + ", ".join(f"{g.facts['scorer']} {g.minute}'" for g in goals) + ".")
    xg_note = f"on expected goals it finished {th['xg']} to {ta['xg']}"
    winner_xg = home if th["xg"] > ta["xg"] else away
    winner = home if sh > sa else away if sa > sh else None
    if winner and abs(sh - sa) >= 2 and abs(th["xg"] - ta["xg"]) < 0.6:
        lines.append(f"The scoreline flatters {winner}: {xg_note}. Finishing, not chance creation, decided it.")
    elif winner and winner != winner_xg:
        lines.append(f"Against the balance of play: {xg_note}, so {winner_xg} made the better chances.")
    else:
        lines.append(f"Deserved on the chances: {xg_note}.")
    key_moments = sorted((m for m in moments if m.kind not in ("goal", "milestone", "speed_trigger")),
                         key=lambda m: -m.importance)[:3]
    for m in sorted(key_moments, key=lambda m: m.t):
        lines.append(f"{m.minute}': {analyst_why(m)}")
    pp = snap["possession_pct"]
    lines.append(f"Possession {list(pp.values())[0]}-{list(pp.values())[1]}; passing accuracy "
                 f"{th['pass_accuracy']}% vs {ta['pass_accuracy']}%.")
    if persona.get("mode") != "analyst":
        lines = lines[:3] + [casual(m, "en") for m in key_moments[:2]]
    return "\n".join(lines)
