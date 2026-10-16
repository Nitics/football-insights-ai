"""CLI: python -m pitchside <command>

  simulate [--seed N] [--home KES --away MAR] [--out match.jsonl]
  realism  [--n 60]
  recap    [--seed N] [--mode analyst|casual] [--lang en|es|pt|fr]
  serve    [--port 8000]
"""
from __future__ import annotations

import argparse
import asyncio
import json


def main() -> None:
    ap = argparse.ArgumentParser(prog="pitchside")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("simulate", "recap"):
        p = sub.add_parser(name)
        p.add_argument("--seed", type=int, default=7)
        p.add_argument("--home", default="KES")
        p.add_argument("--away", default="MAR")
        p.add_argument("--mode", default="analyst")
        p.add_argument("--lang", default="en")
        p.add_argument("--out")
    r = sub.add_parser("realism")
    r.add_argument("--n", type=int, default=60)
    s = sub.add_parser("serve")
    s.add_argument("--port", type=int, default=8000)
    a = ap.parse_args()

    if a.cmd == "simulate":
        from .sim import simulate
        m = simulate(a.home, a.away, a.seed)
        lines = [json.dumps({"type": "match_meta", **m.meta()})] + [json.dumps(e.to_dict()) for e in m.events]
        if a.out:
            open(a.out, "w").write("\n".join(lines) + "\n")
            print(f"wrote {len(m.events)} events to {a.out}")
        else:
            print("\n".join(lines))
    elif a.cmd == "realism":
        from .realism import report
        for k, v in report(a.n).items():
            print(f"{k:24s} {v['mean']:>8}  band {v['band']}  {'OK' if v['ok'] else 'OUT'}")
    elif a.cmd == "recap":
        from .agents import Director
        from .intel import analyse
        from .sim import simulate
        eng = analyse(simulate(a.home, a.away, a.seed))
        out = asyncio.run(Director(eng).recap({"mode": a.mode, "lang": a.lang}))
        print(out["recap"])
        print(f"\n[source: {out['source']}]")
    elif a.cmd == "serve":
        import uvicorn
        uvicorn.run("pitchside.api:app", host="0.0.0.0", port=a.port)


if __name__ == "__main__":
    main()
