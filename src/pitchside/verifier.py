"""Deterministic fact-checker. A model cannot mark its own homework, so
every generated line is checked in code before it can reach the screen.

Rules:
1. Every number in the text must come from the moment's evidence facts
   (in any common rounding/percentage form) or the live score.
2. Any player name from either squad that appears must be in the evidence.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .models import Moment

NUM = re.compile(r"(?<![\w.])(\d+(?:[.,]\d+)?)(?!\d)")


def _forms(v) -> set[str]:
    out: set[str] = set()
    if isinstance(v, bool) or v is None:
        return out
    if isinstance(v, (int, float)):
        f = float(v)
        out.add(str(v))
        for d in (0, 1, 2):
            s = f"{f:.{d}f}"
            out.add(s)
            out.add(s.rstrip("0").rstrip(".") if "." in s else s)
        out.add(str(abs(int(round(f)))))
        out.add(f"{abs(f):.2f}".rstrip("0").rstrip("."))
        if 0 <= f <= 1:  # probabilities -> percentages
            out.add(str(round(f * 100)))
        out.add(str(abs(round(f))))
    elif isinstance(v, str):
        out |= set(NUM.findall(v))
    return {o.replace(",", ".") for o in out}


@dataclass
class Verdict:
    ok: bool
    problems: list[str] = field(default_factory=list)

    def note(self) -> str:
        return "; ".join(self.problems) if self.problems else "all claims grounded"


def allowed_numbers(moment: Moment, extra: dict | None = None) -> set[str]:
    allowed: set[str] = set()
    for v in list(moment.facts.values()) + list((extra or {}).values()):
        allowed |= _forms(v)
    return allowed


def verify(text: str, moment: Moment, squad_names: list[str], extra: dict | None = None) -> Verdict:
    problems: list[str] = []
    allowed = allowed_numbers(moment, extra)
    for raw in NUM.findall(text):
        n = raw.replace(",", ".")
        if n not in allowed and n.rstrip("0").rstrip(".") not in allowed:
            problems.append(f"unsupported number '{raw}'")
    fact_text = " ".join(str(v) for v in moment.facts.values())
    for name in squad_names:
        if name in text and name not in fact_text:
            problems.append(f"player '{name}' not in evidence")
        else:
            surname = name.split()[-1]
            if re.search(rf"\b{re.escape(surname)}\b", text) and surname not in fact_text:
                problems.append(f"player '{surname}' not in evidence")
    return Verdict(ok=not problems, problems=sorted(set(problems)))
