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
from services import premium_service, subclass_service, trial_service
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
      отключает эту проверку — используется прямыми юнит-тестами validate_preset).

    Ограничения по категориям НЕТ: игрок волен собрать любые 5 баффов своего
    пула, включая чистый урон. Раньше требовался хотя бы один бафф обороны или
    контроля — правило снято сознательно, состав сборки остаётся выбором игрока.
    """
    if not (bc.PRESET_MIN_BUFFS <= len(buff_ids) <= bc.PRESET_MAX_BUFFS):
        raise PresetValidationError(
            f"В пресете должно быть от {bc.PRESET_MIN_BUFFS} до {bc.PRESET_MAX_BUFFS} баффов"
        )
    if len(set(buff_ids)) != len(buff_ids):
        raise PresetValidationError("Баффы в пресете не должны повторяться")

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
            raise PresetValidationError(f"Бафф {buff_id} ещё не открыт - пройди испытание")


def preset_subclass(preset: CharacterBuffPreset) -> str | None:
    """Чей пресет: подкласс его баффов. Пул баффов у каждого подкласса свой,
    так что пресет принадлежит ровно одному (2026-10-19: пресеты больше не
    удаляются при смене подкласса - их просто не видно у другого)."""
    from game.content_loader import load_content

    buffs = load_content().buffs
    for buff_id in preset.buff_ids or []:
        buff = buffs.get(buff_id)
        if buff is not None:
            return buff.subclass
    return None


def belongs(preset: CharacterBuffPreset, subclass: str | None) -> bool:
    owner = preset_subclass(preset)
    return subclass is not None and (owner is None or owner == subclass)


async def presets_of(db: AsyncSession, character: Character) -> list[CharacterBuffPreset]:
    """Пресеты текущего подкласса, по порядку создания."""
    rows = (
        await db.scalars(
            select(CharacterBuffPreset)
            .where(CharacterBuffPreset.character_id == character.id)
            .order_by(CharacterBuffPreset.id)
        )
    ).all()
    return [p for p in rows if belongs(p, subclass_service.buff_pool(character))]


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
    """Создание нового пресета - платно, изменение состава уже созданного -
    бесплатно (2026-10-16).
    Новый пресет нельзя создать сверх купленных слотов (патч 14, ч.3)."""
    unlocked = await trial_service.unlocked_buff_ids(db, character.id)
    validate_preset(buff_ids, subclass_service.buff_pool(character), catalog, unlocked)

    if preset_id is None:
        # Слоты - на подкласс: пресеты прежних подклассов места не занимают.
        existing_count = len(await presets_of(db, character))
        if existing_count >= effective_preset_slots(character):
            raise PresetValidationError(
                "Нет свободных слотов пресетов - купи ещё один в разделе «Персонаж»"
            )

    # Создание нового пресета платное, пересбор уже созданного - бесплатно
    # (2026-10-16, решение владельца).
    if preset_id is None:
        await charge(db, character.id, "farm", bc.PRESET_CHANGE_COST_FARM)

    if preset_id is not None:
        preset = await db.get(CharacterBuffPreset, preset_id)
        if preset is None or preset.character_id != character.id or not belongs(preset, subclass_service.buff_pool(character)):
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
    """Активный пресет ТЕКУЩЕГО подкласса: у каждого подкласса свой активный."""
    character = await db.get(Character, character_id)
    if character is None:
        return None
    rows = (
        await db.scalars(
            select(CharacterBuffPreset).where(
                CharacterBuffPreset.character_id == character_id,
                CharacterBuffPreset.is_active.is_(True),
            )
        )
    ).all()
    return next((p for p in rows if belongs(p, subclass_service.buff_pool(character))), None)


def preset_rule_hint(catalog_labels: dict[str, str] | None = None) -> str:
    """Правило состава пресета словами - чтобы клиент его не пересказывал.

    Раньше клиент пересказывал правило сам и врал: писал «хотя бы один - не
    урон», хотя групповая поддержка требованию не удовлетворяла. Само
    ограничение по категориям снято, но текст остаётся на сервере - чтобы
    следующее изменение правил снова не разошлось с экраном.
    """
    return (
        f"Выбери от {bc.PRESET_MIN_BUFFS} до {bc.PRESET_MAX_BUFFS} баффов - любых "
        "из своего пула."
    )


#: Суффиксы ключей, где меньшее значение выгоднее игроку: «перезарядка N ходов»
#: и «срабатывает раз в N ходов». Всё остальное — прибавки, там больше = лучше.
LOWER_IS_BETTER_SUFFIXES = ("_cooldown", "_interval")


def is_lower_better(key: str) -> bool:
    return key.endswith(LOWER_IS_BETTER_SUFFIXES)


def resolve_buff_modifiers(buff_ids: list[str], catalog: dict[str, BuffDef]) -> dict[str, float]:
    """Мерж stat_modifiers всех баффов активного пресета в один словарь
    (патч 14, ч.3) — подаётся в build_combatant аналогично gear_bonus (патч 11).

    Патч 56, общее правило: модификаторы ОДНОГО типа НЕ складываются, берётся
    БОЛЬШИЙ. Раньше здесь был dict.update, то есть побеждал последний бафф в
    списке — при двух баффах с одним ключом результат зависел от порядка
    пресета, и больший модификатор мог молча проиграть меньшему.

    Оговорка про направление: «больший» значит «выгодный игроку». Для
    кулдаунов и интервалов («раз в N ходов») выгоднее МЕНЬШЕЕ число, поэтому
    там берётся минимум — иначе правило выдавало бы игроку худший вариант."""
    merged: dict[str, float] = {}
    for buff_id in buff_ids:
        buff = catalog.get(buff_id)
        if buff is None:
            continue
        for key, value in buff.stat_modifiers.items():
            current = merged.get(key)
            if current is None:
                merged[key] = value
            elif is_lower_better(key):
                merged[key] = min(current, value)
            else:
                merged[key] = max(current, value)
    return merged


async def resolve_active_modifiers(db: AsyncSession, character: Character, pvp: bool = False) -> dict[str, float]:
    """Пресет, еда и руны (2026-10-31). pvp - руны с поправкой PvP."""
    merged = await _preset_and_food(db, character)
    from services import rune_service

    runes = rune_service.combat_modifiers(character, pvp)
    merged.update(runes)
    # Здоровье руны - тем же ключом, что у еды: его читает session.
    hp = runes.get("rune:ash_skin", 0.0)
    if hp:
        merged["max_hp_bonus"] = merged.get("max_hp_bonus", 0.0) + hp
    return merged


async def _preset_and_food(db: AsyncSession, character: Character) -> dict[str, float]:
    """Шорткат: активный пресет персонажа → смерженные stat_modifiers
    (патч 14, ч.3). Пусто, если подкласс не выбран или пресет не активирован.
    2026-10-21: сюда же - боевая часть баффа от еды (урон, защита, здоровье),
    так она попадает во все бои, что строятся от пресета."""
    from services import cooking_service

    food = cooking_service.combat_modifiers(character)
    if subclass_service.buff_pool(character) is None:
        return dict(food)
    active = await get_active_preset(db, character.id)
    if active is None:
        return dict(food)
    from game.content_loader import load_content

    merged = resolve_buff_modifiers(active.buff_ids, load_content().buffs)
    for key, value in food.items():
        merged[key] = merged.get(key, 0.0) + value
    return merged


async def switch_active_preset(
    db: AsyncSession, character: Character, preset_id: int
) -> CharacterBuffPreset:
    """Переключение между сохранёнными пресетами — бесплатно (уровень 1).

    Патч 50: если премиум истёк, а пресетов сохранено больше, чем действующий
    (без бонуса) лимит слотов — "лишние" (по порядку создания, id) не
    удаляются, но переключиться на них нельзя, пока премиум не продлён.
    Уже АКТИВНЫЙ пресет продолжает действовать в бою независимо от этого —
    правило касается только смены активного, не отбирает уже включённый."""
    presets = await presets_of(db, character)
    target = next((p for p in presets if p.id == preset_id), None)
    if target is None:
        raise PresetValidationError("Пресет не найден")
    slot_index = presets.index(target)
    if slot_index >= effective_preset_slots(character):
        raise PresetValidationError(
            "Этот пресет вне доступных слотов - продли Метку Хранителя или купи слот"
        )
    for preset in presets:
        preset.is_active = preset.id == preset_id
    return target
