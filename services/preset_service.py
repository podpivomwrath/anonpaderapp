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
from models import Character, CharacterBuffPreset
from services import trial_service
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


async def save_preset(
    db: AsyncSession,
    character: Character,
    name: str,
    buff_ids: list[str],
    catalog: dict[str, BuffDef],
    preset_id: int | None = None,
) -> CharacterBuffPreset:
    """Создание нового пресета или изменение состава — платно (уровень 2)."""
    unlocked = await trial_service.unlocked_buff_ids(db, character.id)
    validate_preset(buff_ids, character.subclass, catalog, unlocked)
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


async def switch_active_preset(
    db: AsyncSession, character_id: int, preset_id: int
) -> CharacterBuffPreset:
    """Переключение между сохранёнными пресетами — бесплатно (уровень 1)."""
    presets = (
        await db.scalars(
            select(CharacterBuffPreset).where(
                CharacterBuffPreset.character_id == character_id
            )
        )
    ).all()
    target = next((p for p in presets if p.id == preset_id), None)
    if target is None:
        raise PresetValidationError("Пресет не найден")
    for preset in presets:
        preset.is_active = preset.id == preset_id
    return target
