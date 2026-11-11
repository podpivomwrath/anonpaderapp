"""Сигнал союзникам в групповом бою (2026-11-11, предложение игрока, решение
владельца).

Игрок выбрал действие - вместо пустого «Ожидание остальных» у него кнопка
«📢 Показать союзникам». Нажал - каждому союзнику по бою приходит отдельное
сообщение «📢 Ник готовит «Оберег»». Так в группе с незнакомыми видно, кто
лечит, кто ставит щит или оглушает, без голосового чата.

Бои: групповой с тварями (с ним же разломы и руины), массовое PvP и дуэль,
рейды. Две настройки в мини-аппе (Герой -> Настройки), обе включены по
умолчанию: «signals_out_off» - не предлагать кнопку, «signals_in_off» - не
присылать сигналы союзников. Копия настроек - в памяти по vk_id, как у
bot/short_log.py.

Сигнал готовится при объявлении действия (здесь известны навык, цель и
союзники) и живёт до нажатия; устаревший (ход уже прошёл) не отправляется.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import select
from vkbottle import KeyboardButtonColor

BTN = "📢 Показать союзникам"
PAYLOAD_TYPE = "battle_signal"
OUT_FLAG, IN_FLAG = "signals_out_off", "signals_in_off"

#: Бьют выбранного врага, хотя урон у них не от характеристик.
ENEMY_TARGET_SKILLS = frozenset({"poisoner_toxic_burst", "reckoning"})

_no_out: set[int] = set()
_no_in: set[int] = set()


@dataclass
class Signal:
    text: str
    allies: list[int]               # peer_id союзников-игроков
    keyboard: str | None            # клавиатура ожидания без кнопки
    is_current: Callable[[], bool]  # ход, в котором объявлено, ещё идёт


_pending: dict[int, Signal] = {}


async def load(session_factory) -> int:
    """Прочитать при старте, кто выключил сигналы."""
    from models import Character, User

    async with session_factory() as db:
        rows = (await db.execute(
            select(User.vk_id, Character.ui_flags).join(Character, Character.user_id == User.id)
        )).all()
    _no_out.clear()
    _no_in.clear()
    for vk_id, flags in rows:
        if isinstance(flags, dict):
            if flags.get(OUT_FLAG):
                _no_out.add(int(vk_id))
            if flags.get(IN_FLAG):
                _no_in.add(int(vk_id))
    return len(_no_out | _no_in)


def set_flags(vk_id: int, flags: dict) -> None:
    for store, key in ((_no_out, OUT_FLAG), (_no_in, IN_FLAG)):
        if flags.get(key):
            store.add(int(vk_id))
        else:
            store.discard(int(vk_id))
    if flags.get(OUT_FLAG):
        _pending.pop(int(vk_id), None)


def action_text(name: str, action, combatants: dict) -> str | None:
    """«📢 Ник готовит «Оберег»», «📢 Ник готовит «Казнь» → Хор бойниц»."""
    from game.combat import skill_catalog
    from game.combat.session import ActionType
    from game.economy import ability_config as ac

    target = combatants.get(action.target_id) if action.target_id is not None else None
    aim = f" → {target.name}" if target is not None else ""
    if action.type == ActionType.SKILL:
        skill = skill_catalog.skill_def(action.skill_id)
        title = skill.name if skill else action.skill_id
        # Цель - только у навыков с ударом по врагу: лечение и щиты сами
        # выбирают, кого прикрыть, и выбранный враг тут ни при чём.
        hits = action.skill_id in ac.SCALING_SHARES or action.skill_id in ENEMY_TARGET_SKILLS
        return f"📢 {name} готовит «{title}»" + (aim if hits else "")
    if action.type == ActionType.ATTACK:
        return f"📢 {name} бьёт обычной атакой{aim}"
    if action.type == ActionType.DEFEND:
        return f"📢 {name} защищается"
    if action.type == ActionType.ITEM:
        return f"📢 {name} пьёт зелье"
    return None


def prepare(peer_id: int, name: str, action, combatants: dict, allies: list[int],
            keyboard: str | None, is_current: Callable[[], bool]) -> str | None:
    """Запомнить сигнал и вернуть клавиатуру ожидания с кнопкой. Без кнопки
    (вернётся та же клавиатура) - если игрок выключил сигналы, союзников
    нет или действие - пропуск хода."""
    _pending.pop(int(peer_id), None)
    text = action_text(name, action, combatants)
    allies = [a for a in allies if a != peer_id]
    if int(peer_id) in _no_out or not allies or not text:
        return keyboard
    _pending[int(peer_id)] = Signal(text, allies, keyboard, is_current)
    return with_button(keyboard)


def waiting_keyboard(engine, battle_id: int, battle, cid: int, action, keyboard: str | None) -> str | None:
    """Клавиатура «Ожидание остальных» для бойца cid - с кнопкой сигнала,
    если есть кому его показать. Общая для группового боя, PvP и рейда:
    союзники - живые игроки той же стороны из battle.participants."""
    state = engine.sessions.get(battle_id) if engine is not None else None
    participant = battle.participants.get(cid)
    if state is None or participant is None:
        return keyboard
    combatants = state.combatants
    me = combatants.get(cid)
    if me is None:
        return keyboard
    allies = [
        p.peer_id for other, p in battle.participants.items()
        if other != cid and (c := combatants.get(other)) is not None and c.alive and c.side == me.side
    ]
    tick = state.tick_number

    def is_current() -> bool:
        return engine.sessions.get(battle_id) is state and state.tick_number == tick

    return prepare(participant.peer_id, me.name, action, combatants, allies, keyboard, is_current)


def with_button(keyboard: str | None) -> str:
    data = json.loads(keyboard) if keyboard else {"one_time": False, "buttons": []}
    rows = data.get("buttons") or []
    button = {
        "action": {"type": "text", "label": BTN, "payload": json.dumps({"type": PAYLOAD_TYPE})},
        "color": KeyboardButtonColor.PRIMARY.value,
    }
    data["buttons"] = [[button], *rows]
    data.setdefault("one_time", False)
    return json.dumps(data, ensure_ascii=False)


async def send(api, peer_id: int) -> tuple[str, str | None]:
    """Нажатие кнопки: разослать сигнал. Ответ нажавшему и клавиатура ожидания
    без кнопки (None - клавиатуру не трогать)."""
    signal = _pending.pop(int(peer_id), None)
    if signal is None or not signal.is_current():
        return "Этот ход уже прошёл - показывать нечего.", None
    sent = 0
    for ally in signal.allies:
        if ally in _no_in:
            continue
        try:
            await api.messages.send(peer_id=ally, message=signal.text, random_id=0)
            sent += 1
        except Exception as exc:  # noqa: BLE001 - союзник мог запретить сообщения, остальным всё равно шлём
            from loguru import logger

            logger.info("Сигнал боя не дошёл до {}: {}", ally, exc)
    if not sent:
        return "Союзники выключили сигналы - никто не увидит.", signal.keyboard
    return "📢 Союзники видят ваше действие.", signal.keyboard

