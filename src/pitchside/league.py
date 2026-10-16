"""A small fictional league. No real clubs, players, crests or marks."""
from __future__ import annotations

import random

from .models import Player, Team

CLUBS = [
    # id, name, short, colour, attack, passing, press
    ("KES", "Kestrel Vale", "KES", "#1f6feb", 1.10, 1.05, 1.15),
    ("MAR", "Marrowgate Athletic", "MAR", "#d1242f", 1.00, 0.97, 0.95),
    ("DUN", "Duncairn Harbour", "DUN", "#1a7f37", 0.95, 1.08, 0.90),
    ("HAL", "Halloway Forge", "HAL", "#bf8700", 1.05, 0.95, 1.10),
    ("SOL", "Solway Mills", "SOL", "#8250df", 0.90, 1.00, 1.00),
    ("TRE", "Tremont Quay", "TRE", "#0b7285", 1.00, 1.02, 1.05),
]

FIRST = [
    "Alex", "Bruno", "Callum", "Dario", "Emeka", "Felix", "Goran", "Hugo", "Idris",
    "Jonas", "Kofi", "Luca", "Mateo", "Nils", "Oskar", "Pablo", "Quentin", "Rafael",
    "Sipho", "Tomas", "Ugo", "Viktor", "Wes", "Yannick", "Zane", "Thabo", "Rui",
    "Ilan", "Arto", "Ben", "Cian", "Davi", "Elias", "Finn", "Gael", "Hamza",
]
LAST = [
    "Ashby", "Brennick", "Corvale", "Dunmore", "Elstrand", "Farrow", "Galloway",
    "Hartwell", "Ivers", "Jessop", "Kerrigan", "Lindqvist", "Morcombe", "Nakamura",
    "Okonedo", "Pemberly", "Quarry", "Rendell", "Salvay", "Thornbury", "Underhill",
    "Vasquell", "Wexley", "Yarrow", "Zelenko", "Mokoena", "Adebayo", "Brandt",
    "Castellan", "Duarte", "Eklund", "Fenwick", "Grieve", "Holloway", "Ibarra",
]

# (position, typical depth in own attacking frame, y-centre)
SHAPE_433 = [
    ("GK", 5), ("DF", 25), ("DF", 25), ("DF", 25), ("DF", 25),
    ("MF", 48), ("MF", 52), ("MF", 55), ("FW", 75), ("FW", 82), ("FW", 75),
]
NUMBERS = [1, 2, 5, 6, 3, 8, 4, 10, 7, 9, 11]


def build_team(club_id: str, seed: int = 0) -> Team:
    row = next(c for c in CLUBS if c[0] == club_id)
    cid, name, short, colour, att, pas, prs = row
    rng = random.Random(f"{cid}-{seed}")
    firsts = rng.sample(FIRST, 11)
    lasts = rng.sample(LAST, 11)
    players = [
        Player(
            id=f"{cid}-{NUMBERS[i]}",
            name=f"{firsts[i]} {lasts[i]}",
            number=NUMBERS[i],
            position=pos,
            base_x=depth,
            team=cid,
        )
        for i, (pos, depth) in enumerate(SHAPE_433)
    ]
    return Team(cid, name, short, colour, players, att, pas, prs)


def club_ids() -> list[str]:
    return [c[0] for c in CLUBS]
