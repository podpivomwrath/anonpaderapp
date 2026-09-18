"""Мини-апп считает производные статы САМ, чтобы рисовать «было -> станет» до
отправки запроса. Это второе место, где живут формулы боя, и оно уже расходилось
с сервером: округление половины к чётному в Python против округления вверх в JS
давало разницу в 1 HP примерно на каждом двадцатом наборе статов.

Тест гоняет ОБЕ реализации на одной сетке и сравнивает. Требует node - без него
пропускается, чтобы не ломать прогон там, где фронтенда нет.
"""

import json
import pathlib
import shutil
import subprocess

import pytest

from services.derived_stats_service import compute

NODE = shutil.which("node")
ROOT = pathlib.Path(__file__).resolve().parents[1]
FORMULAS = ROOT / "miniapp" / "src" / "formulas.js"

pytestmark = pytest.mark.skipif(
    NODE is None or not FORMULAS.exists(),
    reason="нужен node и исходники мини-аппа",
)

LEVELS = (1, 15, 16, 30, 31, 45, 46, 50, 60)
BUILDS = (
    (10, 10, 10, 10, 10),
    (25, 15, 10, 20, 15),
    (60, 91, 20, 93, 57),
    (100, 100, 100, 100, 100),
)

SCRIPT = """
import { computeDerived, tierForLevel } from './miniapp/src/formulas.js';
const levels = %s;
const builds = %s;
const out = [];
for (const level of levels) {
  for (const baseClass of ['warrior', 'rogue', 'mage']) {
    for (const b of builds) {
      const stats = { str: b[0], agi: b[1], int: b[2], vit: b[3], wil: b[4] };
      out.push({ level, baseClass, stats, tier: tierForLevel(level),
                 ...computeDerived({ level, baseClass, stats }) });
    }
  }
}
console.log(JSON.stringify(out));
"""


def _client_rows() -> list[dict]:
    script = ROOT / "_formula_parity_probe.mjs"
    script.write_text(SCRIPT % (json.dumps(LEVELS), json.dumps(BUILDS)), encoding="utf-8")
    try:
        proc = subprocess.run(
            [NODE, script.name], cwd=ROOT, capture_output=True, text=True, timeout=120
        )
    finally:
        script.unlink(missing_ok=True)
    assert proc.returncode == 0, proc.stderr[:400]
    return json.loads(proc.stdout)


class _Character:
    subclass = None

    def __init__(self, level: int, base_class: str) -> None:
        self.level = level
        self.base_class = base_class


class _Stats:
    def __init__(self, s: dict) -> None:
        self.strength, self.agility = s["str"], s["agi"]
        self.intellect, self.vitality, self.will = s["int"], s["vit"], s["wil"]


def test_client_preview_matches_server_formulas() -> None:
    mismatches: list[str] = []
    for row in _client_rows():
        server = compute(_Character(row["level"], row["baseClass"]), _Stats(row["stats"]))
        pairs = {
            "max_hp": (row["maxHp"], server.max_hp),
            "damage": (row["damage"], server.damage),
            "crit_chance": (row["critChance"], server.crit_chance),
            "mitigation": (row["mitigation"], server.mitigation),
            "control_resist": (row["controlResist"], server.control_resist),
            "support_power": (row["supportPower"], server.support_power),
            "dodge_chance": (row["dodgeChance"], server.dodge_chance),
            "ability_dodge": (row["abilityDodgeChance"], server.ability_dodge_chance),
            "poison_power": (round(row["poisonPower"], 1), server.poison_power),
        }
        for name, (client, srv) in pairs.items():
            if abs(client - srv) > 1e-9:
                mismatches.append(
                    f"ур.{row['level']} {row['baseClass']} {row['stats']} "
                    f"{name}: клиент {client} != сервер {srv}"
                )
    assert not mismatches, "предпросмотр мини-аппа разошёлся с сервером:\n" + "\n".join(
        mismatches[:10]
    )
