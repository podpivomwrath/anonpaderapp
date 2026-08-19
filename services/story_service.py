"""Региональные сюжетные квесты (патч 18): каркас + линия Кряжа.

Одна активная сюжетная линия на регион персонажа (регион — постоянная
привязка, как у наставника/первого квеста). Квест 1.1 каждой линии —
существующий «убей 10» (services/quest_service.py), встроенный в сюжет:
эта служба НЕ дублирует его прогресс, только следит за переходом дальше
после его turn_in (см. advance_after_first_quest).

Состояние — CharacterStoryProgress: quest_step (id из content/story/<region>.json)
+ status ("active" — квест выдан, цель не достигнута; "ready" — цель
достигнута/бой выигран, ждёт разговора с наставником) + completed (линия
региона пройдена целиком).
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from game.combat import display
from game.content_loader import StoryLineDef, StoryQuestDef, load_story_line
from game.economy import story_config as sc
from game.world import grid
from models import Character, CharacterStats, CharacterStoryProgress
from services import experience_service, group_service, quest_service, wallet_service

_lines: dict[str, StoryLineDef] = {}

FALLBACK_NO_QUESTS_TEXT = (
    "📜 Никто не ждёт от тебя ничего. Пепельные Земли не дают поручений — "
    "здесь каждый идёт своей дорогой."
)

_DIR_WORDS = {
    (1, 0): "восток", (-1, 0): "запад", (0, 1): "север", (0, -1): "юг",
    (1, 1): "северо-восток", (-1, 1): "северо-запад",
    (1, -1): "юго-восток", (-1, -1): "юго-запад",
}


def compass_direction(px: int, py: int, tx: int, ty: int) -> str:
    """Направление словом от (px;py) к (tx;ty) — патч 21, пп. 4-5."""
    dx, dy = tx - px, ty - py
    if dx == 0 and dy == 0:
        return "ты уже на месте"
    sx = (dx > 0) - (dx < 0)
    sy = (dy > 0) - (dy < 0)
    return f"на {_DIR_WORDS[(sx, sy)]}"


def get_line(region: str) -> StoryLineDef:
    line = _lines.get(region)
    if line is None:
        line = load_story_line(region)
        _lines[region] = line
    return line


def _flatten(line: StoryLineDef) -> list[tuple[int, StoryQuestDef]]:
    return [(act.act, quest) for act in line.acts for quest in act.quests]


def _find(line: StoryLineDef, quest_id: str) -> tuple[int, StoryQuestDef] | None:
    for act_no, quest in _flatten(line):
        if quest.id == quest_id:
            return act_no, quest
    return None


def _next(line: StoryLineDef, quest_id: str) -> tuple[int, StoryQuestDef] | None:
    flat = _flatten(line)
    for idx, (_, quest) in enumerate(flat):
        if quest.id == quest_id:
            return flat[idx + 1] if idx + 1 < len(flat) else None
    return None


def format_text(text: str, character: Character) -> str:
    """Подставляет {nickname} (никнейм персонажа) в текст контента, если он
    там есть (патч 19: реплики Корня обращаются к игроку по имени). Текст без
    плейсхолдера возвращается как есть."""
    return text.format(nickname=character.name) if "{nickname}" in text else text


def _format_assign(quest: StoryQuestDef, character: Character) -> str:
    text = format_text(quest.assign_text, character)
    if quest.target_x is not None and quest.target_y is not None:
        direction = compass_direction(character.pos_x, character.pos_y, quest.target_x, quest.target_y)
        text += (
            f"\n\n📍 Ориентир: ({quest.target_x};{quest.target_y}) — {quest.target_label} · {direction}"
        )
    return text


async def _get_progress(
    db: AsyncSession, character_id: int, region: str
) -> CharacterStoryProgress | None:
    return await db.scalar(
        select(CharacterStoryProgress).where(
            CharacterStoryProgress.character_id == character_id,
            CharacterStoryProgress.region == region,
        )
    )


async def _get_or_create_progress(db: AsyncSession, character: Character) -> CharacterStoryProgress:
    row = await _get_progress(db, character.id, character.region)
    if row is None:
        line = get_line(character.region)
        first_act, first_quest = line.acts[0].act, line.acts[0].quests[0]
        row = CharacterStoryProgress(
            character_id=character.id, region=character.region,
            act=first_act, quest_step=first_quest.id, status="active",
        )
        db.add(row)
        await db.flush()
    return row


async def _advance_pointer(
    db: AsyncSession, row: CharacterStoryProgress, line: StoryLineDef, finished_quest_id: str
) -> None:
    nxt = _next(line, finished_quest_id)
    if nxt is None:
        row.completed = True
    else:
        act_no, quest = nxt
        row.act = act_no
        row.quest_step = quest.id
        row.status = "active"
        row.quest_seen = False  # патч 21: новый шаг ещё не показан — пометка/пинг
    await db.flush()


async def _grant(
    db: AsyncSession, character: Character, stats: CharacterStats, quest: StoryQuestDef
) -> tuple[str, experience_service.LevelUp, "group_service.LevelGapKick | None"]:
    levelup = experience_service.add_experience(character, stats, quest.xp_reward)
    group_kick = None
    if levelup.levels_gained > 0:
        group_kick = await group_service.enforce_level_gap(db, character)
    lines = []
    if quest.xp_reward:
        lines.append(display.xp_delta_line(levelup.xp_awarded, premium=levelup.premium_applied))
    if quest.gold_reward:
        wallet = await wallet_service.deposit(db, character.id, "farm", quest.gold_reward)
        lines.append(display.gold_delta_line(quest.gold_reward, wallet.farm_currency))
    return "\n".join(lines), levelup, group_kick


@dataclass
class StoryTurnResult:
    text: str
    levels_gained: int = 0
    new_level: int = 1
    region_completed: bool = False
    group_kick: "group_service.LevelGapKick | None" = None  # патч 51, ч.2


async def get_progress(db: AsyncSession, character: Character) -> CharacterStoryProgress | None:
    """Публичный доступ к строке прогресса (для диагностики/тестов) — None,
    если сюжет региона ещё ни разу не выдавался."""
    return await _get_progress(db, character.id, character.region)


async def current_quest_def(db: AsyncSession, character: Character) -> StoryQuestDef | None:
    """Текущий шаг сюжета — None, если линия региона уже пройдена целиком."""
    row = await _get_or_create_progress(db, character)
    if row.completed or row.quest_step is None:
        return None
    line = get_line(character.region)
    found = _find(line, row.quest_step)
    return found[1] if found is not None else None


async def advance_after_first_quest(db: AsyncSession, character: Character) -> str:
    """Вызывать сразу после успешного services.quest_service.turn_in() —
    продвигает сюжетный указатель за первый квест и возвращает его
    transition_text (добавляется к похвале наставника). Идемпотентно."""
    row = await _get_or_create_progress(db, character)
    if row.completed or row.quest_step is None:
        return ""
    line = get_line(character.region)
    found = _find(line, row.quest_step)
    if found is None or found[1].kind != "first_quest":
        return ""
    quest = found[1]
    await _advance_pointer(db, row, line, quest.id)
    return format_text(quest.transition_text, character)


async def visit_mentor(
    db: AsyncSession, character: Character, stats: CharacterStats
) -> StoryTurnResult | None:
    """Разговор с наставником для НЕ-first_quest шагов сюжета. None — линия
    региона уже пройдена целиком, либо текущий шаг — легаси-квест 1.1
    (им ведает services/quest_service.py, см. advance_after_first_quest)."""
    row = await _get_or_create_progress(db, character)
    if row.completed or row.quest_step is None:
        return None
    line = get_line(character.region)
    found = _find(line, row.quest_step)
    if found is None:
        return None
    _, quest = found
    if quest.kind == "first_quest":
        return None

    if quest.kind == "subclass_gate":
        if character.subclass is None:
            row.quest_seen = True
            await db.flush()
            return StoryTurnResult(text=format_text(quest.assign_text, character))
        # Подкласс уже выбран, но хук в list_keeper почему-то не продвинул
        # (гонка/рестарт бота между шагами) — подстраховка, продвигаем здесь.
        reward_text, levelup, group_kick = await _grant(db, character, stats, quest)
        await _advance_pointer(db, row, line, quest.id)
        text = f"{format_text(quest.assign_text, character)}\n\n{reward_text}".strip()
        return StoryTurnResult(text, levelup.levels_gained, levelup.new_level, row.completed, group_kick)

    if quest.kind == "city_scene":
        reward_text, levelup, group_kick = await _grant(db, character, stats, quest)
        await _advance_pointer(db, row, line, quest.id)
        assign = format_text(quest.assign_text, character)
        text = f"{assign}\n\n{reward_text}" if reward_text else assign
        return StoryTurnResult(text, levelup.levels_gained, levelup.new_level, row.completed, group_kick)

    if quest.kind == "travel_combat":
        if row.status == "ready":
            reward_text, levelup, group_kick = await _grant(db, character, stats, quest)
            await _advance_pointer(db, row, line, quest.id)
            ret = format_text(quest.return_text, character)
            text = f"{ret}\n\n{reward_text}" if reward_text else ret
            return StoryTurnResult(text, levelup.levels_gained, levelup.new_level, row.completed, group_kick)
        row.quest_seen = True
        await db.flush()
        return StoryTurnResult(text=_format_assign(quest, character))

    return None


async def check_zone_trigger(db: AsyncSession, character: Character) -> StoryQuestDef | None:
    """Активный travel_combat-шаг, чья цель в радиусе (STORY_TRIGGER_RADIUS)
    от текущей позиции игрока — вызывающий должен показать arrival_text и
    начать сюжетный бой. None — триггерить нечего."""
    row = await _get_progress(db, character.id, character.region)
    if row is None or row.completed or row.status != "active" or row.quest_step is None:
        return None
    line = get_line(character.region)
    found = _find(line, row.quest_step)
    if found is None:
        return None
    quest = found[1]
    if quest.kind != "travel_combat" or quest.target_x is None or quest.target_y is None:
        return None
    dx = character.pos_x - quest.target_x
    dy = character.pos_y - quest.target_y
    if grid.chebyshev_distance(dx, dy) > sc.STORY_TRIGGER_RADIUS:
        return None
    return quest


async def mark_ready(db: AsyncSession, character: Character, quest_id: str) -> None:
    """Вызывать после победы в сюжетном бою (последнем в цепочке, если их
    несколько) — цель достигнута, ждём разговора с наставником."""
    row = await _get_progress(db, character.id, character.region)
    if row is None or row.quest_step != quest_id:
        return  # устарело (уже продвинуто иначе) — молча игнорируем
    row.status = "ready"
    row.quest_seen = False  # патч 21: сдача требует нового визита — пометка/пинг снова
    await db.flush()


async def advance_past_subclass_gate(
    db: AsyncSession, character: Character, stats: CharacterStats
) -> str:
    """Хук сразу после выбора подкласса (патч 12, services/subclass_service.py)
    — если сюжет стоит на паузе на subclass_gate-квесте, продвигает его
    автоматически (без отдельного визита к наставнику). Возвращает строку
    числовой награды (пусто, если сюжет ни при чём/не на этом шаге)."""
    row = await _get_progress(db, character.id, character.region)
    if row is None or row.completed or row.quest_step is None:
        return ""
    line = get_line(character.region)
    found = _find(line, row.quest_step)
    if found is None or found[1].kind != "subclass_gate":
        return ""
    quest = found[1]
    # group_kick здесь не пробрасывается наверх (узкий хук без доступа к
    # peer_id вызывающего) — реалистично недостижимо: левелап на этом шаге
    # сюжета требует лишь что игрок ТОЛЬКО ЧТО выбрал подкласс, крайне редкое
    # сочетание с "уже состоит в группе с разрывом ровно на грани лимита".
    reward_text, _levelup, _group_kick = await _grant(db, character, stats, quest)
    await _advance_pointer(db, row, line, quest.id)
    return reward_text  # текст сцены уже был показан игроку раньше (assign_text)


async def mentor_badge_active(db: AsyncSession, character: Character) -> bool:
    """Пометка [🧙 Наставник ❗] (патч 21) — есть что взять или что сдать."""
    quest = await current_quest_def(db, character)
    if quest is None:
        return False  # линия региона пройдена целиком
    if quest.kind == "first_quest":
        peek = await quest_service.peek_progress(db, character)
        if peek is None:
            return False
        return peek.status is None or peek.status == "ready"
    row = await get_progress(db, character)
    if quest.kind == "travel_combat":
        return row.status == "ready" or not row.quest_seen
    return not row.quest_seen  # city_scene / subclass_gate


async def quest_summary_line(db: AsyncSession, character: Character) -> str | None:
    """Строка активного сюжетного квеста для сводки локации (патч 21, п.4):
    '📜 [Название] → (x;y) · направление' / '📜 [Название] → вернуться в город'.
    None — показывать нечего (первый квест — легаси, не отображается тут;
    либо линия региона пройдена целиком)."""
    quest = await current_quest_def(db, character)
    if quest is None or quest.kind == "first_quest":
        return None
    if quest.kind == "travel_combat":
        row = await get_progress(db, character)
        if row.status == "ready":
            return f"📜 {quest.title} → вернуться к наставнику"
        direction = compass_direction(character.pos_x, character.pos_y, quest.target_x, quest.target_y)
        return f"📜 {quest.title} → ({quest.target_x}; {quest.target_y}) · {direction}"
    return f"📜 {quest.title} → вернуться в город"


async def quest_reminder_text(db: AsyncSession, character: Character, mentor_name: str) -> str:
    """Текст команды /квест (патч 21, п.5)."""
    quest = await current_quest_def(db, character)
    if quest is None:
        return FALLBACK_NO_QUESTS_TEXT

    if quest.kind == "first_quest":
        peek = await quest_service.peek_progress(db, character)
        if peek is None or peek.status is None:
            return f"У тебя нет активного задания. {mentor_name} ждёт тебя в городе."
        if peek.status == "ready":
            return f"📜 {peek.title}: цель достигнута — возвращайся к {mentor_name}."
        return f"📜 {peek.title}: {peek.progress_label} {peek.progress}/{peek.target_count}."

    if quest.kind == "travel_combat":
        row = await get_progress(db, character)
        if row.status == "ready":
            return f"📜 {quest.title}: цель достигнута — возвращайся к {mentor_name}."
        return _format_assign(quest, character)

    if quest.kind == "subclass_gate":
        if character.subclass is None:
            return format_text(quest.assign_text, character)
        return f"У тебя нет активного задания. {mentor_name} ждёт тебя в городе."

    return format_text(quest.assign_text, character)  # city_scene
