"""Рейды и разломы: разбор хода (механики боссов, лимит ходов), награды за
этапы (отложенные до победы), переход между этапами, победа, гибель группы и
возврат игроков на карту.

Вынесено из bot/handlers/raid_combat.py без изменений логики (2026-10-22,
нарезка). Состояние боёв (_battles, _engine, _bot_api) живёт в raid_combat.py -
здесь raid_combat.X, чтобы копия была одна и тесты подменяли там же.
"""

import asyncio
from dataclasses import dataclass
from loguru import logger
from bot import background
from bot import dailies_texts, group_texts, raid_key_texts, raid_texts as rt
from bot import trial_tracking
from bot.handlers import respawn as respawn_handlers
from bot.handlers import stats_window
from bot.keyboards import raid as kb
from bot.keyboards.world import movement_keyboard
from game.combat import balance_config as bc
from game.combat import display, raid_archive, raid_bosses, raid_field, raid_mill
from game.combat import raid_trail as trail_combat
from game.combat.resolver import TickResult
from game.combat.session import ActionType, CombatSessionState, DeclaredAction
from game.economy import raid_config as rc
from game.economy import raid_field_config as fc
from game.economy import rift_config as rfc
from models import Character
from services import daily_service, encounter_service, item_service, mount_service, pvp_shield, quest_service, raid_combat_service, subclass_service, trial_service, trophy_service
from bot.handlers import raid_combat


# --- Резолв тика: механики боссов + награды ---


async def _kill_random_survivor(battle_id: int, battle: raid_combat.RaidBattle) -> int | None:
    """Гарантированная гибель одного случайного ЖИВОГО участника (провал
    окна прерывания/фазы проверки урона Хирурга) — HP обнуляется НАПРЯМУЮ,
    в обход обычного резолва тика (см. game/combat/raid_bosses.py — этот
    приём уже описан там для сценария лайфстила, тот же принцип). Возвращает
    id погибшего (для лога/дальнейшей проверки вайпа) или None, если живых
    уже не осталось (не должно происходить, но не падать)."""
    state = raid_combat._engine.sessions.get(battle_id)
    if state is None:
        return None
    alive_players = [c for c in state.combatants.values() if c.kind == "character" and c.alive]
    if not alive_players:
        return None
    victim = battle.rng.choice(alive_players)
    victim.current_hp = 0
    return victim.id


async def on_raid_tick_resolved(session_id: int, tick: int, result: TickResult) -> None:
    battle = raid_combat._battles.get(session_id)
    if battle is None:
        return
    raid_combat._declared_this_tick.pop(session_id, None)
    battle.frozen_now = set()
    _record_contribution(battle, result)
    battle.stage_ticks += 1
    state = raid_combat._engine.sessions.get(session_id)
    # Классовые испытания и в рейде/разломе (2026-10-24, bot/trial_tracking.py).
    trial_tracking.observe(session_id, state.combatants if state is not None else None, result,
                           list(battle.participants))
    extra_lines: list[str] = []
    scripted_death_ids: list[int] = []
    field_cleared = False
    frozen_ids: list[int] = []

    if not battle.is_theatre and state is not None and battle.field_stage is not None:
        outcome = _field_after_tick(battle, state, result)
        extra_lines.extend(outcome.lines)
        scripted_death_ids.extend(outcome.deaths)
        field_cleared = outcome.cleared and not result.finished
        frozen_ids = [cid for cid in outcome.frozen if cid in battle.participants]

    if battle.is_theatre and battle.stage == 2 and state is not None:
        dead_veld_ids = [vid for vid, cid in battle.veld_combatant_ids.items() if cid in result.deaths]
        if dead_veld_ids:
            dead_veld_ids.sort(key=lambda vid: rc.VELD_ORDER.index(vid))
            outcome = raid_bosses.check_veld_kill_order(
                state.combatants, battle.veld_combatant_ids, dead_veld_ids,
                battle.veld_killed_order, battle.veld_violations,
            )
            battle.veld_violations = outcome.violations
            extra_lines.extend(outcome.lines)

    if battle.is_theatre and battle.stage == 3 and state is not None and battle.surgeon_id is not None:
        surgeon = state.combatants.get(battle.surgeon_id)
        ai = battle.surgeon_ai
        if surgeon is not None and ai is not None and surgeon.alive:
            # Окно прерывания (первый ход ИЛИ только что открыто фазой 2).
            # Смотрим на ПОПЫТКУ контроля по самому Хирургу, а не на успешно
            # наложенный эффект: Хирург не поддаётся контролю в принципе (патч 66),
            # так что ждать FREEZE значило бы сделать окно непроходимым. Цель
            # проверяется отдельно - контроль по другому противнику навык не
            # сбивает.
            if ai.awaiting_interrupt:
                if result.control_attempts_on.get(battle.surgeon_id):
                    extra_lines.append(rt.SURGEON_INTERRUPTED_LINE)
                    ai.close_interrupt_window()
                else:
                    victim_id = await _kill_random_survivor(session_id, battle)
                    if victim_id is not None:
                        victim_name = battle.participants.get(victim_id)
                        extra_lines.append(
                            f"{rt.SURGEON_INTERRUPT_FAIL_DEATH_LINE}"
                            + (f" {victim_name.name} больше не встаёт." if victim_name else "")
                        )
                        scripted_death_ids.append(victim_id)
                    ai.close_interrupt_window()
            elif tick == 1:
                extra_lines.append(rt.SURGEON_PREPARE_FIRST_TEXT)
                ai.open_interrupt_window()
            elif ai.phase == 1 and surgeon.current_hp <= surgeon.max_hp * rc.SURGEON_PHASE2_HP_THRESHOLD:
                ai.phase = 2
                extra_lines.append(rt.SURGEON_PREPARE_PHASE2_TEXT)
                ai.open_interrupt_window()
            elif (
                ai.phase == 2
                and ai.phase3_turns_left is None
                and not battle.surgeon_phase3_failed
                and surgeon.current_hp <= surgeon.max_hp * rc.SURGEON_PHASE3_HP_THRESHOLD
            ):
                ai.enter_phase3()
                battle.surgeon_phase3_hp_at_start = surgeon.current_hp
                extra_lines.append(rt.SURGEON_PHASE3_TEXT)
            elif ai.phase3_turns_left is not None:
                ai.phase3_turns_left -= 1
                if ai.phase3_turns_left <= 0:
                    dealt = (battle.surgeon_phase3_hp_at_start or surgeon.current_hp) - surgeon.current_hp
                    ai.phase3_turns_left = None
                    if dealt >= rc.SURGEON_PHASE3_DAMAGE_REQUIRED:
                        extra_lines.append(rt.SURGEON_PHASE3_SURVIVED_LINE)
                    else:
                        battle.surgeon_phase3_failed = True
                        extra_lines.append(rt.SURGEON_PHASE3_FAIL_TEXT)
            elif battle.surgeon_phase3_failed:
                victim_id = await _kill_random_survivor(session_id, battle)
                if victim_id is not None:
                    scripted_death_ids.append(victim_id)

    if scripted_death_ids and state is not None:
        alive_players_left = [c for c in state.combatants.values() if c.kind == "character" and c.alive]
        if not alive_players_left:
            # Последний ход - всем, до конца захода: иначе погибший от
            # взрыва или фазы босса не видел, от чего умер (2026-10-13).
            await raid_combat._broadcast_board(session_id, battle, result, boss_lines=extra_lines)
            # Вайп сценарной гибелью — TickEngine об этом не узнает сам
            # (HP обнулён В ОБХОД resolve_tick), поэтому завершаем ЯВНО:
            # abort_session — единственный ПУБЛИЧНЫЙ метод движка для этого
            # (снимает job таймера, освобождает session_id), дальше —
            # собственная логика вайпа этого модуля.
            raid_combat._engine.abort_session(session_id)
            await raid_combat._finish_wipe(session_id, battle)
            return

    # Награда - одна за ВЗЯТЫЙ ЭТАП, а не за каждого павшего противника:
    # раньше каждая кукла, Вельд и знаменосец отдельно сыпали трофеями и
    # опытом. Этап взят, когда сторона противника пала (театр, туман,
    # генерал) или когда поле закрыло этап само (призыватель взял алебарду).
    stage_won = field_cleared or (result.finished and result.winner_side == 0)
    notices: dict[int, str] = {}
    if stage_won:
        alive_char_ids = [
            cid for cid, c in raid_combat._live_state(session_id, battle).items()
            if c.side == 0 and c.alive and cid in battle.participants
        ]
        notices = await _stage_rewards(battle, alive_char_ids)

    if frozen_ids and not field_cleared:
        raid_combat._declared_this_tick.setdefault(session_id, set()).update(frozen_ids)
        battle.frozen_now = set(frozen_ids)
        for cid in frozen_ids:
            held = (
                "📖 Каталог сковал тебя: в следующем ходу ты пропускаешь." if battle.is_archive
                else "⛓ Тебя держат: в следующем ходу ты пропускаешь." if battle.is_rift
                else "🦴 Руки держат крепко: в следующем ходу ты пропускаешь."
            )
            notices[cid] = f"{notices[cid]}\n{held}" if notices.get(cid) else held
    await raid_combat._broadcast_board(session_id, battle, result, notices, boss_lines=extra_lines)

    if field_cleared:
        # Этап поля закончен не смертью всех противников - движок об этом не
        # знает, закрываем сессию сами (тот же приём, что у сценарного вайпа).
        battle.tick_offset = tick
        raid_combat._engine.abort_session(session_id)
        await _advance_or_finish(session_id, battle)
        return
    if result.finished:
        battle.tick_offset = tick
    elif battle.stage_ticks >= rc.RAID_STAGE_TURN_LIMIT:
        # Предел этапа: босс больше не ждёт и бьёт ультимативно - вся группа
        # гибнет. Не навык из списка, а сценарный конец: раньше одиночка мог
        # тянуть этап сотнями ходов на зельях (решение владельца 2026-10-02).
        raid_combat._engine.abort_session(session_id)
        ultimate = (
            rfc.RIFT_TYPES[battle.rift_kind].ultimate_text if battle.is_rift
            else rc.RAID_ULTIMATE_TEXT[battle.raid_id]
        )
        await raid_combat._finish_wipe(session_id, battle, ultimate)
        return
    if frozen_ids:
        # Последней строкой: следующий ход движок откроет только после
        # возврата из этого колбэка, а пропуск надо объявить уже в нём.
        background.spawn(_auto_skip(session_id, frozen_ids))


@dataclass
class StageReward:
    """Награда взятого этапа, снятая в момент победы на этапе: кто был жив
    и сколько этап стоил. Выдаётся в конце захода (_grant_pending_rewards)."""
    stage: int
    alive_ids: list[int]
    xp_mobs: float
    loot_mult: int


PENDING_REWARD_LINE = "🎁 Награда за этап засчитана - её выдадут, если пройдёте до конца."


async def _stage_rewards(battle: raid_combat.RaidBattle, alive_char_ids: list[int]) -> dict[int, str]:
    """Этап взят: награда запоминается живым и ждёт конца захода."""
    battle.pending_rewards.append(
        StageReward(battle.stage, list(alive_char_ids), raid_combat._xp_mobs(battle), raid_combat._loot_mult(battle))
    )
    return {cid: PENDING_REWARD_LINE for cid in alive_char_ids}


async def _grant_pending_rewards(battle: raid_combat.RaidBattle) -> None:
    """Победа: все отложенные награды этапов - одним сообщением каждому."""
    by_cid: dict[int, list[str]] = {}
    for reward in battle.pending_rewards:
        notices = await raid_combat._grant_stage_reward(battle, reward)
        for cid, text in notices.items():
            if text:
                by_cid.setdefault(cid, []).append(text)
    battle.pending_rewards = []
    for cid, parts in by_cid.items():
        p = battle.participants.get(cid)
        if p is None:
            continue
        try:
            await raid_combat._bot_api.messages.send(
                peer_id=p.peer_id, random_id=0, message="🎁 Награда за пройденные этапы:\n" + "\n".join(parts),
            )
        except Exception:
            logger.exception("Рейд: не удалось отправить награду {}", p.peer_id)


async def _grant_stage_reward(battle: raid_combat.RaidBattle, reward: StageReward) -> dict[int, str]:
    """Награда за взятый этап живым участникам: опыт, трофеи, дроп, ключ;
    на третьем этапе - испытание «выше уровнем». {id: строки уведомления}."""
    alive_char_ids = reward.alive_ids
    notices: dict[int, str] = {}
    async with raid_combat.get_session_factory()() as db:
        characters = []
        for cid in alive_char_ids:
            character = await db.get(Character, cid)
            if character is not None:
                characters.append(character)
        mob_level = battle.rift_level if battle.is_rift else raid_bosses.BOSS_LEVEL
        rewards = await raid_combat_service.reward_mob_kill(
            db, characters, mob_level, battle.rng, reward.loot_mult, reward.xp_mobs,
        )
        for r in rewards:
            p = battle.participants.get(r.character_id)
            if p is None:
                continue
            xp_line = display.xp_delta_line(r.xp_gained, premium=r.xp_premium_applied)
            lines = [xp_line] if xp_line else []  # на 60 уровне опыта нет
            drop_line = trophy_service.format_drop_line(r.trophies)
            if drop_line:
                lines.append(drop_line)
            for item in r.items_dropped:
                lines.append(item_service.format_drop_announcement(item))
            lines.extend(r.elixir_lines)
            if battle.is_rift:
                gold_owner = next((c for c in characters if c.id == r.character_id), None)
                if gold_owner is not None:
                    lines.append(await _rift_gold(db, battle, gold_owner, reward.stage))
                if reward.stage >= battle.final_stage:
                    # Шахтёрская лампа (2026-10-23) - находка за пройденный разлом.
                    from services import craft_gear_service

                    lamp = await craft_gear_service.roll_lamp(db, r.character_id, battle.rng)
                    if lamp:
                        lines.append(lamp)
            if r.raid_key_dropped:
                lines.append(raid_key_texts.raid_key_drop_line())
            if r.group_kick is not None and r.group_kick.kicked_character_id == r.character_id:
                lines.append(group_texts.level_gap_kick_self_line())
            character = next((c for c in characters if c.id == r.character_id), None)
            if character is not None and r.trophies:
                daily_progress = await daily_service.record_trophies(db, character, r.trophies)
                daily_notice = dailies_texts.progress_notice(daily_progress)
                if daily_notice:
                    lines.append(daily_notice)
                for c in daily_progress.completed:
                    await stats_window.notify_levelup(p.peer_id, c.levels_gained, c.new_level)
            notices[r.character_id] = "\n".join(lines)
            if r.levels_gained > 0:
                await stats_window.notify_levelup(p.peer_id, r.levels_gained, r.new_level)
        for character in characters:
            await quest_service.record_kill(db, character)
        if reward.stage == 3 and not battle.is_rift:
            # Хирург и Генерал - «выше уровнем» для испытаний (см.
            # SURGEON_TRIAL_LEVEL). Засчитывается всем, кто в рейде:
            # победа общая, как и рейд.
            trial_level = raid_combat._trial_level(battle)
            for cid, p in list(battle.participants.items()):
                character = await db.get(Character, cid)
                if character is None or subclass_service.buff_pool(character) is None:
                    continue
                for buff_id in await trial_service.record_level_kill(db, character, trial_level):
                    opened = f"📖 Испытание пройдено. Открыт бафф: {trial_service.buff_name(buff_id)}."
                    notices[cid] = f"{notices[cid]}\n{opened}" if notices.get(cid) else opened
        await db.commit()
    return notices


async def _auto_skip(battle_id: int, character_ids: list[int]) -> None:
    """Пропуск хода за скованного: иначе группа ждала бы таймера хода."""
    for cid in character_ids:
        try:
            await raid_combat._engine.declare_action(battle_id, cid, DeclaredAction(type=ActionType.SKIP))
        except (KeyError, ValueError):
            continue


def _field_after_tick(battle: raid_combat.RaidBattle, state: CombatSessionState, result: TickResult):
    stage = battle.field_stage
    if getattr(stage, "rift", False):
        return stage.after_tick(state, result, battle.rng)
    if isinstance(stage, (raid_archive.ArchiveStage, raid_mill.CargoStage, raid_mill.MillerStage,
                          trail_combat.NamelessStage)):
        return stage.after_tick(state, result, battle.rng)
    if isinstance(stage, raid_field.FogStage):
        return stage.after_tick(state, result)
    if isinstance(stage, raid_field.SummonerStage):
        outcome = stage.after_tick(state, result, battle.rng)
        if outcome.cleared:
            battle.field_leftover = stage.leftover
        return outcome
    damage_by = {cid: c.damage for cid, c in battle.contribution.items()}
    return stage.after_tick(state, result, battle.rng, damage_by)


def _record_contribution(battle: raid_combat.RaidBattle, result: TickResult) -> None:
    """Складывает вклад этого хода в копилку рейда.

    Урон считаем по ПРИШЕДШЕМУ (hit_renders.amount уже после блока и щитов):
    сводка должна отвечать «сколько ты снял с боссов», а не «сколько бы снял».
    Тик яда/горения тоже засчитывается автору эффекта - он его повесил.
    """
    for hit in result.hit_renders:
        # «Впитано» - весь урон, пришедший в игрока: и дошедший, и срезанный
        # блоком и щитами. Раньше считалось только срезанное, и тот, кто
        # весь рейд принимал удары на себя без щита, стоял в таблице с нулём.
        taken = (0 if hit.missed else max(hit.amount, 0)) + (hit.absorbed or 0)
        if hit.target_id in battle.participants and taken:
            battle.contribution.setdefault(hit.target_id, raid_combat.RaidContribution()).absorbed += taken
        if hit.missed or hit.amount <= 0:
            continue
        if hit.source_id in battle.participants and hit.target_side != hit.source_side:
            battle.contribution.setdefault(hit.source_id, raid_combat.RaidContribution()).damage += hit.amount
    for heal in result.heal_renders:
        if heal.source_id in battle.participants and heal.amount > 0:
            battle.contribution.setdefault(heal.source_id, raid_combat.RaidContribution()).healed += heal.amount


async def on_raid_battle_finished(session_id: int, result: TickResult) -> None:
    battle = raid_combat._battles.get(session_id)
    if battle is None:
        return
    if result.winner_side != 0:
        await _settle_trials(session_id, battle, won=False)
        await raid_combat._finish_wipe(session_id, battle)
        return
    await _advance_or_finish(session_id, battle)


async def _settle_trials(session_id: int, battle: raid_combat.RaidBattle, won: bool) -> None:
    """Этап окончен - отчёты участников в классовые испытания (каждый этап -
    отдельный бой) и весть, если открылся бафф."""
    opened = await trial_tracking.settle(session_id, won)
    for cid, buffs in opened.items():
        p = battle.participants.get(cid)
        if p is None:
            continue
        try:
            await raid_combat._bot_api.messages.send(
                peer_id=p.peer_id, message=trial_tracking.opened_text(buffs), random_id=0,
            )
        except Exception:  # noqa: BLE001 - баффы уже открыты, весть вторична
            pass


async def _advance_or_finish(session_id: int, battle: raid_combat.RaidBattle) -> None:
    """Этап зачищен (сторона игроков победила). stage<3 — пауза 5-10 сек +
    переход к следующему этапу; stage==3 — рейд пройден целиком."""
    await _settle_trials(session_id, battle, won=True)
    stage_cleared = battle.stage
    if stage_cleared >= battle.final_stage:
        await _finish_victory(session_id, battle)
        return

    texts = raid_combat._texts(battle)
    if battle.is_rift:
        transition_text = texts.transition_text(stage_cleared)
    else:
        transition_text = texts.STAGE1_TO_STAGE2_TEXT if stage_cleared == 1 else texts.STAGE2_TO_STAGE3_TEXT
    for p in list(battle.participants.values()):
        await raid_combat._bot_api.messages.send(
            peer_id=p.peer_id, message=transition_text, random_id=0, keyboard=kb.raid_waiting_keyboard(),
        )
    # Поле - один длинный бой: пауза короче театрального антракта.
    pause = (
        (fc.STAGE_PAUSE_MIN_SECONDS, fc.STAGE_PAUSE_MAX_SECONDS) if battle.is_field or battle.is_rift
        else (rc.STAGE_TRANSITION_PAUSE_MIN_SECONDS, rc.STAGE_TRANSITION_PAUSE_MAX_SECONDS)
    )
    await asyncio.sleep(battle.rng.uniform(*pause))
    if raid_combat._battles.get(session_id) is not battle:
        return  # рейд прервали, пока шла пауза (перезапуск, abort_run)

    battle.stage += 1
    state = raid_combat._start_stage_session(session_id, battle)
    raid_combat._engine.start_session(state)
    for p in list(battle.participants.values()):
        await raid_combat._bot_api.messages.send(
            peer_id=p.peer_id, message=raid_combat._appear_text(battle),
            attachment=raid_combat._stage_attachment(battle), random_id=0,
        )
    await raid_combat._broadcast_board(session_id, battle, None, boss_lines=raid_combat._take_opening_lines(battle))


async def _grant_stage_clear_bonus(battle: raid_combat.RaidBattle) -> None:
    """Гарантированный предмет за этап — ОДНОМУ случайному живому участнику
    (текст патча). Плюс, на этапе 3, Скальпель Хирурга — ВСЕГДА, тоже
    одному случайному участнику (независимый розыгрыш)."""
    async with raid_combat.get_session_factory()() as db:
        candidates = []
        for cid in list(battle.participants):
            character = await db.get(Character, cid)
            if character is not None:
                candidates.append(character)
        if not candidates:
            return
        winner = battle.rng.choice(candidates)
        item = await raid_combat_service.grant_guaranteed_item(
            db, winner, raid_bosses.BOSS_LEVEL, battle.rng, raid_combat._STAGE_LOOT_FLOOR[battle.stage],
        )
        winner_peer = battle.participants[winner.id].peer_id
        await db.commit()
    try:
        await raid_combat._bot_api.messages.send(
            peer_id=winner_peer, message=item_service.format_drop_announcement(item), random_id=0,
        )
    except Exception:
        pass

    if battle.stage == 3:
        unique_id = raid_combat._unique_id(battle)
        async with raid_combat.get_session_factory()() as db:
            scalpel_winner = battle.rng.choice(candidates)
            scalpel_winner = await db.get(Character, scalpel_winner.id)
            scalpel = await item_service.grant_unique_item(
                db, scalpel_winner, unique_id, battle.rng,
            )
            peer_id = battle.participants[scalpel_winner.id].peer_id
            from services import raid_service
            await raid_service.finish_run(db, battle.run_id, won=True)
            await db.commit()
        try:
            await raid_combat._bot_api.messages.send(
                peer_id=peer_id,
                message=f"🔴 Тебе достаётся {scalpel.name}.",
                random_id=0,
            )
        except Exception:
            pass


async def _rift_gold(db, battle: raid_combat.RaidBattle, character: Character, stage: int) -> str:
    """Золото разлома за этап - в «мобах» кольца, как у событий."""
    from services import guild_service, scene_event_service, wallet_service

    if stage == battle.final_stage:
        mobs = rfc.STAGE_GOLD_MOBS[-1]
    else:
        mobs = rfc.STAGE_GOLD_MOBS[stage - 1]
    amount = scene_event_service.gold_amount(character, mobs)
    await wallet_service.deposit(db, character.id, "farm", amount)
    return f"💰 +{guild_service.gold_label(character, amount)}"


async def _grant_rift_legendaries(battle: raid_combat.RaidBattle) -> None:
    """Легендарная вещь (2 - у разлома на 5) случайным участникам всего
    захода, включая павших: победа общая. Уровень вещи - уровень разлома,
    но не выше уровня получателя: надеть её он должен сразу."""
    count = rfc.RIFT_TYPES[battle.rift_kind].legendaries
    async with raid_combat.get_session_factory()() as db:
        candidates = [c for c in [await db.get(Character, cid) for cid in battle.participants] if c is not None]
        if not candidates:
            return
        winners = battle.rng.sample(candidates, min(count, len(candidates)))
        while len(winners) < count:
            winners.append(battle.rng.choice(candidates))  # меньше людей, чем вещей
        drops = []
        for winner in winners:
            item = await raid_combat_service.grant_guaranteed_item(
                db, winner, min(battle.rift_level, winner.level), battle.rng, "legendary",
            )
            drops.append((winner, item))
        await db.commit()
    names = ", ".join(f"{w.name} - {item.name}" for w, item in drops)
    for cid, p in list(battle.participants.items()):
        lines = [item_service.format_drop_announcement(item) for w, item in drops if w.id == cid]
        lines.append(f"🟠 Легендарная добыча разлома: {names}.")
        try:
            await raid_combat._bot_api.messages.send(peer_id=p.peer_id, message="\n\n".join(lines), random_id=0)
        except Exception:
            logger.exception("Разлом: не доставлена добыча {}", p.peer_id)


async def _grant_blood_chests(battle: raid_combat.RaidBattle) -> None:
    """Кровавый разлом пройден (2026-10-13): каждому участнику захода,
    включая павших, - Ларец руды и Ларец расходников. Открываются в сумке
    мини-аппа рулеткой, как Пепельный."""
    from services import lootbox_service

    async with raid_combat.get_session_factory()() as db:
        for cid in list(battle.participants):
            character = await db.get(Character, cid)
            if character is None:
                continue
            for kind in (lootbox_service.ORE, lootbox_service.SUPPLY):
                await lootbox_service.grant_chest(db, character, character.daily_streak or 1, kind)
        await db.commit()
    text = (
        "🩸 Кровавый разлом отдаёт своё: ⛏ Ларец руды и 🧪 Ларец расходников - "
        "в сумке, открыть в мини-аппе."
    )
    for p in list(battle.participants.values()):
        try:
            await raid_combat._bot_api.messages.send(peer_id=p.peer_id, message=text, random_id=0)
        except Exception:
            logger.exception("Разлом: не доставлены ларцы {}", p.peer_id)


async def _finish_victory(session_id: int, battle: raid_combat.RaidBattle) -> None:
    await _grant_pending_rewards(battle)
    if battle.is_rift:
        await _grant_rift_legendaries(battle)
        if getattr(battle, "rift_blood", False):
            await _grant_blood_chests(battle)
    else:
        await _grant_stage_clear_bonus(battle)
    texts = raid_combat._texts(battle)
    await _cleanup_and_return(session_id, battle, texts.EPILOGUE_TEXT, defeated=False)


async def _finish_wipe(session_id: int, battle: raid_combat.RaidBattle, text: str | None = None) -> None:
    texts = raid_combat._texts(battle)
    await _cleanup_and_return(session_id, battle, text or texts.RAID_DEFEAT_TEXT, defeated=True)


async def wipe(battle_id: int, text: str) -> None:
    """Архив: время головоломок или загадок вышло - гибнет вся группа."""
    battle = raid_combat._battles.get(battle_id)
    if battle is not None:
        await raid_combat._finish_wipe(battle_id, battle, text)


async def _send_location_summary(character_id: int, peer_id: int) -> None:
    from bot.handlers import world as world_handlers  # избегаем цикла импортов

    try:
        async with raid_combat.get_session_factory()() as db:
            character = await db.get(Character, character_id)
            if character is None:
                return
            text, attachment, keyboard = await world_handlers.location_summary_parts(db, character, peer_id)
        await raid_combat._bot_api.messages.send(
            peer_id=peer_id, message=text, random_id=0, attachment=attachment, keyboard=keyboard,
        )
    except Exception:
        logger.exception("Рейд: не удалось отправить сводку локации {}", peer_id)


#: Павшие в пройденном разломе поднимаются с этой долей здоровья (2026-10-16).
RIFT_RAISED_HP_PCT = 0.01


async def _cleanup_and_return(session_id: int, battle: raid_combat.RaidBattle, text: str, *, defeated: bool) -> None:
    """И победа, и поражение возвращают всех к Монолиту (0;0) — позиция
    персонажей не менялась на всём протяжении рейда, поэтому достаточно
    показать обычную клавиатуру перемещения ИМЕННО для этой клетки."""
    raid_combat._battles.pop(session_id, None)
    trial_tracking.drop(session_id)
    raid_combat._declared_this_tick.pop(session_id, None)
    combatants = battle.last_combatants
    state = raid_combat._engine.sessions.get(session_id)
    if state is not None:
        combatants = dict(state.combatants)
    for p in list(battle.participants.values()):
        raid_combat._peer_battle.pop(p.peer_id, None)
        raid_combat._chosen_target.pop(p.character_id, None)
        raid_combat._character_in_raid.discard(p.character_id)

    raised: set[int] = set()
    async with raid_combat.get_session_factory()() as db:
        has_mount_by_cid = {}
        defeats: dict[int, object] = {}
        for cid in list(battle.participants):
            character = await db.get(Character, cid)
            if character is None:
                continue
            character.pos_x, character.pos_y = battle.home
            combatant = combatants.get(cid)
            survived = combatant is not None and combatant.alive and not defeated
            if (
                not survived and battle.is_rift and not defeated and combatant is not None
                and any(c.alive and c.kind == "character" for c in combatants.values())
            ):
                # Разлом пройден - павших поднимают свои (2026-10-16, как в
                # групповом PvE): на месте, с RIFT_RAISED_HP_PCT здоровья, без
                # смерти и потери опыта.
                from sqlalchemy import select

                from models import CharacterStats
                from services import vitals_service

                stats = await db.scalar(select(CharacterStats).where(CharacterStats.character_id == cid))
                if stats is not None:
                    vit_bonus = (await item_service.compute_gear_bonus(db, cid)).get("vit", 0)
                    vitals_service.set_hp(
                        character, stats, max(1, round(combatant.max_hp * RIFT_RAISED_HP_PCT)), vit_bonus,
                    )
                raised.add(cid)
                survived = True
            if survived:
                has_mount_by_cid[cid] = await mount_service.has_any_mount(db, cid)
                # Щит от снайпинга на выходе (2026-10-18): успеть уйти.
                pvp_shield.grant(
                    cid, pvp_shield.RIFT if battle.is_rift else pvp_shield.RAID, cell=tuple(battle.home),
                )
            else:
                defeats[cid] = (await encounter_service.resolve_defeat(db, character), character.respawn_at)
        from services import raid_service
        await raid_service.finish_run(db, battle.run_id, won=not defeated)
        if battle.is_rift:
            from services import rift_service

            await rift_service.finish_run(db, battle.rift_id, cleared=not defeated)
        await db.commit()

    # Таблица итогов ОДНА на всех и уходит каждому - и в победе, и в
    # поражении: разбор неудачного захода нужен не меньше, чем удачного.
    # Строится один раз - она у всех одинаковая, в этом и смысл: игроки
    # смотрят её, чтобы сравнить состав между собой.
    table = rt.contribution_table([
        (p.name, battle.contribution.get(cid, raid_combat.RaidContribution()))
        for cid, p in battle.participants.items()
    ])
    text = f"{text}\n\n{table}"

    for cid, p in list(battle.participants.items()):
        if cid in has_mount_by_cid:
            raised_line = (
                f"\n\n🩸 Ты пал в разломе, но группа его прошла и подняла тебя: "
                f"{round(RIFT_RAISED_HP_PCT * 100)}% здоровья, опыт не потерян."
                if cid in raised else ""
            )
            await raid_combat._bot_api.messages.send(
                peer_id=p.peer_id, message=text + raised_line + SAFE_EXIT_LINE, random_id=0,
                keyboard=movement_keyboard(*battle.home, p.peer_id, has_mount=has_mount_by_cid.get(cid, False)),
            )
            # Сводка клетки (0; 0), как после любого боя: без неё игрок
            # оставался с эпилогом и не видел, где стоит (живой прогон рейда).
            await _send_location_summary(cid, p.peer_id)
        elif cid in defeats:
            defeat, respawn_at = defeats[cid]
            await raid_combat._bot_api.messages.send(
                peer_id=p.peer_id, message=text, random_id=0, keyboard=kb.raid_waiting_keyboard(),
            )
            await respawn_handlers.register_death(p.peer_id, respawn_at, defeat.xp_lost, defeat.relics_lost, defeat.fish_lost)
        else:
            # Персонажа не нашли в БД. Раньше такой участник не получал НИ
            # ОДНОГО сообщения и оставался с боевой клавиатурой мёртвого боя.
            await raid_combat._bot_api.messages.send(
                peer_id=p.peer_id, message=text, random_id=0,
                keyboard=movement_keyboard(*battle.home, p.peer_id, has_mount=False),
            )


SAFE_EXIT_LINE = f"\n\n🛡 {bc.PVP_SAFE_SECONDS // 60} мин. на тебя нельзя нападать, пока не ушёл с этой клетки. Нападёшь сам - защита пропадёт."
