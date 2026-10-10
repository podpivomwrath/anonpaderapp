"""Разломы: этапы боя. Чистая логика поверх session/resolver - без БД и VK,
как raid_field.py; оркестрация (рассылка, награды, смена этапов) -
bot/handlers/raid_combat.py, тем же путём, что и рейды 60 уровня.

Противники - обычные мобы кольца разлома (те же формулы, что
encounters.spawn_mob), усиленные множителями из rift_config. Уровень -
по группе: самый старший участник, но в пределах уровней разлома.

Интерфейс этапа тот же, что у этапов поля: setup(session) -> строки,
after_tick(session, result, rng) -> StageTick, reward_ids.
"""

import random

from game.combat import balance_config as bc
from game.combat import formulas
from game.combat.raid_field import StageTick, _kill, _players, _strike
from game.combat.resolver import TickResult
from game.combat.session import CombatantState, CombatSessionState, build_combatant
from game.economy import rift_config as rc
from game.world import grid
from game.world import world_config as wc
from game.world.encounters import _scale_stats_split, balanced_mob_stats


def build_mob(
    id: int, name: str, level: int, ring: int, hp_mult: float, dmg_mult: float,
    primary: str = "str", label: str = "бьёт",
) -> CombatantState:
    """Моб кольца ring уровня level, усиленный hp_mult/dmg_mult."""
    zone = grid.zone_level_range(wc.ring_bounds(ring)[0])
    hp = bc.MOB_HP_MULTIPLIER * formulas.mob_ring_multiplier(*zone) * hp_mult
    dmg = bc.MOB_DAMAGE_MULTIPLIER * formulas.mob_ring_damage_multiplier(*zone) * dmg_mult
    stats = _scale_stats_split(balanced_mob_stats(level, primary), hp, dmg)
    mob = build_combatant(id=id, side=1, kind="mob", name=name, level=level, stats=stats, primary_stat=primary)
    mob.scripted_hit = _strike(label, 1.0)
    return mob


class _Stage:
    """Общая основа: нумерация id, уровень и кольцо разлома."""

    #: признак этапа разлома для оркестрации (bot/handlers/raid_combat.py)
    rift = True
    is_boss = False

    def __init__(self, start_id: int, level: int, ring: int, size: int) -> None:
        self._next_id = start_id
        self.level = level
        self.ring = ring
        self.size = size
        self.ticks = 0
        self.ids: list[int] = []
        #: поправка типа (HP, урон) - ставит build_stage
        self.power: tuple[float, float] = (1.0, 1.0)

    def _new_id(self) -> int:
        self._next_id += 1
        return self._next_id

    def _mob(self, name: str, hp: float, dmg: float, primary: str = "str", label: str = "бьёт") -> CombatantState:
        hp_k, dmg_k = self.power
        return build_mob(self._new_id(), name, self.level, self.ring, hp * hp_k, dmg * dmg_k, primary, label)

    def _boss_hp(self) -> float:
        return rc.BOSS_HP * self.size * rc.HP_PER_SLOT

    @property
    def reward_ids(self) -> set[int]:
        return set(self.ids)

    def after_tick(self, session: CombatSessionState, result: TickResult, rng: random.Random) -> StageTick:
        self.ticks += 1
        return StageTick()


class WaveStage(_Stage):
    """Волна одинаковых противников, без механик."""

    def __init__(self, start_id, level, ring, size, name: str, count: int, *, elite: bool = False,
                 primary: str = "str", label: str = "бьёт") -> None:
        super().__init__(start_id, level, ring, size)
        self.name, self.count, self.elite = name, count, elite
        self.primary, self.label = primary, label

    def setup(self, session: CombatSessionState) -> list[str]:
        hp, dmg = (rc.ELITE_HP, rc.ELITE_DMG) if self.elite else (rc.WAVE_HP, rc.WAVE_DMG)
        for _ in range(self.count):
            mob = self._mob(self.name, hp, dmg, self.primary, self.label)
            self.ids.append(mob.id)
            session.add(mob)
        return []


class _BossStage(_Stage):
    is_boss = True
    name = ""
    primary = "str"
    label = "бьёт"

    def setup(self, session: CombatSessionState) -> list[str]:
        boss = self._mob(self.name, self._boss_hp(), rc.BOSS_DMG, self.primary, self.label)
        self.boss_id = boss.id
        self.ids.append(boss.id)
        session.add(boss)
        return self.opening()

    def opening(self) -> list[str]:
        return []

    def boss(self, session: CombatSessionState) -> CombatantState:
        return session.combatants[self.boss_id]


class MatriarchStage(_BossStage):
    """Гнездо осколков: раз в SHARD_EVERY ходов Матка выпускает осколок. Не
    добитый за SHARD_FUSE ходов - взрывается по всем игрокам."""

    name = "Матка осколков"
    label = "давит"

    def __init__(self, *args) -> None:
        super().__init__(*args)
        self.shards: dict[int, int] = {}  # id осколка -> ход появления

    def opening(self) -> list[str]:
        return ["🪨 Матка выпускает осколки - добивайте их, пока не взорвались."]

    def after_tick(self, session, result, rng) -> StageTick:
        self.ticks += 1
        out = StageTick()
        if not self.boss(session).alive:
            # Осколки без Матки рассыпаются. Движок о них не знает и бой сам
            # не закончил бы - этап закрывает оркестрация (cleared).
            alive = [sid for sid in self.shards if session.combatants[sid].alive]
            for sid in alive:
                _kill(session.combatants[sid])
            self.shards.clear()
            out.cleared = bool(alive)
            return out
        for sid, born in list(self.shards.items()):
            shard = session.combatants[sid]
            if not shard.alive:
                del self.shards[sid]
                continue
            if self.ticks - born >= rc.SHARD_FUSE:
                _kill(shard)
                del self.shards[sid]
                out.lines.append("💥 Осколок взрывается! Каменная крошка бьёт по всем.")
                for player in _players(session):
                    player.current_hp -= max(1, round(player.max_hp * rc.SHARD_BLAST))
                    if player.current_hp <= 0:
                        player.current_hp = 0
                        out.deaths.append(player.id)
        if self.ticks % rc.SHARD_EVERY == 0:
            shard = self._mob("Осколок", rc.SHARD_HP, 0.0, label="царапает")
            shard.scripted_hit = lambda mob, s, r: []
            session.add(shard)
            self.shards[shard.id] = self.ticks
            out.lines.append(f"🪨 От Матки отваливается осколок. Взорвётся через {rc.SHARD_FUSE} хода.")
        return out


class KeeperStage(_BossStage):
    """Пепельная крипта: раз в STONE_EVERY ходов Хранитель каменеет на
    STONE_TICKS ходов - урон по нему почти не проходит. Ход до этого он
    замирает: время перевязаться, а не тратить навыки."""

    name = "Хранитель праха"
    primary = "int"
    label = "осыпает прахом"

    def __init__(self, *args) -> None:
        super().__init__(*args)
        self.stone_left = 0

    def opening(self) -> list[str]:
        return ["⚱️ Хранитель временами каменеет - тогда его почти не пробить."]

    def after_tick(self, session, result, rng) -> StageTick:
        self.ticks += 1
        out = StageTick()
        boss = self.boss(session)
        if not boss.alive:
            return out
        if self.stone_left > 0:
            self.stone_left -= 1
            if self.stone_left == 0:
                boss.buff_modifiers["incoming_damage_reduction"] = 0.0
                out.lines.append("⚱️ Камень на Хранителе трескается - он снова уязвим.")
        elif self.ticks % rc.STONE_EVERY == rc.STONE_EVERY - 1:
            out.lines.append("⚱️ Хранитель замирает. Кожа серееет - следующий ход он будет камнем.")
        elif self.ticks % rc.STONE_EVERY == 0:
            self.stone_left = rc.STONE_TICKS
            boss.buff_modifiers["incoming_damage_reduction"] = rc.STONE_REDUCTION
            out.lines.append(f"🗿 Хранитель каменеет на {rc.STONE_TICKS} хода: урон почти не проходит.")
        return out


class DeepStage(_BossStage):
    """Кровавый омут: Тот, что на дне, злеет каждые RAGE_EVERY ходов (+урон),
    а каждые DRAG_EVERY ходов утягивает одного игрока под воду - тот
    пропускает ход."""

    name = "Тот, что на дне"
    label = "хлещет корнями"

    def opening(self) -> list[str]:
        return ["🩸 Тот, что на дне, злеет с каждым ходом. Медлить нельзя."]

    def after_tick(self, session, result, rng) -> StageTick:
        self.ticks += 1
        out = StageTick()
        boss = self.boss(session)
        if not boss.alive:
            return out
        if self.ticks % rc.RAGE_EVERY == 0:
            rage = rc.RAGE_STEP * (self.ticks // rc.RAGE_EVERY)
            boss.buff_modifiers["damage_bonus"] = rage
            out.lines.append(f"🩸 Омут вскипает: Тот, что на дне, бьёт сильнее (+{round(rage * 100)}%).")
        if self.ticks % rc.DRAG_EVERY == 0:
            players = _players(session)
            if players:
                victim = rng.choice(players)
                out.frozen.append(victim.id)
                out.lines.append(f"🌊 Корень утягивает {victim.name} под воду: ход пропущен.")
        return out


class DoubleStage(_BossStage):
    """Зеркальный разлом: на SPLIT_AT здоровья Двойник раскалывается -
    вторая половина забирает половину оставшегося HP. Убить нужно обе."""

    name = "Двойник"
    primary = "agi"
    label = "режет"

    def __init__(self, *args) -> None:
        super().__init__(*args)
        self.split = False

    def opening(self) -> list[str]:
        return ["🪞 На половине здоровья Двойник раскалывается надвое."]

    def after_tick(self, session, result, rng) -> StageTick:
        self.ticks += 1
        out = StageTick()
        boss = self.boss(session)
        if self.split or not boss.alive or boss.current_hp > boss.max_hp * rc.SPLIT_AT:
            return out
        self.split = True
        half = max(1, boss.current_hp // 2)
        twin = self._mob("Отражение Двойника", self._boss_hp(), rc.BOSS_DMG, self.primary, self.label)
        twin.max_hp = boss.max_hp
        twin.current_hp = half
        boss.current_hp -= half
        session.add(twin)
        self.ids.append(twin.id)
        out.lines.append("🪞 Двойник раскалывается надвое! Убейте обе половины.")
        return out


#: Этапы по типам: фабрики (start_id, level, ring, size) -> этап.
def _wave(name: str, count: int, **kw):
    return lambda start, level, ring, size: WaveStage(start, level, ring, size, name, count, **kw)


def _boss(cls):
    return lambda start, level, ring, size: cls(start, level, ring, size)


STAGES = {
    "shard_nest": (_wave("Осколочный ползун", 3, primary="agi", label="скребёт"), _boss(MatriarchStage)),
    "ash_crypt": (_wave("Пепельный гуль", 3, label="рвёт"), _boss(KeeperStage)),
    "blood_pool": (
        _wave("Утопленник", 4, label="хватает"),
        _wave("Страж омута", 2, elite=True, label="бьёт цепью"),
        _boss(DeepStage),
    ),
    "mirror_rift": (_wave("Отражение", 4, primary="agi", label="режет"), _boss(DoubleStage)),
}


def stage_count(kind: str) -> int:
    return len(STAGES[kind])


def build_stage(kind: str, stage: int, start_id: int, level: int, ring: int):
    """stage - с единицы."""
    size = rc.RIFT_TYPES[kind].max_size
    built = STAGES[kind][stage - 1](start_id, level, ring, size)
    built.power = rc.TYPE_POWER[kind]
    return built
