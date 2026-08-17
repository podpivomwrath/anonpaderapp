"""Пресеты микробаффов и респек (п.7-8 дизайна).

Три уровня стоимости:
  1. переключение между сохранёнными пресетами — бесплатно, мгновенно;
  2. создание нового пресета / изменение состава — платно (farm-валюта);
  3. полный ресет класса — платно (донат-валюта), см. respec_service.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from game.combat import balance_config as bc
from game.content_loader import BuffDef
from game.economy import premium_config as pc
from models import Character, CharacterBuffPreset
from services import premium_service, trial_service
from services.wallet_service import charge


class PresetValidationError(Exception):
    """Пресет нарушает правила сборки."""


def validate_preset(
    buff_ids: list[str],
    subclass_id: str | None,
    catalog: dict[str, BuffDef],
    unlocked_buff_ids: set[str] | None = None,
) -> None:
    """Правила валидации (п.7, гейт баффов — патч 12):
    - 3-5 баффов, без дублей;
    - все баффы существуют и принадлежат пулу подкласса персонажа;
    - каждый бафф подкласса должен быть открыт испытанием (unlocked_buff_ids=None
      отключает эту проверку — используется прямыми юнит-тестами validate_preset);
    - минимум 1 бафф из категории обороны ИЛИ контроль/утилити
      (нельзя собрать чистый моно-урон пресет).
    """
    if not (bc.PRESET_MIN_BUFFS <= len(buff_ids) <= bc.PRESET_MAX_BUFFS):
        raise PresetValidationError(
            f"В пресете должно быть от {bc.PRESET_MIN_BUFFS} до {bc.PRESET_MAX_BUFFS} баффов"
        )
    if len(set(buff_ids)) != len(buff_ids):
        raise PresetValidationError("Баффы в пресете не должны повторяться")

    categories: set[str] = set()
    for buff_id in buff_ids:
        buff = catalog.get(buff_id)
        if buff is None:
            raise PresetValidationError(f"Неизвестный бафф: {buff_id}")
        if buff.subclass is not None and buff.subclass != subclass_id:
            raise PresetValidationError(
                f"Бафф {buff_id} принадлежит пулу другого подкласса"
            )
        if (
            buff.subclass is not None
            and unlocked_buff_ids is not None
            and buff_id not in unlocked_buff_ids
        ):
            raise PresetValidationError(f"Бафф {buff_id} ещё не открыт — пройди испытание")
        categories.add(buff.category)

    if not categories & bc.PRESET_REQUIRED_CATEGORIES:
        raise PresetValidationError(
            "Минимум один бафф должен быть из категории обороны или контроль/утилити"
        )


def effective_preset_slots(character: Character) -> int:
    """Патч 50: купленные слоты (character.preset_slots) + бонусный слот
    Метки Хранителя, пока она активна. Не мутирует preset_slots — бонус
    просто не учитывается, когда премиум истёк (пресеты сверх купленного
    лимита остаются сохранёнными, но недоступными для сохранения/переключения,
    см. save_preset/switch_active_preset)."""
    bonus = pc.PRESET_SLOT_BONUS if premium_service.is_premium(character) else 0
    return character.preset_slots + bonus


def next_slot_cost(current_slots: int) -> int:
    """Цена покупки СЛЕДУЮЩЕГО слота пресета (патч 14, ч.3)."""
    if current_slots >= len(bc.PRESET_SLOT_COSTS):
        raise PresetValidationError("Все слоты пресетов уже куплены")
    return bc.PRESET_SLOT_COSTS[current_slots]


async def buy_preset_slot(db: AsyncSession, character: Character) -> Character:
    """Покупка дополнительного слота пресета за золото — растущая цена."""
    cost = next_slot_cost(character.preset_slots)
    await charge(db, character.id, "farm", cost)
    character.preset_slots += 1
    await db.flush()
    return character


async def save_preset(
    db: AsyncSession,
    character: Character,
    name: str,
    buff_ids: list[str],
    catalog: dict[str, BuffDef],
    preset_id: int | None = None,
) -> CharacterBuffPreset:
    """Создание нового пресета или изменение состава — платно (уровень 2).
    Новый пресет нельзя создать сверх купленных слотов (патч 14, ч.3)."""
    unlocked = await trial_service.unlocked_buff_ids(db, character.id)
    validate_preset(buff_ids, character.subclass, catalog, unlocked)

    if preset_id is None:
        existing_count = len(
            (
                await db.scalars(
                    select(CharacterBuffPreset).where(
                        CharacterBuffPreset.character_id == character.id
                    )
                )
            ).all()
        )
        if existing_count >= effective_preset_slots(character):
            raise PresetValidationError(
                "Нет свободных слотов пресетов — купи ещё один в разделе «Персонаж»"
            )

    await charge(db, character.id, "farm", bc.PRESET_CHANGE_COST_FARM)

    if preset_id is not None:
        preset = await db.get(CharacterBuffPreset, preset_id)
        if preset is None or preset.character_id != character.id:
            raise PresetValidationError("Пресет не найден")
        preset.name = name
        preset.buff_ids = buff_ids
    else:
        preset = CharacterBuffPreset(
            character_id=character.id, name=name, buff_ids=buff_ids
        )
        db.add(preset)
    await db.flush()
    return preset


async def get_active_preset(db: AsyncSession, character_id: int) -> CharacterBuffPreset | None:
    return await db.scalar(
        select(CharacterBuffPreset).where(
            CharacterBuffPreset.character_id == character_id,
            CharacterBuffPreset.is_active.is_(True),
        )
    )


def resolve_buff_modifiers(buff_ids: list[str], catalog: dict[str, BuffDef]) -> dict[str, float]:
    """Мерж stat_modifiers всех баффов активного пресета в один словарь
    (патч 14, ч.3) — подаётся в build_combatant аналогично gear_bonus (патч 11)."""
    merged: dict[str, float] = {}
    for buff_id in buff_ids:
        buff = catalog.get(buff_id)
        if buff is not None:
            merged.update(buff.stat_modifiers)
    return merged


async def resolve_active_modifiers(db: AsyncSession, character: Character) -> dict[str, float]:
    """Шорткат: активный пресет персонажа → смерженные stat_modifiers
    (патч 14, ч.3). Пусто, если подкласс не выбран или пресет не активирован."""
    if character.subclass is None:
        return {}
    active = await get_active_preset(db, character.id)
    if active is None:
        return {}
    from game.content_loader import load_content

    return resolve_buff_modifiers(active.buff_ids, load_content().buffs)


async def switch_active_preset(
    db: AsyncSession, character: Character, preset_id: int
) -> CharacterBuffPreset:
    """Переключение между сохранёнными пресетами — бесплатно (уровень 1).

    Патч 50: если премиум истёк, а пресетов сохранено больше, чем действующий
    (без бонуса) лимит слотов — "лишние" (по порядку создания, id) не
    удаляются, но переключиться на них нельзя, пока премиум не продлён.
    Уже АКТИВНЫЙ пресет продолжает действовать в бою независимо от этого —
    правило касается только смены активного, не отбирает уже включённый."""
    presets = (
        await db.scalars(
            select(CharacterBuffPreset)
            .where(CharacterBuffPreset.character_id == character.id)
            .order_by(CharacterBuffPreset.id)
        )
    ).all()
    target = next((p for p in presets if p.id == preset_id), None)
    if target is None:
        raise PresetValidationError("Пресет не найден")
    slot_index = presets.index(target)
    if slot_index >= effective_preset_slots(character):
        raise PresetValidationError(
            "Этот пресет вне доступных слотов — продли Метку Хранителя или купи слот"
        )
    for preset in presets:
        preset.is_active = preset.id == preset_id
    return target
