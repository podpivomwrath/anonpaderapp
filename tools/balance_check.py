"""Ночная проверка баланса (2026-10-21): симулятор на настоящих движках боя
против коридоров. Вышел подкласс из коридора - весть администратору, но
только когда картина поменялась с прошлой ночи, чтобы не повторять одно и то же.

Коридоры - из tools/sim_balance.py::scorecard: дуэль у ДД 35-70%, у танка и
хилера 10-35% (их сила - в группе); соло против двух мобов у ДД от 40%,
у остальных от 25%. Числа - сравнение подклассов при равных вещах, а не
предсказание живых боёв (ИИ симулятора ровнее человека).

Запуск: python tools/balance_check.py [--rounds 24] [--notify]
По крону на сервере: docker compose -f docker-compose.prod.yml exec -T bot python tools/balance_check.py --notify
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

from tools import sim_balance as sb  # noqa: E402
from game.classes.base import REGISTRY  # noqa: E402

LEVEL = 50
DUEL = {"dd": (0.35, 0.70), "support": (0.35, 0.70), "tank": (0.10, 0.35), "healer": (0.10, 0.35)}
SOLO_MIN = {"dd": 0.40, "support": 0.25, "tank": 0.25, "healer": 0.25}
STATE_FILE = Path("/app/logs/balance_check.json")


def measure(rounds: int, rng: random.Random) -> dict[str, dict]:
    subs = list(REGISTRY)
    mixed = {s: sb.modifiers_for(sb.preset_variants(s).get("смешанный", [])) for s in subs}
    duel = sb.duel_tournament([(s, "x", mixed[s]) for s in subs], LEVEL, rounds, rng)
    out = {}
    for sub in subs:
        solo = sb.solo_pve(sub, LEVEL, mixed[sub], rounds, rng, "двое")
        out[sub] = {"duel": duel[(sub, "x")], "solo": solo["winrate"]}
    return out


def verdict(results: dict[str, dict]) -> list[str]:
    problems = []
    for sub, r in results.items():
        role = REGISTRY[sub].natural_role.value
        lo, hi = DUEL[role]
        title = REGISTRY[sub].title
        if not lo <= r["duel"] <= hi:
            problems.append(f"{title}: дуэль {r['duel']:.0%} (коридор {lo:.0%}-{hi:.0%})")
        if r["solo"] < SOLO_MIN[role]:
            problems.append(f"{title}: соло против двоих {r['solo']:.0%} (нужно от {SOLO_MIN[role]:.0%})")
    return problems


async def notify(text: str) -> None:
    from vkbottle import API

    from config import get_settings

    settings = get_settings()
    if settings.admin_vk_id and settings.vk_token:
        await API(settings.vk_token).messages.send(peer_id=settings.admin_vk_id, random_id=0, message=text)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rounds", type=int, default=24)
    parser.add_argument("--notify", action="store_true")
    args = parser.parse_args()
    results = measure(args.rounds, random.Random(2026))
    for sub, r in results.items():
        print(f"{REGISTRY[sub].title:18} дуэль {r['duel']:>4.0%}  соло против двоих {r['solo']:>4.0%}")
    problems = verdict(results)
    print("\n".join(problems) or "Все подклассы в коридорах.")
    if args.notify:
        previous = json.loads(STATE_FILE.read_text(encoding="utf-8")) if STATE_FILE.exists() else None
        if problems and problems != previous:
            asyncio.run(notify("⚖️ Ночная проверка баланса:\n" + "\n".join(f"· {p}" for p in problems)))
        try:
            STATE_FILE.write_text(json.dumps(problems, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
