"""Симулятор боевого баланса: КПД классов и подклассов в четырёх режимах.

Запуск:  python tools/sim_balance.py [--fast]

Зачем. Винрейт сам по себе мало что говорит про танка и саппорта: они и должны
бить слабо. Поэтому КПД считается по-разному в зависимости от того, что роль
обязана делать:

  * СОЛО PvE   - винрейт против НАСТОЯЩИХ мобов из бестиария (game/world/
                 encounters.py). Это проверка «а играется ли класс один», её
                 обязаны проходить и танк, и хилер.
  * МАСС PvE   - групповой бой против пачки мобов. Личный урон тут не главное,
                 главное - ВКЛАД: насколько падает винрейт группы, если убрать
                 из неё этого бойца и заменить средним ДД.
  * PvP 1x1    - круговой турнир на настоящем дуэльном движке.
  * МАСС PvP   - бои 3x3 на тиковом движке, тот же вклад, что и в масс PvE.

Бои идут через реальные движки (resolve_tick и DuelEngine), никаких
упрощённых формул: если движок и контент разойдутся, симулятор это покажет.

Ограничение, которое важно помнить при чтении цифр: качество результата упирается
в качество ИИ. Он тут эвристический (см. choose_action) и играет ровнее живого
человека, поэтому числа стоит читать как СРАВНЕНИЕ подклассов между собой, а не
как предсказание реального винрейта.
"""

from __future__ import annotations

import argparse
import asyncio
import itertools
import random
import statistics
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from loguru import logger

logger.remove()

import game.classes  # noqa: F401  - регистрация подклассов
from game.classes.base import REGISTRY
from game.combat import balance_config as bc
from game.combat.duel_engine import DuelEngine
from game.combat.resolver import resolve_tick
from game.combat.session import (
    ActionType,
    CombatMode,
    CombatantState,
    CombatSessionState,
    DeclaredAction,
    EffectKind,
    Stats,
    build_combatant,
)
from game.combat.subclass_skills import SUBCLASS_SKILL_DEFS
from game.content_loader import load_content
from game.world import encounters

CONTENT = load_content()
MAX_TURNS = 60          # ничья, если никто не добил - чтобы не висеть вечно
REGIONS = ("ridge", "woods", "scorched", "docks")  # четыре региона бестиария


# ----------------------------------------------------------------------------
# Сборка бойцов
# ----------------------------------------------------------------------------

#: Куда роль тратит очки уровня. Ключи - поля Stats.
ROLE_WEIGHTS = {
    "dd":      {"primary": 0.60, "vitality": 0.30, "will": 0.10},
    "tank":    {"primary": 0.35, "vitality": 0.50, "will": 0.15},
    "healer":  {"primary": 0.30, "vitality": 0.25, "will": 0.45},
    "support": {"primary": 0.45, "vitality": 0.30, "will": 0.25},
}

PRIMARY_FIELD = {"str": "strength", "agi": "agility", "int": "intellect"}


def build_stats(base_class: str, primary_stat: str, level: int, role: str) -> Stats:
    """Стартовое распределение класса + очки уровня по весам роли.
    Бюджет тот же, что у живого игрока: 85 стартовых + 3 за уровень."""
    start = bc.STARTING_STATS[base_class]
    stats = Stats(
        strength=start["STR"], agility=start["AGI"], intellect=start["INT"],
        vitality=start["VIT"], will=start["WIL"],
    )
    points = bc.STAT_POINTS_PER_LEVEL * (level - 1)
    weights = ROLE_WEIGHTS[role]
    primary_field = PRIMARY_FIELD[primary_stat]
    for key, share in weights.items():
        field_name = primary_field if key == "primary" else key
        setattr(stats, field_name, getattr(stats, field_name) + round(points * share))
    return stats


def make_fighter(
    cid: int, side: int, subclass_id: str | None, level: int, role: str,
    buff_modifiers: dict[str, float] | None = None, base_class: str | None = None,
) -> CombatantState:
    if subclass_id is not None:
        sub = REGISTRY[subclass_id]
        base_class, primary = sub.base_class, sub.primary_stat
        name = sub.title
    else:
        primary = bc.PRIMARY_STAT_BY_CLASS[base_class]
        name = {"warrior": "Воин", "rogue": "Разбойник", "mage": "Маг"}[base_class]
    fighter = build_combatant(
        id=cid, side=side, kind="character", name=f"{name}#{cid}", level=level,
        stats=build_stats(base_class, primary, level, role), primary_stat=primary,
        subclass_id=subclass_id, buff_modifiers=dict(buff_modifiers or {}),
    )
    fighter.sim_skills = _skills_for(subclass_id, base_class)
    fighter.sim_role = role
    return fighter


def _skills_for(subclass_id: str | None, base_class: str) -> list[str]:
    from game.combat.base_skills import skills_for_character

    return [s.id for s in skills_for_character(base_class, subclass_id)]


# ----------------------------------------------------------------------------
# Пресеты баффов
# ----------------------------------------------------------------------------


def buffs_of(subclass_id: str) -> list:
    return [b for b in CONTENT.buffs.values() if b.subclass == subclass_id and b.implemented]


def _pick(pool: list, categories: tuple[str, ...], limit: int) -> list:
    return [b for b in pool if b.category in categories][:limit]


def preset_variants(subclass_id: str) -> dict[str, list[str]]:
    """Варианты сборок. Правила пресета (services/preset_service.py): 3-5 баффов,
    минимум один из обороны или контроль/утилити. «Без баффов» - не легальный
    пресет, а точка отсчёта: показывает, сколько подкласс стоит сам по себе."""
    pool = buffs_of(subclass_id)
    defensive = _pick(pool, ("defense", "control_utility"), 5)
    damage = _pick(pool, ("damage",), 5)
    group = _pick(pool, ("group_support",), 5)

    def compose(*groups: list) -> list[str]:
        out: list[str] = []
        for group_ in groups:
            for b in group_:
                if b.id not in out and len(out) < bc.PRESET_MAX_BUFFS:
                    out.append(b.id)
        # правило: хотя бы один бафф обороны/утилиты
        if defensive and not any(
            CONTENT.buffs[i].category in bc.PRESET_REQUIRED_CATEGORIES for i in out
        ):
            out[-1] = defensive[0].id
        return out

    variants = {
        "без баффов": [],
        "урон": compose(damage[:4], defensive[:1]),
        "оборона": compose(defensive[:4], damage[:1]),
        "смешанный": compose(damage[:2], defensive[:2], group[:1]),
    }
    if group:
        variants["поддержка"] = compose(group[:3], defensive[:2])
    return {k: v for k, v in variants.items() if k == "без баффов" or len(v) >= bc.PRESET_MIN_BUFFS}


def modifiers_for(buff_ids: list[str]) -> dict[str, float]:
    from services.preset_service import resolve_buff_modifiers

    return resolve_buff_modifiers(buff_ids, CONTENT.buffs)


# ----------------------------------------------------------------------------
# ИИ
# ----------------------------------------------------------------------------

#: Навыки, которые бьют не ради урона: лечение, щит, оборона, контроль.
HEAL_SKILLS = {"dark_mystic_blood_pact", "dark_mystic_circle", "dark_mystic_ward"}
DEFENCE_SKILLS = {"guardian_block", "guardian_unbreakable"}
CONTROL_SKILLS = {"guardian_stonegrip", "poisoner_disrupt", "elementalist_ice",
                  "warrior_stagger", "mage_ice_bonds"}
EXECUTE_SKILLS = {"shadow_blade_execute", "blood_knight_harvest"}
#: Навыки с нулевым множителем: по «самому сильному удару» они не выбираются
#: никогда, поэтому каждому нужна своя явная причина применения. Без этого
#: Отравитель ни разу не жмёт свой финишер, а Клинок теней - самоуворот.
ZERO_MULT_SKILLS = {"poisoner_toxic_burst", "shadow_blade_shadow_dance",
                    "guardian_block", "guardian_unbreakable",
                    "dark_mystic_ward", "dark_mystic_circle", "warrior_warcry",
                    "rogue_smoke"}


def _hp_share(c: CombatantState) -> float:
    return c.current_hp / c.max_hp if c.max_hp else 0.0


def choose_action(
    actor: CombatantState, session: CombatSessionState, target: CombatantState
) -> DeclaredAction:
    """Эвристика «как сыграл бы неплохой, но не гениальный игрок»: сначала
    ситуативные навыки роли (лечить раненого, уйти в оборону на низком HP,
    добить слабую цель), потом самый сильный доступный удар, иначе - атака."""
    ready = [s for s in getattr(actor, "sim_skills", []) if not actor.is_on_cooldown(s)]
    allies = [c for c in session.alive_allies_of(actor)] + [actor]
    weakest_ally = min(allies, key=_hp_share)

    def use(skill_id: str, tgt: int | None = None) -> DeclaredAction:
        return DeclaredAction(type=ActionType.SKILL, skill_id=skill_id,
                              target_id=tgt if tgt is not None else target.id)

    # 1. Лечение: чем хуже дела у самого раненого, тем приоритетнее
    if _hp_share(weakest_ally) < 0.75:
        hurt_allies = sum(1 for a in allies if _hp_share(a) < 0.7)
        if "dark_mystic_circle" in ready and hurt_allies >= 2 and _hp_share(actor) > 0.45:
            return use("dark_mystic_circle")
        if "dark_mystic_ward" in ready and _hp_share(weakest_ally) < 0.6:
            return use("dark_mystic_ward")
        if "dark_mystic_blood_pact" in ready:
            return use("dark_mystic_blood_pact")

    # 2. Оборона танка на низком здоровье
    if _hp_share(actor) < 0.55:
        if "guardian_unbreakable" in ready and not actor.has_effect(EffectKind.DAMAGE_CAP):
            return use("guardian_unbreakable")
        if "guardian_block" in ready and not actor.has_effect(EffectKind.BLOCK_STANCE):
            return use("guardian_block")
    # Танк держит оборону и просто так, если ничего срочнее нет
    if ("guardian_block" in ready and _hp_share(actor) < 0.85
            and not actor.has_effect(EffectKind.BLOCK_STANCE)):
        return use("guardian_block")

    # 3. Отравитель: выброс копит смысл, пока на цели много стаков яда -
    # он их тратит, превращая тик-урон в мгновенный.
    if "poisoner_toxic_burst" in ready:
        poison = target.effect_from(EffectKind.DOT, actor.id)
        if poison is not None and poison.stacks >= 3:
            return use("poisoner_toxic_burst")

    # 3a. Самоусиления и самозащита, которые по множителю никогда не выиграют.
    # Поверх ещё действующего эффекта не перекладываем - это потерянный ход.
    if _hp_share(actor) < 0.7 and not actor.has_effect(EffectKind.DODGE):
        for skill_id in ("shadow_blade_shadow_dance", "rogue_smoke"):
            if skill_id in ready:
                return use(skill_id)
    if "warrior_warcry" in ready and not actor.has_effect(EffectKind.DAMAGE_BUFF):
        return use("warrior_warcry")

    # 4. Добивание
    if _hp_share(target) < 0.35:
        for skill_id in EXECUTE_SKILLS:
            if skill_id in ready:
                return use(skill_id)

    # 5. Контроль, если цель ещё не под контролем
    if not target.has_effect(EffectKind.FREEZE):
        for skill_id in CONTROL_SKILLS & set(ready):
            return use(skill_id)

    # 6. Самый сильный доступный удар
    offensive = [
        s for s in ready
        if s not in HEAL_SKILLS and s not in ZERO_MULT_SKILLS and s in SUBCLASS_SKILL_DEFS
    ]
    if offensive:
        best = max(offensive, key=lambda s: SUBCLASS_SKILL_DEFS[s].multiplier)
        if SUBCLASS_SKILL_DEFS[best].multiplier > 0:
            return use(best)
    from game.combat.base_skills import BASE_SKILL_DEFS

    base_offensive = [s for s in ready if s in BASE_SKILL_DEFS and BASE_SKILL_DEFS[s].multiplier > 0]
    if base_offensive:
        return use(max(base_offensive, key=lambda s: BASE_SKILL_DEFS[s].multiplier))

    # 7. Хилер без раненых всё же лечит-бьёт: пакт и урон наносит
    if "dark_mystic_blood_pact" in ready:
        return use("dark_mystic_blood_pact")
    return DeclaredAction(type=ActionType.ATTACK, target_id=target.id)


def pick_target(actor: CombatantState, session: CombatSessionState) -> CombatantState | None:
    enemies = session.alive_enemies_of(actor)
    if not enemies:
        return None
    return min(enemies, key=lambda c: c.current_hp)  # добиваем самого слабого


# ----------------------------------------------------------------------------
# Режимы боя
# ----------------------------------------------------------------------------


@dataclass
class FightStats:
    won: bool = False
    draw: bool = False
    turns: int = 0
    hp_left_share: float = 0.0
    damage_by: dict[int, int] = field(default_factory=dict)
    healing_by: dict[int, int] = field(default_factory=dict)
    damage_taken: dict[int, int] = field(default_factory=dict)
    #: Доля снятого с врагов HP. В отличие от винрейта не упирается ни в пол,
    #: ни в потолок, поэтому годится там, где подкласс проигрывает всегда.
    enemy_hp_removed: float = 0.0


def run_tick_fight(
    players: list[CombatantState], enemies: list[CombatantState], rng: random.Random,
    mode: CombatMode = CombatMode.PVE,
) -> FightStats:
    """Бой на тиковом движке: соло/групповой PvE и масс PvP."""
    session = CombatSessionState(session_id=1, mode=mode)
    for c in players + enemies:
        session.add(c)
    stats = FightStats()
    for _ in range(MAX_TURNS):
        session.tick_number += 1
        actions: dict[int, DeclaredAction] = {}
        for c in session.combatants.values():
            if not c.alive or c.kind != "character":
                continue
            target = pick_target(c, session)
            if target is not None:
                actions[c.id] = choose_action(c, session, target)
        hp_before = {c.id: c.current_hp for c in session.combatants.values()}
        result = resolve_tick(session, actions, rng)
        stats.turns = session.tick_number
        for hit in result.hits:
            if not hit.missed:
                stats.damage_by[hit.source_id] = stats.damage_by.get(hit.source_id, 0) + hit.amount
        for c in session.combatants.values():
            lost = hp_before[c.id] - c.current_hp
            if lost > 0:
                stats.damage_taken[c.id] = stats.damage_taken.get(c.id, 0) + lost
            elif lost < 0:
                stats.healing_by[c.id] = stats.healing_by.get(c.id, 0) - lost
        if result.finished:
            stats.won = result.winner_side == 0
            stats.draw = result.draw
            break
    stats.enemy_hp_removed = (
        sum(1.0 - _hp_share(e) for e in enemies) / len(enemies) if enemies else 0.0
    )
    alive_players = [c for c in players if c.alive]
    stats.hp_left_share = (
        sum(_hp_share(c) for c in alive_players) / len(players) if players else 0.0
    )
    if not stats.won and not stats.draw and alive_players and not any(e.alive for e in enemies):
        stats.won = True
    return stats


#: Один цикл событий на весь прогон. asyncio.run() на КАЖДЫЙ ход дуэли создаёт
#: и рвёт цикл заново - на десятках тысяч ходов это дороже самого боя.
_LOOP = asyncio.new_event_loop()


def run_duel(a: CombatantState, b: CombatantState, rng: random.Random) -> int | None:
    """Настоящий дуэльный движок. Возвращает id победителя либо None (ничья)."""
    engine = DuelEngine(rng=rng, max_turns=MAX_TURNS)
    engine.start_duel(1, a, b)
    state = engine.duels[1]
    session_view = state.as_session_state()
    while not state.finished:
        actor = state.combatants[state.current_actor_id]
        target = state.opponent_of(actor.id)
        if not actor.alive or not target.alive:
            break
        action = choose_action(actor, session_view, target)
        result = _LOOP.run_until_complete(engine._resolve_turn(state, action))
        if result.finished:
            return None if result.draw else result.winner_id
    return None


# ----------------------------------------------------------------------------
# Сценарии
# ----------------------------------------------------------------------------


def solo_pve(subclass_id: str, level: int, mods: dict, rounds: int, rng: random.Random,
             difficulty: str = "равный") -> dict:
    """Соло против настоящих мобов бестиария.

    Три сложности, потому что на равном мобе побеждают вообще все и разница
    между подклассами не видна:
      равный - моб уровня игрока (базовая проверка «класс играется один»);
      выше   - моб на 10 уровней выше (игрок забрёл в чужое кольцо);
      двое   - два моба уровня игрока разом.
    """
    wins = turns = 0
    hp_left: list[float] = []
    removed: list[float] = []
    dist_by_level = {25: 30, 35: 20, 50: 8, 60: 8}
    dist = dist_by_level[level]
    for i in range(rounds):
        if subclass_id in REGISTRY:
            role = REGISTRY[subclass_id].natural_role.value
            player = make_fighter(1, 0, subclass_id, level, role, mods)
        else:  # базовый класс до 30 уровня: свои навыки, баффов ещё нет
            player = make_fighter(1, 0, None, level, "dd", mods, base_class=subclass_id)
        region = REGIONS[i % len(REGIONS)]
        if difficulty == "выше":
            mobs = [encounters.spawn_mob(2, region, min(level + 10, bc.MAX_LEVEL), dist, rng).combatant]
        elif difficulty == "двое":
            mobs = [encounters.spawn_mob(2 + n, region, level, dist, rng).combatant for n in range(2)]
        else:
            mobs = [encounters.spawn_mob(2, region, level, dist, rng).combatant]
        res = run_tick_fight([player], mobs, rng)
        wins += res.won
        turns += res.turns
        hp_left.append(res.hp_left_share)
        removed.append(res.enemy_hp_removed)
    return {
        "winrate": wins / rounds,
        "turns": turns / rounds,
        "hp_left": statistics.fmean(hp_left),
        "enemy_hp_removed": statistics.fmean(removed),
    }


def group_pve(team: list[str], level: int, mods_by_sub: dict, rounds: int,
              rng: random.Random) -> dict:
    wins = 0
    contribution: dict[str, list[float]] = defaultdict(list)
    for i in range(rounds):
        players = [
            make_fighter(10 + n, 0, sub, level, REGISTRY[sub].natural_role.value,
                         mods_by_sub.get(sub, {}))
            for n, sub in enumerate(team)
        ]
        mobs = [
            encounters.spawn_mob(50 + n, REGIONS[(i + n) % len(REGIONS)], level, 8, rng).combatant
            for n in range(len(team))
        ]
        res = run_tick_fight(players, mobs, rng)
        wins += res.won
        total_damage = sum(res.damage_by.get(p.id, 0) for p in players) or 1
        for p in players:
            contribution[p.subclass_id].append(res.damage_by.get(p.id, 0) / total_damage)
    return {"winrate": wins / rounds,
            "damage_share": {k: statistics.fmean(v) for k, v in contribution.items()}}


def duel_tournament(configs: list[tuple[str, str, dict]], level: int, rounds: int,
                    rng: random.Random) -> dict:
    wins: dict[tuple[str, str], int] = defaultdict(int)
    fights: dict[tuple[str, str], int] = defaultdict(int)
    for (sub_a, var_a, mods_a), (sub_b, var_b, mods_b) in itertools.permutations(configs, 2):
        if sub_a == sub_b:
            continue
        for _ in range(rounds):
            a = make_fighter(1, 0, sub_a, level, REGISTRY[sub_a].natural_role.value, mods_a)
            b = make_fighter(2, 1, sub_b, level, REGISTRY[sub_b].natural_role.value, mods_b)
            winner = run_duel(a, b, rng)
            fights[(sub_a, var_a)] += 1
            fights[(sub_b, var_b)] += 1
            if winner == a.id:
                wins[(sub_a, var_a)] += 1
            elif winner == b.id:
                wins[(sub_b, var_b)] += 1
    return {key: wins[key] / fights[key] for key in fights}


def mass_pvp(team_a: list[str], team_b: list[str], level: int, mods_by_sub: dict,
             rounds: int, rng: random.Random) -> float:
    wins = 0
    for _ in range(rounds):
        side_a = [
            make_fighter(10 + n, 0, sub, level, REGISTRY[sub].natural_role.value,
                         mods_by_sub.get(sub, {}))
            for n, sub in enumerate(team_a)
        ]
        side_b = [
            make_fighter(20 + n, 1, sub, level, REGISTRY[sub].natural_role.value,
                         mods_by_sub.get(sub, {}))
            for n, sub in enumerate(team_b)
        ]
        res = run_tick_fight(side_a, side_b, rng, mode=CombatMode.PVP_GROUP)
        wins += res.won
    return wins / rounds


# ----------------------------------------------------------------------------
# Вклад в группе: «насколько команда слабеет без этого бойца»
# ----------------------------------------------------------------------------

FILLER = "blood_knight"  # нейтральный ДД, которым замещаем проверяемого бойца


def team_winrate_pve(team: list[str], level: int, mods_by_sub: dict, mob_count: int,
                     rounds: int, rng: random.Random,
                     mob_level: int | None = None) -> tuple[float, float, float]:
    """mob_level задаётся отдельно: сложность подбирается так, чтобы базовая
    команда была около 50% - только там видна разница от замены бойца."""
    level_of_mobs = mob_level or level
    wins = 0
    hp_left: list[float] = []
    scores: list[float] = []
    for i in range(rounds):
        players = [
            make_fighter(10 + n, 0, sub, level, REGISTRY[sub].natural_role.value,
                         mods_by_sub.get(sub, {}))
            for n, sub in enumerate(team)
        ]
        mobs = [
            encounters.spawn_mob(50 + n, REGIONS[(i + n) % len(REGIONS)], level_of_mobs, 8, rng).combatant
            for n in range(mob_count)
        ]
        res = run_tick_fight(players, mobs, rng)
        wins += res.won
        hp_left.append(res.hp_left_share)
        scores.append((res.enemy_hp_removed + res.hp_left_share) / 2)
    return wins / rounds, statistics.fmean(hp_left), statistics.fmean(scores)


def group_contribution(subclass_id: str, level: int, mods_by_sub: dict, mob_count: int,
                       rounds: int, rng: random.Random) -> tuple[float, float]:
    """Насколько команда сильнее с этим бойцом, чем с обычным ДД на его месте.

    Винрейт в групповом PvE почти двоичный (пачку либо выносят, либо она сносит
    группу), поэтому основная метрика - ОСТАВШЕЕСЯ HP команды: величина
    непрерывная и показывает запас прочности, а не только факт победы.
    Возвращает (прирост винрейта, прирост сводного КПД)."""
    base_win, base_hp, base_score = team_winrate_pve(
        [FILLER] * 3, level, mods_by_sub, mob_count, rounds, rng)
    sub_win, sub_hp, sub_score = team_winrate_pve(
        [subclass_id, FILLER, FILLER], level, mods_by_sub, mob_count, rounds, rng)
    return sub_win - base_win, sub_score - base_score


def pvp_contribution(subclass_id: str, level: int, mods_by_sub: dict, rounds: int,
                     rng: random.Random) -> tuple[float, float]:
    """То же для масс PvP: обе команды из ДД, в одной один боец заменён на
    проверяемого. Возвращает (винрейт команды, прирост к зеркальному бою).

    Зеркальный бой даёт НЕ 50%: часть боёв упирается в лимит ходов и не
    засчитывается победой ни одной стороне, поэтому опору печатаем явно."""
    enemy = [FILLER] * 3
    baseline = mass_pvp([FILLER] * 3, enemy, level, mods_by_sub, rounds, rng)
    with_sub = mass_pvp([subclass_id, FILLER, FILLER], enemy, level, mods_by_sub, rounds, rng)
    return with_sub, with_sub - baseline


# ----------------------------------------------------------------------------
# Вклад отдельного баффа
# ----------------------------------------------------------------------------


def buff_marginal_group(subclass_id: str, buff_id: str, level: int, rounds: int,
                        rng: random.Random) -> float:
    """Вклад баффа В ГРУППЕ. Групповые баффы («Только в бою с союзниками») в
    соло-замере всегда дают ноль - не потому что мёртвые, а потому что им
    некого поддерживать. Судить их можно только здесь."""
    team = [subclass_id, FILLER, FILLER]
    mods_without = {subclass_id: {}}
    mods_with = {subclass_id: modifiers_for([buff_id])}
    _, _, without = team_winrate_pve(team, level, mods_without, 6, rounds, rng)
    _, _, with_buff = team_winrate_pve(team, level, mods_with, 6, rounds, rng)
    return with_buff - without


GROUP_ONLY_CATEGORY = "group_support"


def _score(res: dict) -> float:
    """Сводный КПД боя: сколько снято с врагов и сколько осталось своего HP.
    Обе части непрерывны, поэтому счёт двигается и у тех, кто всегда
    проигрывает, и у тех, кто всегда выигрывает."""
    return (res["enemy_hp_removed"] + res["hp_left"]) / 2


def pick_difficulty(subclass_id: str, level: int, rng: random.Random, rounds: int) -> str:
    """Сложность, на которой подкласс НЕ упирается в пол или потолок: только там
    видно, что даёт отдельный бафф. Без этого у слабых подклассов все баффы
    читаются как «0%» просто потому, что бой проигран при любом раскладе."""
    best, best_gap = "двое", 99.0
    for diff in ("равный", "выше", "двое"):
        gap = abs(_score(solo_pve(subclass_id, level, {}, rounds, rng, diff)) - 0.5)
        if gap < best_gap:
            best, best_gap = diff, gap
    return best


def buff_marginal(subclass_id: str, buff_id: str, level: int, rounds: int,
                  rng: random.Random, difficulty: str) -> float:
    """Сколько даёт ОДИН бафф: разница сводного КПД с ним и без него."""
    without = _score(solo_pve(subclass_id, level, {}, rounds, rng, difficulty))
    with_buff = _score(solo_pve(subclass_id, level, modifiers_for([buff_id]), rounds, rng, difficulty))
    return with_buff - without


# ----------------------------------------------------------------------------
# Отчёт
# ----------------------------------------------------------------------------

BASE_CLASSES = ("warrior", "rogue", "mage")
ROLE_RU = {"dd": "ДД", "tank": "танк", "healer": "хилер", "support": "саппорт"}


def header(title: str) -> None:
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def scorecard(n: int, rng: random.Random, level: int = 50) -> None:
    """Короткая сводка для итераций по балансу: один экран вместо отчёта.

    Целевые коридоры (дизайн-решение зафиксировано в balance_config: Страж и
    Тёмный мистик осознанно слабее в дуэлях, их ценность - в группе):
      соло «двое»  40-75% у ДД, 25-55% у танка/саппорта/хилера, ноль - брак;
      дуэль        35-65% у ДД, 20-30% у танка и хилера;
      масс PvE     вклад не ниже -5%;
      масс PvP     винрейт команды 45-80%.
    """
    subs = list(REGISTRY)
    mixed = {s_: modifiers_for(preset_variants(s_).get("смешанный", [])) for s_ in subs}
    mirror = mass_pvp([FILLER] * 3, [FILLER] * 3, level, mixed, n, rng)
    duel = duel_tournament([(s_, "x", mixed[s_]) for s_ in subs], level, max(n // 4, 8), rng)
    # доля урона в группе: прямая проверка «саппорт не бьёт сильнее ДД»
    shares = group_pve(subs[:3] + subs[3:], level, mixed, n, rng)["damage_share"]
    print(f"{'подкласс':18} {'роль':8} {'равный':>8} {'двое':>7} {'дуэль':>7} "
          f"{'масс PvE':>9} {'масс PvP':>9} {'доля урона':>11}")
    for sub in subs:
        easy = solo_pve(sub, level, mixed[sub], n, rng, "равный")
        solo = solo_pve(sub, level, mixed[sub], n, rng, "двое")
        _, d_score = group_contribution(sub, level, mixed, 6, n, rng)
        pvp_team, _ = pvp_contribution(sub, level, mixed, n, rng)
        print(f"{REGISTRY[sub].title:18} {ROLE_RU[REGISTRY[sub].natural_role.value]:8} "
              f"{easy['winrate']:>7.0%} {solo['winrate']:>7.0%} {duel[(sub, 'x')]:>7.0%} "
              f"{d_score:>+9.0%} {pvp_team:>9.0%} {shares.get(sub, 0):>11.0%}")
    print("")
    print(f"Зеркальный масс PvP (опора): {mirror:.0%}")


def main() -> None:
    sys.stdout.reconfigure(line_buffering=True)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fast", action="store_true", help="меньше боёв, быстрый прогон")
    parser.add_argument("--seed", type=int, default=20260918)
    parser.add_argument("--scorecard", action="store_true",
                        help="короткая сводка вместо полного отчёта")
    args = parser.parse_args()
    n = 30 if args.fast else 120
    rng = random.Random(args.seed)
    level = 50
    if args.scorecard:
        scorecard(n, rng, level)
        return
    subs = list(REGISTRY)
    mixed = {s: modifiers_for(preset_variants(s).get("смешанный", [])) for s in subs}

    header("1. СОЛО PvE ПРОТИВ НАСТОЯЩИХ МОБОВ (уровень 50, пресет «смешанный»)")
    print(f"{'подкласс':18} {'роль':8} {'равный':>16} {'моб +10 ур.':>16} {'двое мобов':>16}")
    print(f"{'':18} {'':8} {'win / HP':>16} {'win / HP':>16} {'win / HP':>16}")
    for sub in subs:
        row = [f"{REGISTRY[sub].title:18} {ROLE_RU[REGISTRY[sub].natural_role.value]:8}"]
        for diff in ("равный", "выше", "двое"):
            r = solo_pve(sub, level, mixed[sub], n, rng, diff)
            row.append(f"{r['winrate']:>6.0%} /{r['hp_left']:>6.0%}   ")
        print("".join(row))
    print("\nБазовые классы до выбора подкласса (уровень 25, баффов ещё нет):")
    for cls in BASE_CLASSES:
        parts = [f"{cls:18} {'-':8}"]
        for diff in ("равный", "выше", "двое"):
            r = solo_pve(cls, 25, {}, n, rng, diff)
            parts.append(f"{r['winrate']:>6.0%} /{r['hp_left']:>6.0%}   ")
        print("".join(parts))

    header("2. ВЛИЯНИЕ СБОРКИ БАФФОВ (соло, сложность «двое мобов», уровень 50)")
    for sub in subs:
        print(f"\n{REGISTRY[sub].title} [{ROLE_RU[REGISTRY[sub].natural_role.value]}]")
        for name, ids in preset_variants(sub).items():
            r = solo_pve(sub, level, modifiers_for(ids), n, rng, "двое")
            print(f"   {name:12} win={r['winrate']:>5.0%}  HP={r['hp_left']:>5.0%}  ходов={r['turns']:>5.1f}")

    header("3. PvP 1x1: КРУГОВОЙ ТУРНИР НА ДУЭЛЬНОМ ДВИЖКЕ (уровень 50)")
    configs = [(s, "смешанный", mixed[s]) for s in subs]
    table = duel_tournament(configs, level, max(n // 4, 8), rng)
    for (sub, _), wr in sorted(table.items(), key=lambda kv: -kv[1]):
        print(f"   {REGISTRY[sub].title:18} {ROLE_RU[REGISTRY[sub].natural_role.value]:8} винрейт {wr:>6.0%}")

    header("4. МАСС PvE: ВКЛАД В ГРУППУ (3 бойца против 6 мобов, уровень 50)")
    print("Замеряется замена одного ДД на этот подкласс. 0 = ровно как ещё один ДД.")
    base_win, _, base_score = team_winrate_pve([FILLER] * 3, level, mixed, 6, n, rng)
    print(f"Опорная команда из трёх ДД: винрейт {base_win:.0%}, КПД {base_score:.0%}")
    print(f"Строка «{REGISTRY[FILLER].title}» - замена ДД на такого же ДД, то есть шум.")
    print("")
    for sub in subs:
        d_win, d_score = group_contribution(sub, level, mixed, 6, n, rng)
        print(f"   {REGISTRY[sub].title:18} {ROLE_RU[REGISTRY[sub].natural_role.value]:8} "
              f"винрейт {d_win:+.0%}   КПД команды {d_score:+.0%}")

    header("5. МАСС PvP 3x3: ВКЛАД В КОМАНДУ (уровень 50)")
    print("Обе стороны из ДД, в одной один боец заменён на проверяемого.")
    mirror = mass_pvp([FILLER] * 3, [FILLER] * 3, level, mixed, n, rng)
    print(f"Зеркальный бой ДД против таких же ДД: {mirror:.0%} побед "
          "(остальное - ничьи по лимиту ходов). Это опора.")
    print("")
    for sub in subs:
        winrate, delta = pvp_contribution(sub, level, mixed, n, rng)
        print(f"   {REGISTRY[sub].title:18} {ROLE_RU[REGISTRY[sub].natural_role.value]:8} "
              f"винрейт команды {winrate:>5.0%}  ({delta:+.0%} к опоре)")

    header("6. ВКЛАД КАЖДОГО МИКРОБАФФА (прирост сводного КПД в соло)")
    print("Сложность подбирается под подкласс: на его пределе, а не там, где "
          "он выигрывает или проигрывает при любом раскладе.")
    for sub in subs:
        diff = pick_difficulty(sub, level, rng, max(n // 3, 12))
        print("")
        print(f"{REGISTRY[sub].title} (сложность «{diff}»)")
        rows = []
        for b in buffs_of(sub):
            # групповые баффы меряем в группе, остальные - в соло
            if b.category == GROUP_ONLY_CATEGORY:
                delta = buff_marginal_group(sub, b.id, level, max(n // 3, 12), rng)
                rows.append((b.name + " (в группе)", delta))
            else:
                rows.append((b.name, buff_marginal(sub, b.id, level, max(n // 3, 12), rng, diff)))
        for name, delta in sorted(rows, key=lambda kv: -kv[1]):
            mark = "  <- мёртвый?" if abs(delta) < 0.005 else ""
            print(f"   {name:34} {delta:+.1%}{mark}")


if __name__ == "__main__":
    main()
