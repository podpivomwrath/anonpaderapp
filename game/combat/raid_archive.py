"""Безликий Архивариус - бой третьего этапа «Безликого архива».

Обычный бой без загадок, механики про знание и книги:
- Каталог: навык, который игрок повторил (тот же, что и в прошлый раз, не
  сменив другим), Архивариус копирует. Урон - тем же числом в игрока,
  лечение - себе. Навыки без урона и лечения он повторяет «в ту же
  сторону»: оборона - режет входящий урон, самоусиление - усиливает
  себя, уворот - уворачивается. Контроль сверх урона оглушает повторившего.
- Цитата: за ход он раскрывает книгу; в следующем ходу запоминает
  сильнейший удар по себе и бьёт им случайного игрока. Работает всегда,
  независимо от каталога.
- Ластик: за ход берёт ластик; следующим ходом стирает с группы щиты,
  усиления и эффекты эликсиров.
- Последняя глава: ниже четверти HP каждому каждый ход выпадает страница -
  сила, слабость, щит или немота (все навыки на ход в откате).

Чистая логика поверх session/resolver, как raid_field.py. Оркестрация -
bot/handlers/raid_combat.py.
"""

import random

from game.combat import balance_config as bc
from game.combat import base_skills, subclass_skills
from game.combat.raid_bosses import _boss_combatant
from game.combat.raid_field import StageTick, _players, _target_of
from game.combat.resolver import TickResult
from game.combat.session import ActionType, CombatantState, CombatSessionState, EffectKind
from game.combat.skills import PendingHit, compute_hit
from game.economy import raid_archive_config as ac

BOSS_NAME = "Безликий Архивариус"

#: Самоуворот: повторишь - он сам начнёт уворачиваться.
_DODGE_SKILLS = {"rogue_smoke", "shadow_blade_shadow_dance"}
#: Самоусиление урона: повторишь - он ударит сильнее.
_BUFF_SKILLS = {"warrior_warcry"}

#: Что стирает ластик: всё, что игрок повесил себе на пользу.
_ERASABLE = {
    EffectKind.DAMAGE_BUFF, EffectKind.DODGE, EffectKind.SHIELD_POOL, EffectKind.BLOCK_STANCE,
    EffectKind.BLOCK_HEAL, EffectKind.DAMAGE_CAP, EffectKind.LAST_BREATH, EffectKind.CONTROL_IMMUNE,
    EffectKind.BLOOD_REFLECT, EffectKind.FLAT_DAMAGE_BONUS, EffectKind.ELEMENTAL_FLOW,
    EffectKind.ASHEN_FEVER,
}

PAGES = ("power", "weak", "shield", "silence")
_PAGE_WORD = {"power": "сила", "weak": "слабость", "shield": "щит", "silence": "немота"}


def _is_control(skill_id: str) -> bool:
    return base_skills.is_control_skill(skill_id) or subclass_skills.is_control_skill(skill_id)


def _skill_name(skill_id: str) -> str:
    skill = base_skills.BASE_SKILL_DEFS.get(skill_id) or subclass_skills.SUBCLASS_SKILL_DEFS.get(skill_id)
    return skill.name if skill else skill_id


class ArchivistAI:
    def __init__(self) -> None:
        self.turn = 0

    def __call__(self, boss: CombatantState, session: CombatSessionState, rng: random.Random) -> list[PendingHit]:
        self.turn += 1
        if self.turn % ac.STORM_EVERY == 0:
            return [
                compute_hit(boss, t, rng, label="Буря страниц", multiplier=ac.STORM_MULT, is_ability=True)
                for t in session.alive_enemies_of(boss)
            ]
        target = _target_of(boss, session, rng)
        if target is None:
            return []
        return [compute_hit(boss, target, rng, label="Удар переплётом", multiplier=ac.STRIKE_MULT)]


class ArchiveStage:
    def __init__(self, start_id: int) -> None:
        self._next_id = start_id
        self.boss_id: int | None = None
        self.ai = ArchivistAI()
        self.ticks = 0
        self.last_skill: dict[int, str] = {}
        self.quote_open = False
        self.eraser_up = False
        self.guard_turns = 0
        self.hinted: set[str] = set()

    @property
    def reward_ids(self) -> set[int]:
        return {self.boss_id} if self.boss_id is not None else set()

    def setup(self, session: CombatSessionState) -> list[str]:
        self._next_id += 1
        boss = _boss_combatant(self._next_id, BOSS_NAME, ac.BOSS_HP, ac.BOSS_STAT_MULT, "int")
        boss.scripted_hit = self.ai
        boss.control_immune_always = True
        boss.incoming_hit_hook = self._hook
        self.boss_id = boss.id
        session.add(boss)
        return []

    def _hook(self, hit: PendingHit, source: CombatantState | None, amount: int) -> int:
        if self.guard_turns > 0:
            return round(amount * (1 - ac.CATALOG_GUARD_REDUCTION))
        return amount

    def _hint(self, key: str, line: str, out: StageTick) -> None:
        if key not in self.hinted:
            self.hinted.add(key)
            out.lines.append(line)

    def after_tick(self, session: CombatSessionState, result: TickResult, rng: random.Random) -> StageTick:
        self.ticks += 1
        out = StageTick()
        boss = session.combatants[self.boss_id]
        if not boss.alive:
            return out
        if self.guard_turns > 0:
            self.guard_turns -= 1

        self._catalog(session, result, boss, out)
        if self.quote_open:
            self.quote_open = False
            self._quote(session, result, boss, rng, out)
        if self.eraser_up:
            self.eraser_up = False
            self._erase(session, out)

        if self.ticks % ac.QUOTE_EVERY == 0:
            self.quote_open = True
            out.lines.append("⚠️ Архивариус раскрывает книгу на чистой странице.")
            self._hint("quote", "Сильнейший удар по нему в этот ход он запишет - и вернёт.", out)
        elif self.ticks % ac.ERASER_EVERY == ac.ERASER_OFFSET:
            self.eraser_up = True
            out.lines.append("⚠️ Архивариус берёт ластик.")
            self._hint("eraser", "После этого хода он сотрёт с вас щиты и усиления.", out)

        if boss.current_hp <= boss.max_hp * ac.LAST_CHAPTER_HP:
            self._last_chapter(session, boss, rng, out)
        return out

    # --- Каталог ---

    def _catalog(self, session, result: TickResult, boss: CombatantState, out: StageTick) -> None:
        for cid, action in result.actions.items():
            if action.type != ActionType.SKILL or not action.skill_id:
                continue
            player = session.combatants.get(cid)
            skill_id = action.skill_id
            repeated = self.last_skill.get(cid) == skill_id
            self.last_skill[cid] = skill_id
            if not repeated or player is None or not player.alive:
                continue
            name = _skill_name(skill_id)
            self._hint("catalog", "📖 Повторённый навык уже в его каталоге: он отвечает тем же.", out)
            damage = sum(
                h.amount for h in result.hit_renders
                if h.source_id == cid and h.target_side == 1 and not h.missed and not h.is_tick
            )
            heal = sum(h.amount for h in result.heal_renders if h.source_id == cid)
            copied = False
            if damage > 0:
                copied = True
                player.current_hp -= damage
                out.lines.append(f"📖 Каталог: «{name}» → {player.name} - {damage} урона")
                if player.current_hp <= 0:
                    player.current_hp = 0
                    out.deaths.append(cid)
                    out.lines.append(f"☠ {player.name} погибает")
            if heal > 0:
                copied = True
                before = boss.current_hp
                boss.current_hp = min(boss.max_hp, boss.current_hp + heal)
                out.lines.append(f"📖 Каталог: «{name}» - Архивариус восполняет {boss.current_hp - before} HP")
            if _is_control(skill_id) and player.alive:
                player.apply_effect(EffectKind.FREEZE, 1.0, 1, boss.id)
                out.frozen.append(cid)
                out.lines.append(f"📖 Каталог: «{name}» - {player.name} скован на ход")
                copied = True
            if copied:
                continue
            if skill_id in _DODGE_SKILLS:
                boss.apply_effect(EffectKind.DODGE, ac.CATALOG_DODGE, ac.CATALOG_DODGE_TURNS, -3)
                out.lines.append(f"📖 Каталог: «{name}» - Архивариус уворачивается {ac.CATALOG_DODGE_TURNS} хода")
            elif skill_id in _BUFF_SKILLS:
                boss.apply_effect(EffectKind.DAMAGE_BUFF, ac.CATALOG_BUFF, ac.CATALOG_BUFF_TURNS, -2)
                out.lines.append(f"📖 Каталог: «{name}» - Архивариус бьёт сильнее {ac.CATALOG_BUFF_TURNS} хода")
            else:
                # Оборона, провокация, щиты - «в ту же сторону»: он закрывается.
                self.guard_turns = ac.CATALOG_GUARD_TURNS
                out.lines.append(
                    f"📖 Каталог: «{name}» - Архивариус закрывается книгой: урон по нему "
                    f"-{round(ac.CATALOG_GUARD_REDUCTION * 100)}% на {ac.CATALOG_GUARD_TURNS} хода"
                )

    # --- Цитата ---

    def _quote(self, session, result: TickResult, boss: CombatantState, rng, out: StageTick) -> None:
        strongest = max(
            (h for h in result.hit_renders
             if h.target_id == boss.id and h.source_side == 0 and not h.missed and not h.is_tick),
            key=lambda h: h.amount, default=None,
        )
        players = _players(session)
        if strongest is None or strongest.amount <= 0 or not players:
            out.lines.append("Страница остаётся чистой - цитировать нечего.")
            return
        target = rng.choice(players)
        target.current_hp -= strongest.amount
        source = session.combatants[strongest.source_id].name
        out.lines.append(f"📖 Цитата: удар {source} → {target.name} - {strongest.amount} урона")
        if target.current_hp <= 0:
            target.current_hp = 0
            out.deaths.append(target.id)
            out.lines.append(f"☠ {target.name} погибает")

    # --- Ластик ---

    def _erase(self, session, out: StageTick) -> None:
        erased = 0
        for player in _players(session):
            before = len(player.effects)
            player.effects = [e for e in player.effects if e.kind not in _ERASABLE]
            erased += before - len(player.effects)
        out.lines.append(
            f"🧽 Ластик проходит по вам: стёрто усилений - {erased}." if erased
            else "🧽 Ластик проходит впустую - стирать было нечего."
        )

    # --- Последняя глава ---

    def _last_chapter(self, session, boss: CombatantState, rng, out: StageTick) -> None:
        self._hint("chapter", "📜 Последняя глава: страницы летят по залу, и каждому выпадает своя.", out)
        drawn = []
        for player in _players(session):
            page = rng.choice(PAGES)
            if page == "power":
                player.apply_effect(EffectKind.DAMAGE_BUFF, ac.PAGE_DAMAGE_UP, 1, -4)
            elif page == "weak":
                player.apply_effect(EffectKind.WEAKEN, ac.PAGE_DAMAGE_DOWN, 1, -4)
            elif page == "shield":
                player.apply_effect(EffectKind.SHIELD_POOL, round(player.max_hp * ac.PAGE_SHIELD), 1, -4)
            else:
                for skill_id in list(player.cooldowns) + _skills_of(player):
                    player.cooldowns[skill_id] = max(player.cooldowns.get(skill_id, 0), 1)
            drawn.append(f"{player.name} - {_PAGE_WORD[page]}")
        if drawn:
            out.lines.append("📜 " + ", ".join(drawn))


def _skills_of(player: CombatantState) -> list[str]:
    base_class = next(
        (cls for cls, stat in bc.PRIMARY_STAT_BY_CLASS.items() if stat == player.primary_stat), None,
    )
    if base_class is None:
        return []
    return [s.id for s in base_skills.skills_for_character(base_class, player.subclass_id)]
