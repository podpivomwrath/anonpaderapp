"""События исследования со сценами (патч 110): показ, кнопки, таймеры.

Висящее событие - в памяти процесса, как у старых событий (_pending_events
в bot/handlers/world.py): рестарт бота его теряет, и это нормально - кнопки
просто перестают отвечать. След и эффекты, которые живут дольше одной
сцены, лежат в БД (services/scene_event_service.py).

Только одиночная игра: групповое исследование сюда не заходит вовсе (там
только бои), а для групп будут отдельные события.
"""

import asyncio
import itertools
import random
import time
from dataclasses import dataclass

from loguru import logger
from vkbottle import Keyboard, KeyboardButtonColor, Text
from vkbottle.bot import BotLabeler, Message
from vkbottle.dispatch.rules import ABCRule

from bot import dailies_texts, group_texts
from bot.handlers import stats_window
from bot.keyboards.world import waiting_keyboard
from bot.vk_media import photo_attachment
from game.world import scene_events as se
from game.world.scene_events import Riddle, Scene, SceneEvent, SceneResult
from models import CharacterStats
from services import guild_service
from services import item_service, preset_service, scene_event_service, wallet_service
from services import onboarding_service as onboarding_svc
from services.db import get_session_factory

labeler = BotLabeler()
_rng = random.Random()
_tokens = itertools.count(1)

#: VK обрезает подпись кнопки длиннее 40 символов - режем сами, аккуратно.
LABEL_LIMIT = 40
#: Сколько ждём ответа на загадку, прежде чем засчитать провал.
RIDDLE_SECONDS = 180
#: Урон при тяжёлом срыве в «ещё чуть-чуть», % макс. HP.
HEAVY_FAIL_DAMAGE = [15, 25]


@dataclass
class Pending:
    event_id: str
    scene_id: str
    token: int
    step: int = 0            # push: сделано рывков
    bank: float = 0.0        # push: накоплено
    riddle: Riddle | None = None
    currency: str | None = None  # dice: выбранная валюта (gold | gems)
    stake: int | None = None     # dice: введённая ставка
    deadline: float = 0.0    # timer / riddle: time.monotonic()
    busy: bool = False       # идёт обработка нажатия - второе нажатие не пускаем
    task: asyncio.Task | None = None


_pending: dict[int, Pending] = {}


def has_pending(peer_id: int) -> bool:
    return peer_id in _pending


def cancel(peer_id: int) -> None:
    p = _pending.pop(peer_id, None)
    if p is not None and p.task is not None:
        p.task.cancel()


def _api():
    from bot.handlers import world as world_handlers  # цикл импортов

    return world_handlers._bot_api


def _label(text: str) -> str:
    return text if len(text) <= LABEL_LIMIT else text[: LABEL_LIMIT - 1].rstrip() + "…"


async def _send(peer_id: int, text: str, keyboard: str | None = None, attachment: str | None = None) -> None:
    await _api().messages.send(
        peer_id=peer_id, message=text, random_id=0, keyboard=keyboard, attachment=attachment,
    )


async def _load(db, peer_id: int):
    character = await onboarding_svc.get_character(db, peer_id)
    if character is None or character.creation_state is not None:
        return None, None
    from sqlalchemy import select

    stats = await db.scalar(select(CharacterStats).where(CharacterStats.character_id == character.id))
    return character, stats


# --- Показ сцены ------------------------------------------------------------------


def _button(kb: Keyboard, label: str, payload: dict, color=KeyboardButtonColor.SECONDARY) -> None:
    kb.add(Text(_label(label), payload=payload), color=color)
    kb.row()


def _finish_keyboard(kb: Keyboard) -> str:
    # Keyboard.row() после последней кнопки оставляет пустой ряд - VK его не принимает.
    if kb.buttons and not kb.buttons[-1]:
        kb.buttons.pop()
    return kb.get_json()


async def _render(db, character, stats, p: Pending, peer_id: int) -> tuple[str, str]:
    event = se.event_by_id(p.event_id)
    scene = event.scenes[p.scene_id]
    kb = Keyboard(one_time=False)
    base = {"type": "scene", "t": p.token}
    text = scene.text

    if scene.type == "choice":
        totals = await scene_event_service.total_stats(db, character, stats)
        for i, choice in enumerate(scene.choices):
            if not se.meets(choice.requires, character.base_class, character.subclass):
                continue
            label = choice.label
            if choice.check is not None:
                chance = se.check_chance(choice.check.stat, totals, choice.check.difficulty)
                label += f" ({se.STAT_EMOJI[choice.check.stat]} {round(chance * 100)}%)"
            label += scene_event_service.cost_label(character, choice.cost)
            _button(kb, label, {**base, "c": i})

    elif scene.type == "push":
        if p.step:
            text = _rng.choice(scene.pull_texts) if scene.pull_texts else ""
            text += f"\n\nВытащено: {p.step}."
        risk = se.push_risk(scene, p.step + 1)
        _button(kb, f"{scene.pull_label} (риск {round(risk * 100)}%)", {**base, "a": "pull"},
                KeyboardButtonColor.NEGATIVE)
        _button(kb, scene.stop_label, {**base, "a": "stop"}, KeyboardButtonColor.POSITIVE)

    elif scene.type == "timer":
        p.deadline = time.monotonic() + scene.seconds
        _button(kb, scene.button, {**base, "a": "timer"}, KeyboardButtonColor.NEGATIVE)
        text += f"\n\n⏱ {scene.seconds} сек."
        p.task = asyncio.create_task(_expire(peer_id, p.token, p.scene_id, scene.seconds + 0.5, "timeout"))

    elif scene.type == "riddle":
        p.riddle = _rng.choice(scene.riddles)
        p.deadline = time.monotonic() + RIDDLE_SECONDS
        text += f"\n\n«{p.riddle.q}»\n\nОтвет напиши сообщением."
        _button(kb, scene.giveup_label, {**base, "a": "giveup"})
        p.task = asyncio.create_task(_expire(peer_id, p.token, p.scene_id, RIDDLE_SECONDS, "giveup"))

    elif scene.type == "dice":
        # Одна партия в три шага, на каждом - «Отменить»: валюта -> сумма
        # сообщением -> «Бросить кости». Деньги списываются только при броске.
        if p.currency is None:
            for currency in scene.currencies:
                _button(kb, CURRENCY_BUTTONS[currency], {**base, "a": "currency", "v": currency})
        elif p.stake is None:
            wallet = await wallet_service.get_wallet(db, character.id)
            have = wallet.donate_currency if p.currency == "gems" else wallet.farm_currency
            text = f"Сколько ставишь? Напиши сумму сообщением.\n\n{_money(p.currency, have)} у тебя."
            p.deadline = time.monotonic() + RIDDLE_SECONDS
            p.task = asyncio.create_task(_expire(peer_id, p.token, p.scene_id, RIDDLE_SECONDS, "cancel"))
        else:
            text = f"Ставка: {_money(p.currency, p.stake)}."
            _button(kb, "🎲 Бросить кости", {**base, "a": "roll"}, KeyboardButtonColor.POSITIVE)
        _button(kb, "Отменить", {**base, "a": "cancel"})

    return text, _finish_keyboard(kb)


CURRENCY_BUTTONS = {"gold": "💰 Золото", "gems": "💎 Самоцветы"}


def _money(currency: str, amount: int) -> str:
    return f"{amount} 💎" if currency == "gems" else f"{amount} золота"


async def start(peer_id: int, event: SceneEvent) -> None:
    """Начать событие: первая сцена с заголовком."""
    cancel(peer_id)
    p = Pending(event_id=event.id, scene_id=event.start, token=next(_tokens))
    _pending[peer_id] = p
    async with get_session_factory()() as db:
        character, stats = await _load(db, peer_id)
        if character is None:
            _pending.pop(peer_id, None)
            return
        text, keyboard = await _render(db, character, stats, p, peer_id)
    attachment = photo_attachment(event.image) if event.image else None
    await _send(peer_id, f"{event.title}\n\n{text}", keyboard, attachment)


# --- Нажатия ----------------------------------------------------------------------


def _claim(peer_id: int, token) -> Pending | None:
    """Висящее событие под этот токен - и сразу занять его, чтобы второе
    нажатие (двойной клик, старая кнопка) ничего не сделало."""
    p = _pending.get(peer_id)
    if p is None or token != p.token or p.busy:
        return None
    p.busy = True
    if p.task is not None:
        p.task.cancel()
        p.task = None
    return p


@labeler.message(payload_contains={"type": "scene"})
async def on_button(message: Message) -> None:
    peer_id = message.peer_id
    payload = message.get_payload_json() or {}
    p = _claim(peer_id, payload.get("t"))
    if p is None:
        return
    try:
        await _dispatch(peer_id, p, payload)
    except Exception:
        logger.exception("Событие {} упало на нажатии {}", p.event_id, payload)
        cancel(peer_id)
        await _send(peer_id, "Что-то пошло не так - событие прервалось.", waiting_keyboard())
        await _epilogue(peer_id, [], None)
    finally:
        p.busy = False


async def _dispatch(peer_id: int, p: Pending, payload: dict) -> None:
    event = se.event_by_id(p.event_id)
    scene = event.scenes[p.scene_id]
    action = payload.get("a", "choice")
    async with get_session_factory()() as db:
        character, stats = await _load(db, peer_id)
        if character is None:
            cancel(peer_id)
            return

        if scene.type == "choice" and action == "choice":
            idx = payload.get("c")
            if not isinstance(idx, int) or not 0 <= idx < len(scene.choices):
                return
            choice = scene.choices[idx]
            if not se.meets(choice.requires, character.base_class, character.subclass):
                return
            if not await scene_event_service.can_afford(db, character, choice.cost) or \
                    not await scene_event_service.pay(db, character, choice.cost):
                await db.rollback()
                text, keyboard = await _render(db, character, stats, p, peer_id)
                await _send(peer_id, "Нечем заплатить.\n\n" + text, keyboard)
                return
            result, pre = _choice_result(choice, await scene_event_service.total_stats(db, character, stats))
            await _resolve(peer_id, db, character, stats, p, result, pre)
            return

        if scene.type == "push":
            await _push(peer_id, db, character, stats, p, scene, action)
            return

        if scene.type == "timer" and action == "timer":
            ok = time.monotonic() <= p.deadline
            await _resolve(peer_id, db, character, stats, p, scene.success if ok else scene.timeout, [])
            return

        if scene.type == "riddle" and action == "giveup":
            await _resolve(peer_id, db, character, stats, p, scene.failure, [])
            return

        if scene.type == "dice":
            await _dice(peer_id, db, character, stats, p, scene, action, payload)
            return


def _choice_result(choice, totals: dict[str, int]) -> tuple[SceneResult, list[str]]:
    if choice.check is not None:
        chance = se.check_chance(choice.check.stat, totals, choice.check.difficulty)
        ok = _rng.random() < chance
        emoji = se.STAT_EMOJI[choice.check.stat]
        verdict = "удалось" if ok else "не вышло"
        return (choice.success if ok else choice.failure), [f"{emoji} {round(chance * 100)}% - {verdict}."]
    if choice.success is not None and choice.failure is not None:
        ok = _rng.random() < se.CLASS_OPTION_CHANCE
        return (choice.success if ok else choice.failure), []
    if choice.outcomes:
        return se.pick_result(_rng, choice.outcomes), []
    return choice.result or SceneResult(), []


async def _resolve(peer_id, db, character, stats, p: Pending, result: SceneResult | None,
                   pre: list[str], applied=None) -> None:
    result = result or SceneResult()
    applied = await scene_event_service.apply_result(db, character, stats, result, _rng, applied)
    lines = pre + applied.lines

    if result.combat:
        await scene_event_service.finish_event(db, character, applied)
        gear_bonus = await item_service.compute_gear_bonus(db, character.id)
        modifiers = await scene_event_service.solo_modifiers(
            db, character, await preset_service.resolve_active_modifiers(db, character),
        )
        await db.commit()
        _pending.pop(peer_id, None)
        await _send(peer_id, "\n\n".join(lines) or "Бой!", waiting_keyboard())
        await _notify(peer_id, applied)
        from bot.handlers import combat as combat_handlers

        await combat_handlers.start_event_encounter(
            peer_id, character, stats, gear_bonus, modifiers,
            elite=result.combat == "elite", bonus=result.bonus,
        )
        return

    if result.next:
        p.scene_id = result.next
        p.step, p.bank, p.riddle, p.currency, p.stake = 0, 0.0, None, None, None
        text, keyboard = await _render(db, character, stats, p, peer_id)
        await db.commit()
        await _send(peer_id, "\n\n".join([*lines, text]), keyboard)
        await _notify(peer_id, applied)
        return

    await scene_event_service.finish_event(db, character, applied)
    await db.commit()
    _pending.pop(peer_id, None)
    await _epilogue(peer_id, lines, applied)


async def _push(peer_id, db, character, stats, p: Pending, scene: Scene, action: str) -> None:
    if action == "stop":
        applied = scene_event_service.Applied(new_level=character.level)
        await _cash_out(db, character, scene, p.bank, applied)
        await _resolve(peer_id, db, character, stats, p, SceneResult(text=scene.stop_text), [], applied)
        return
    if action != "pull":
        return
    p.step += 1
    if _rng.random() < se.push_risk(scene, p.step):
        penalty = se.push_penalty(p.step)
        applied = scene_event_service.Applied(new_level=character.level)
        if penalty == "light":
            # Теряешь только то, что тащил сейчас; прежнее - при тебе.
            await _cash_out(db, character, scene, p.bank, applied)
            result = SceneResult(text=scene.fail_light)
        elif penalty == "heavy":
            result = SceneResult(text=scene.fail_heavy, damage=HEAVY_FAIL_DAMAGE)
        else:
            result = SceneResult(text=scene.fail_ruin, ruin=True)
        await _resolve(peer_id, db, character, stats, p, result, [], applied)
        return
    p.bank += scene.step_reward
    text, keyboard = await _render(db, character, stats, p, peer_id)
    await _send(peer_id, text, keyboard)


async def _cash_out(db, character, scene: Scene, bank: float, applied) -> None:
    if bank <= 0:
        return
    if scene.loot == "gold":
        await scene_event_service.grant_gold(db, character, bank, applied)
    elif scene.loot == "ore":
        await scene_event_service.grant_ore(db, character, max(1, round(bank)), _rng, applied)
    else:
        await scene_event_service.grant_trophies(db, character, bank, _rng, applied)


async def _dice(peer_id, db, character, stats, p: Pending, scene: Scene, action: str, payload: dict) -> None:
    """Одна партия: валюта -> сумма (сообщением, см. stake_answer) -> бросок."""
    if action == "cancel":
        await _resolve(peer_id, db, character, stats, p, SceneResult(text=scene.leave_text), [])
        return
    if action == "currency" and p.currency is None and payload.get("v") in scene.currencies:
        p.currency = payload["v"]
        text, keyboard = await _render(db, character, stats, p, peer_id)
        await _send(peer_id, text, keyboard)
        return
    if action != "roll" or p.currency is None or p.stake is None:
        return
    wallet_column = "donate" if p.currency == "gems" else "farm"
    try:
        await wallet_service.charge(db, character.id, wallet_column, p.stake)
    except wallet_service.NotEnoughCurrency:
        p.stake = None
        text, keyboard = await _render(db, character, stats, p, peer_id)
        await _send(peer_id, "Столько у тебя уже нет.\n\n" + text, keyboard)
        return
    won, mine, theirs = se.roll_dice(_rng, scene.win_chance)
    if won:
        await wallet_service.deposit(db, character.id, wallet_column, p.stake * 2)
    line = (
        f"🎲 Ты: {mine[0]} и {mine[1]}, он: {theirs[0]} и {theirs[1]}.\n"
        + (f"{scene.win_text} +{_money(p.currency, p.stake)}"
           + (f" (после налога гильдии на руки {guild_service.after_tax(character, p.stake * 2)} из {p.stake * 2})"
              if won and p.currency == "gold" and guild_service.after_tax(character, p.stake * 2) != p.stake * 2 else "")
           if won
           else f"{scene.lose_text} −{_money(p.currency, p.stake)}")
    )
    await _resolve(peer_id, db, character, stats, p, SceneResult(), [line])


def parse_stake(text: str) -> int | None:
    """Сумма ставки из сообщения: «250», «1 000», «250 зол» - берём число."""
    digits = "".join(ch for ch in text if ch.isdigit())
    if not digits or len(digits) > 12:
        return None
    value = int(digits)
    return value if value > 0 else None


# --- Таймер и загадка -------------------------------------------------------------


async def _expire(peer_id: int, token: int, scene_id: str, seconds: float, action: str) -> None:
    """Время вышло: не успел нажать / не ответил на загадку."""
    try:
        await asyncio.sleep(seconds)
    except asyncio.CancelledError:
        return
    p = _pending.get(peer_id)
    if p is None or p.token != token or p.scene_id != scene_id or p.busy:
        return
    p.busy = True
    p.task = None
    try:
        scene = se.event_by_id(p.event_id).scenes[p.scene_id]
        if action == "timeout":
            result = scene.timeout
        elif action == "cancel":  # ставку так и не назвали
            result = SceneResult(text=scene.leave_text)
        else:
            result = scene.failure
        async with get_session_factory()() as db:
            character, stats = await _load(db, peer_id)
            if character is None:
                cancel(peer_id)
                return
            await _resolve(peer_id, db, character, stats, p, result, [])
    except Exception:
        logger.exception("Событие {}: сбой по таймеру", p.event_id)
        cancel(peer_id)
    finally:
        p.busy = False


class RiddleAnswer(ABCRule[Message]):
    """Свободный текст - это ответ, только пока загадка ждёт ответа."""

    async def check(self, event: Message) -> bool:
        p = _pending.get(event.peer_id)
        return bool(p and p.riddle is not None and event.text and not event.payload)


@labeler.message(RiddleAnswer())
async def riddle_answer(message: Message) -> None:
    peer_id = message.peer_id
    p = _pending.get(peer_id)
    if p is None or p.riddle is None:
        return
    p = _claim(peer_id, p.token)
    if p is None:
        return
    try:
        scene = se.event_by_id(p.event_id).scenes[p.scene_id]
        right = se.answer_matches(message.text, p.riddle.a)
        async with get_session_factory()() as db:
            character, stats = await _load(db, peer_id)
            if character is None:
                cancel(peer_id)
                return
            await _resolve(peer_id, db, character, stats, p, scene.success if right else scene.failure, [])
    except Exception:
        logger.exception("Событие {}: сбой на ответе загадки", p.event_id)
        cancel(peer_id)
    finally:
        p.busy = False


def _awaits_stake(p: Pending | None) -> bool:
    if p is None or p.currency is None or p.stake is not None:
        return False
    return se.event_by_id(p.event_id).scenes[p.scene_id].type == "dice"


class StakeAnswer(ABCRule[Message]):
    """Свободный текст - это сумма ставки, только пока кости её ждут."""

    async def check(self, event: Message) -> bool:
        return bool(_awaits_stake(_pending.get(event.peer_id)) and event.text and not event.payload)


@labeler.message(StakeAnswer())
async def stake_answer(message: Message) -> None:
    peer_id = message.peer_id
    p = _pending.get(peer_id)
    if not _awaits_stake(p):
        return
    p = _claim(peer_id, p.token)
    if p is None:
        return
    try:
        async with get_session_factory()() as db:
            character, stats = await _load(db, peer_id)
            if character is None:
                cancel(peer_id)
                return
            wallet = await wallet_service.get_wallet(db, character.id)
            have = wallet.donate_currency if p.currency == "gems" else wallet.farm_currency
            amount = parse_stake(message.text)
            if amount is None:
                note = "Нужна сумма числом, например 250."
            elif amount > have:
                note = f"У тебя только {_money(p.currency, have)}."
            else:
                p.stake, note = amount, None
            text, keyboard = await _render(db, character, stats, p, peer_id)
        await _send(peer_id, f"{note}\n\n{text}" if note else text, keyboard)
    except Exception:
        logger.exception("Событие {}: сбой на ставке", p.event_id)
        cancel(peer_id)
    finally:
        p.busy = False


# --- Итог -------------------------------------------------------------------------


async def _notify(peer_id: int, applied) -> None:
    if applied is None:
        return
    await stats_window.notify_levelup(peer_id, applied.levels_gained, applied.new_level)
    await group_texts.notify_group_kick(_api(), applied.group_kick)
    notice = dailies_texts.progress_notice_from(applied.daily_completed, None)
    if notice:
        await _send(peer_id, notice)
    for c in applied.daily_completed:
        await stats_window.notify_levelup(peer_id, c.levels_gained, c.new_level)


async def _epilogue(peer_id: int, lines: list[str], applied) -> None:
    """Итог события и сводка локации - как у старых событий."""
    from bot.handlers import world as world_handlers

    if lines:
        await _send(peer_id, "\n\n".join(lines), waiting_keyboard())
    await _notify(peer_id, applied)
    async with get_session_factory()() as db:
        character, _stats = await _load(db, peer_id)
        if character is None:
            return
        text, attachment, keyboard = await world_handlers.location_summary_parts(db, character, peer_id)
        await db.commit()
    await _api().messages.send(
        peer_id=peer_id, message=text, random_id=0, attachment=attachment, keyboard=keyboard,
    )
