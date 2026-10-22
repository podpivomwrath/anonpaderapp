"""Рейд «Тропа Безымянного», этап 3: бой с Безымянным (2026-10-20).

У каждого игрока клетка на арене 3×3. Шаг на соседнюю клетку (и по
диагонали) - отдельное действие, занимает ход (bot/handlers/raid_combat.py
объявляет его как SKIP с payload step).

- «Отпечатки»: раз в tc.MARK_EVERY ходов Безымянный метит клетки, следующим
  ходом наступает на них - кто остался, получает tc.MARK_PCT макс. HP.
- «Тропа под ногами»: простоял на клетке tc.BURN_AFTER ходов - она жжёт.
- «Безымянность»: один игрок не видит отпечатков, пока союзник не встанет к
  нему на клетку (окликнет).
- Финал: ниже tc.FINAL_HP тропа сужается - крайние клетки по очереди горят
  навсегда.

Урон механик - мимо резолвера, но через щиты (как у жерновов).
"""

import random

from game.combat.raid_bosses import _boss_combatant
from game.combat.raid_field import StageTick, _players, _target_of
from game.combat.resolver import TickResult
from game.combat.session import ActionType, CombatantState, CombatSessionState
from game.combat.shared_rules import absorb_by_shields
from game.combat.skills import PendingHit, compute_hit
from game.economy import raid_trail_config as tc

BOSS_NAME = "Безымянный"
CELLS = tc.ARENA * tc.ARENA
CENTER = CELLS // 2
#: Крайние клетки в порядке, в каком тропа сужается: углы, потом края.
OUTER_ORDER = (0, 8, 2, 6, 1, 7, 3, 5)


def adjacent(a: int, b: int) -> bool:
    """Соседние клетки арены, включая диагональ."""
    (r1, c1), (r2, c2) = divmod(a, tc.ARENA), divmod(b, tc.ARENA)
    return a != b and abs(r1 - r2) <= 1 and abs(c1 - c2) <= 1


def _hurt(player: CombatantState, amount: int, out: StageTick) -> None:
    if amount <= 0 or not player.alive:
        return
    amount = absorb_by_shields(player, amount, out.lines)
    if amount <= 0:
        return
    player.current_hp = max(0, player.current_hp - amount)
    if player.current_hp <= 0:
        out.deaths.append(player.id)
        out.lines.append(f"☠ {player.name} погибает")


class NamelessAI:
    def __call__(self, boss: CombatantState, session: CombatSessionState, rng: random.Random) -> list[PendingHit]:
        target = _target_of(boss, session, rng)
        if target is None:
            return []
        return [compute_hit(boss, target, rng, label="Удар босой ногой", multiplier=tc.STRIKE_MULT)]


class NamelessStage:
    def __init__(self, start_id: int) -> None:
        self._next_id = start_id
        self.boss_id: int | None = None
        self.ticks = 0
        self.hinted: set[str] = set()
        self.pos: dict[int, int] = {}
        self.still: dict[int, int] = {}
        #: Клетки, куда Безымянный наступит в конце следующего хода.
        self.marks: set[int] = set()
        self.burning: set[int] = set()
        self.nameless: set[int] = set()
        self.final = False

    def _new_id(self) -> int:
        self._next_id += 1
        return self._next_id

    @property
    def reward_ids(self) -> set[int]:
        return {self.boss_id} if self.boss_id is not None else set()

    def setup(self, session: CombatSessionState) -> list[str]:
        boss = _boss_combatant(self._new_id(), BOSS_NAME, tc.BOSS_HP, tc.BOSS_STAT_MULT)
        boss.scripted_hit = NamelessAI()
        boss.control_immune_always = True
        self.boss_id = boss.id
        session.add(boss)
        # Игроки - по разным клеткам, центр свободен.
        free = [c for c in range(CELLS) if c != CENTER]
        for n, p in enumerate(sorted(c.id for c in _players(session))):
            self.pos[p] = free[n % len(free)]
            self.still[p] = 0
        return []

    # --- то, что видит клавиатура ---

    def danger(self, cid: int) -> set[int]:
        """Красные клетки для этого игрока: без имени он их не видит."""
        if cid in self.nameless:
            return set()
        return self.marks | self.burning

    def can_step(self, cid: int, cell: int) -> bool:
        return cid in self.pos and 0 <= cell < CELLS and adjacent(self.pos[cid], cell)

    def _hint(self, key: str, line: str, out: StageTick) -> None:
        if key not in self.hinted:
            self.hinted.add(key)
            out.lines.append(line)

    # --- ход ---

    def after_tick(self, session: CombatSessionState, result: TickResult, rng: random.Random) -> StageTick:
        from bot import raid_trail_texts as tt

        self.ticks += 1
        out = StageTick()
        boss = session.combatants[self.boss_id]
        if not boss.alive:
            return out
        players = {p.id: p for p in _players(session)}
        for cid in list(self.pos):
            if cid not in players:
                self.pos.pop(cid)
                self.still.pop(cid, None)
                self.nameless.discard(cid)

        # 1. Шаги этого хода.
        moved: set[int] = set()
        for cid, action in result.actions.items():
            step = (action.payload or {}).get("step") if action.type == ActionType.SKIP else None
            if cid in self.pos and isinstance(step, int) and self.can_step(cid, step):
                self.pos[cid] = step
                moved.add(cid)
        for cid in self.pos:
            self.still[cid] = 0 if cid in moved else self.still.get(cid, 0) + 1
        # Окликнуть: союзник шагнул на клетку безымянного (или тот к союзнику).
        # Окликает только тот, кто сам помнит имя: двое безымянных, сойдясь,
        # раньше возвращали имя друг другу (2026-10-22).
        forgot = set(self.nameless)
        for cid in list(self.nameless):
            if any(o != cid and o not in forgot and self.pos.get(o) == self.pos.get(cid)
                   and (o in moved or cid in moved)
                   for o in self.pos):
                self.nameless.discard(cid)
                out.lines.append(tt.CALLED_LINE.format(name=players[cid].name))

        # 2. Наступает на отмеченное в прошлый ход.
        if self.marks:
            for cid, cell in self.pos.items():
                if cell in self.marks:
                    p = players[cid]
                    amount = round(p.max_hp * tc.MARK_PCT)
                    out.lines.append(tt.MARK_HIT.format(name=p.name, amount=amount))
                    _hurt(p, amount, out)
            self.marks = set()

        # 3. Тропа под ногами и сгоревшие клетки финала.
        for cid, cell in list(self.pos.items()):
            p = players.get(cid)
            if p is None or not p.alive:
                continue
            if cell in self.burning:
                amount = round(p.max_hp * tc.SHRINK_PCT)
                out.lines.append(tt.BURN_LINE.format(name=p.name, amount=amount))
                _hurt(p, amount, out)
            elif self.still[cid] >= tc.BURN_AFTER:
                amount = round(p.max_hp * tc.BURN_PCT)
                out.lines.append(tt.BURN_LINE.format(name=p.name, amount=amount))
                _hurt(p, amount, out)

        # 4. Финал: тропа сужается.
        if not self.final and boss.current_hp <= boss.max_hp * tc.FINAL_HP:
            self.final = True
        if self.final and self.ticks % tc.SHRINK_EVERY == 0:
            nxt = next((c for c in OUTER_ORDER if c not in self.burning), None)
            if nxt is not None:
                self.burning.add(nxt)
                out.lines.append(tt.SHRINK_LINE)

        # 5. Новые отпечатки - на следующий ход.
        if self.ticks % tc.MARK_EVERY == 0:
            count = tc.MARK_COUNT_FINAL if self.final else tc.MARK_COUNT
            occupied = [c for c in set(self.pos.values()) if c not in self.burning]
            pool = [c for c in range(CELLS) if c not in self.burning]
            # Хотя бы один отпечаток - под кем-то: иначе стоять можно вечно.
            first = {rng.choice(occupied)} if occupied else set()
            rest = rng.sample([c for c in pool if c not in first], max(0, min(count - len(first), len(pool) - 1)))
            self.marks = first | set(rest)
            out.lines.append(tt.MARKS_LINE)
            self._hint("marks", tt.STAGE3_HINT, out)

        # 6. Безымянность.
        if self.ticks % tc.NAMELESS_EVERY == tc.NAMELESS_OFFSET and len(self.pos) > 1:
            candidates = [c for c in self.pos if c not in self.nameless]
            if candidates:
                cid = rng.choice(candidates)
                self.nameless.add(cid)
                out.lines.append(tt.NAMELESS_LINE.format(name=players[cid].name))
                self._hint("nameless", tt.NAMELESS_HINT, out)
        return out
