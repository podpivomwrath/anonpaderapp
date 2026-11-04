"""PvP: итоги боёв - колбэки тикового движка (и 1×1, и массовый), рендер боя,
победа и поражение, вести заказчикам контрактов.

Вынесено из bot/handlers/pvp.py без изменений логики (2026-10-22, нарезка).
Общее состояние боёв (_battles, _bot_api, движки) по-прежнему живёт в pvp.py -
здесь к нему обращаются как pvp.X, чтобы копия была одна и тесты подменяли там же.
"""

from loguru import logger

from bot import dailies_texts, short_log
from bot.handlers import respawn as respawn_handlers
from bot.handlers import stats_window
from bot.keyboards import world as kb
from bot.keyboards.pvp import pvp_combat_keyboard, pvp_waiting_keyboard
from bot.pvp_texts import NOTHING_TO_TAKE
from game.combat import balance_config as bc
from game.combat import battle_log, display
from game.combat.resolver import TickResult
from game.combat.session import ActionType, CombatSessionState
from game.combat.skills import DEFENSIVE_SKILLS
from game.economy import fishing as game_fishing
from models import Character
from services import pk_service, pts_service, subclass_service, trial_service
from services import admin_service, daily_service, death_service, fishing_service, mining_service, mount_service, pvp_service, trophy_service
from services import onboarding_service as onboarding_svc
from bot.handlers import pvp


# --- Итог боя 1×1 ---


async def _finish_duel(battle: pvp.Battle, winner_cid: int, loser_cid: int) -> None:
    winner_p = battle.participants[winner_cid]
    loser_p = battle.participants[loser_cid]

    async with pvp.get_session_factory()() as db:
        winner = await db.get(Character, winner_cid)
        loser = await db.get(Character, loser_cid)
        if winner is None or loser is None:
            return
        pvp_service.record_win(winner)
        pvp_service.record_loss(loser)
        # Напал сам и проиграл - самооборона победителя, клейма нет (2026-10-20).
        pk = await pk_service.on_pvp_kill(db, winner, loser, victim_attacked=battle.side_of.get(loser_cid) == 0)
        # Заказ на игрока (2026-10-16): после клейма - оно смотрит, взят ли заказ.
        from services import contract_service

        payout = await contract_service.on_kill(db, loser, [winner.id])
        await pts_service.season_rollover(db)
        await db.refresh(winner, ["pts", "pts_season"])
        await db.refresh(loser, ["pts", "pts_season"])
        # Повторы той же пары и бой без сопротивления (2026-10-31): набивка PTS.
        prior = await pts_service.recent_duels(db, winner.id, loser.id)
        pts_delta, pts_reason = pts_service.apply_duel(
            winner, loser, prior=prior, loser_tried=loser_cid in battle.tried_attack,
        )
        winner_pts_line = pts_service.delta_line(pts_delta, winner, pts_reason)
        loser_pts_line = pts_service.delta_line(-pts_delta, loser) if pts_delta else ""
        # Клеймо 3+: защита «слабого не обирают» снята - трофеи с него заберёт
        # и тот, кто старше на 10+ уровней.
        no_reward = pvp_service.no_reward_for_kill(winner.level, loser.level) and not pk_service.costly_death(loser)
        moved = {} if no_reward else await trophy_service.transfer_all(db, loser.id, winner.id)
        # Патч 58: рыба из садка ПРОПАДАЕТ, а не переходит победителю.
        # Иначе охотиться на рыбаков было бы выгоднее, чем рыбачить —
        # риск для проигравшего при этом сохраняется полностью.
        fish_lost = await fishing_service.drop_bag(db, loser.id)
        # Патч 59: добыча прерывается, но начатый кусок возвращается в жилу —
        # победитель прерывает работу, а не уничтожает общий ресурс.
        await mining_service.cancel_dig(db, loser)
        death_service.apply_pvp_death(loser)
        await admin_service.log_death(db, loser, "pvp")
        respawn_handlers.register_pvp_death(loser_p.peer_id)
        await pvp_service.log_battle(db, "duel", [winner_cid, loser_cid], [winner_cid])
        daily_progress = await daily_service.record_pvp_win(db, winner)
        # Испытания «победи выше уровнем» засчитывают и PvP (2026-10-13).
        trial_buffs = await trial_service.record_level_kill(db, winner, loser.level) if subclass_service.buff_pool(winner) else []
        winner_pos = (winner.pos_x, winner.pos_y)
        winner_has_mount = await mount_service.has_any_mount(db, winner.id)
        await db.commit()

    win_text = f"🏆 Ты побеждаешь {loser_p.name}!"
    if no_reward:
        win_text += f"\n\n{NOTHING_TO_TAKE}"
    else:
        line = pvp._format_transfer_line(moved)
        if line:
            win_text += f"\n\n{line}"
    if winner_pts_line:
        win_text += f"\n\n{winner_pts_line}"
    daily_notice = dailies_texts.progress_notice(daily_progress)
    if daily_notice:
        win_text += f"\n\n{daily_notice}"
    for buff_id in trial_buffs:
        win_text += f"\n\n📖 Испытание пройдено. Открыт бафф: {trial_service.buff_name(buff_id)}."
    if pk.killer_lines:
        win_text += "\n\n" + "\n".join(pk.killer_lines)
    if payout.hunter_lines.get(winner_cid):
        win_text += "\n\n" + "\n".join(payout.hunter_lines[winner_cid])
    await pvp._bot_api.messages.send(
        peer_id=winner_p.peer_id, message=win_text, random_id=0,
        keyboard=kb.movement_keyboard(*winner_pos, winner_p.peer_id, has_mount=winner_has_mount),
    )
    for c in daily_progress.completed:
        await stats_window.notify_levelup(winner_p.peer_id, c.levels_gained, c.new_level)
    lose_text = f"☠ Тебя побеждает {winner_p.name}. Ты уходишь во тьму."
    if pk.victim_lines:
        lose_text += "\n\n" + "\n".join(pk.victim_lines)
    if payout.victim_lines:
        lose_text += "\n\n" + "\n".join(payout.victim_lines)
    if loser_pts_line:
        lose_text += f"\n\n{loser_pts_line}"
    if fish_lost:
        # Потерю садка нужно назвать вслух: рыба не переходит победителю, и
        # без строки игрок решил бы, что улов просто пропал из-за бага.
        lose_text += (
            chr(10) * 2
            + f"🧺 Садок пропал: {game_fishing.format_kg(fish_lost)} рыбы."
        )
    await pvp._bot_api.messages.send(
        peer_id=loser_p.peer_id, message=lose_text,
        random_id=0, keyboard=kb.waiting_keyboard(),
    )
    await _notify_orderers(payout.orderer_notes)


async def _notify_orderers(notes: list[tuple[int, str]]) -> None:
    """Заказчику - что убийство по его заказу выполнено (без имён охотников)."""
    if not notes:
        return
    async with pvp.get_session_factory()() as db:
        peers = {cid: await onboarding_svc.vk_id_for_character(db, cid) for cid, _ in notes}
    for cid, text in notes:
        if peers.get(cid):
            try:
                await pvp._bot_api.messages.send(peer_id=peers[cid], message=text, random_id=0)
            except Exception:  # noqa: BLE001 - заказчик закрыл диалог с ботом
                pass


# --- Массовый бой: рендер + колбэки тик-движка ---


def _render_mass(session: CombatSessionState, lines: list[str]) -> str:
    battle = pvp._battles.get(session.session_id)
    titles = battle.side_titles if battle is not None and battle.side_titles else None
    header = f"{'🏰 ОСАДА' if titles else '⚔️ БОЙ'} - ход {session.tick_number}"
    side_lines = []
    for side in (0, 1):
        members = [c for c in session.combatants.values() if c.side == side]
        roster = ", ".join(f"{c.name} {display.health_bar(c.current_hp, c.max_hp)}" for c in members)
        title = titles[side] if titles else f"Сторона {side + 1}"
        side_lines.append(f"{title}: {roster}")
    log = " ".join(lines) if lines else "Бой продолжается."
    return "\n".join([header, *side_lines, "", log])


def _render_mass_tick(session: CombatSessionState, result: TickResult, viewer_side: int, battle: pvp.Battle) -> str:
    """Итоги хода массового боя глазами стороны viewer_side - тот же формат, что
    у PvE и рейдов (game/combat/battle_log.py): разделы «ваша сторона» и
    «противник», у осады - с названиями сторон."""
    titles = battle.side_titles if battle.side_titles else None
    return battle_log.render_tick(
        session, result, viewer_side=viewer_side,
        title="🏰 ОСАДА" if titles else "⚔️ БОЙ", side_titles=titles,
    )


async def on_mass_tick_resolved(session_id: int, tick: int, result: TickResult) -> None:
    battle = pvp._battles.get(session_id)
    if battle is None:
        return
    # Патч 31, п.6: новое окно открылось — все живые снова могут объявлять.
    pvp._declared_this_tick.pop(session_id, None)
    for hit in result.hits:
        if hit.source_id == hit.target_id:
            continue
        key = (hit.source_id, hit.target_id)
        battle.damage_by_pair[key] = battle.damage_by_pair.get(key, 0) + hit.amount
    for cid, action in result.actions.items():
        if action.type == ActionType.ATTACK or (
            action.type == ActionType.SKILL and action.skill_id not in DEFENSIVE_SKILLS
        ):
            battle.tried_attack.add(cid)

    session = pvp._mass_engine.sessions.get(session_id)
    if session is not None:
        battle.last_combatants = dict(session.combatants)
    # Лог хода - у каждой стороны свой вид («ВАША СТОРОНА» / «ПРОТИВНИК»): общий
    # текст со всеми событиями в одну строку не давал понять, кто за кого бьёт.
    text_by_side: dict[int, str] = {}

    def _board_for(cid: int) -> str:
        if session is None:
            return "\n".join(result.lines)
        side = battle.side_of.get(cid, 0)
        if side not in text_by_side:
            text_by_side[side] = _render_mass_tick(session, result, side, battle)
        return text_by_side[side]

    short_by_side: dict[int, str] = {}

    def _short_for(cid: int) -> str:
        if session is None:
            return "\n".join(result.lines)
        side = battle.side_of.get(cid, 0)
        if side not in short_by_side:
            short_by_side[side] = battle_log.render_short(
                session, result, viewer_side=side, title="🏰 ОСАДА" if battle.side_titles else "⚔️ БОЙ",
            )
        return short_by_side[side]

    # Патч 38: у кого цель погибла в этот тик — автопереключение на первого
    # живого противника + личное уведомление (не в общий боевой лог, у
    # каждого своя цель, значит и уведомление у каждого своё).
    switch_notices: dict[int, str] = {}
    if result.deaths:
        dead_names = {cid: c.name for cid, c in battle.last_combatants.items() if cid in result.deaths}
        dead_set = set(result.deaths)
        for cid, target_cid in list(pvp._chosen_target.items()):
            if target_cid not in dead_set or cid not in battle.participants:
                continue
            me = battle.last_combatants.get(cid)
            if me is None or not me.alive:
                continue
            enemies = pvp._enemies_of(session_id, battle, cid)
            dead_name = dead_names.get(target_cid, "Цель")
            if enemies:
                pvp._chosen_target[cid] = enemies[0]
                new_name = battle.last_combatants[enemies[0]].name
                switch_notices[cid] = f"{dead_name} падает. Новая цель: {new_name}."
            else:
                pvp._chosen_target.pop(cid, None)  # бой вот-вот завершится (сторона добита)

    for cid, participant in list(battle.participants.items()):
        combatant = battle.last_combatants.get(cid)
        keyboard = (
            pvp_combat_keyboard(participant.base_class, combatant.cooldowns, subclass_id=combatant.subclass_id, show_target=True)
            if combatant is not None and combatant.alive
            else pvp_waiting_keyboard()
        )
        personal_text = _board_for(cid)
        short_text = _short_for(cid)
        notice = switch_notices.get(cid)
        if notice:
            personal_text = f"{notice}\n\n{personal_text}"
            short_text = f"{notice}\n\n{short_text}"
        target_line = pvp._target_line(session_id, battle, cid)
        if target_line:
            personal_text = f"{personal_text}\n{target_line}"
            short_text = f"{short_text}\n{target_line}"
        own = battle_log.class_line(session.combatants, cid) if session is not None else None
        if own:
            personal_text = f"{personal_text}\n{own}"
        await short_log.send(pvp._bot_api, participant.peer_id, short_text, personal_text, keyboard)


async def on_mass_battle_finished(session_id: int, result: TickResult) -> None:
    battle = pvp._battles.pop(session_id, None)
    pvp._declared_this_tick.pop(session_id, None)
    if battle is None:
        return
    for p in list(battle.participants.values()):
        pvp._peer_battle.pop(p.peer_id, None)
        pvp._chosen_target.pop(p.character_id, None)

    combatants = battle.last_combatants
    dead_ids = [cid for cid in battle.participants if cid in combatants and not combatants[cid].alive]
    survivor_ids = [cid for cid in battle.participants if cid in combatants and combatants[cid].alive]

    if battle.arena:
        # Арена: ни смерти, ни трофеев, ни рейтинга - игроки возвращаются на арену.
        if pvp.on_arena_finished is not None:
            winner = survivor_ids[0] if not result.draw and len(survivor_ids) == 1 else None
            await pvp.on_arena_finished(battle, winner, result.draw)
        return
    if (battle.siege_id is None and not result.draw and len(battle.participants) == 2
            and len(dead_ids) == 1 and len(survivor_ids) == 1):
        # Бой один на один (2026-10-29: дуэль идёт на этом же движке) - итог
        # как у дуэли: все трофеи победителю, очки PTS по правилу дуэли.
        await _finish_duel(battle, survivor_ids[0], dead_ids[0])
        return

    if battle.siege_id is not None:
        from bot.handlers import guild_siege  # избегаем цикла импортов

        await guild_siege.on_siege_battle_finished(battle, result, dead_ids, survivor_ids)
        return

    async with pvp.get_session_factory()() as db:
        characters: dict[int, Character] = {}
        for cid in list(battle.participants):
            character = await db.get(Character, cid)
            if character is not None:
                characters[cid] = character

        winner_ids: list[int] = []
        daily_progress_by_cid: dict[int, object] = {}
        if not result.draw:
            winner_ids = list(survivor_ids)
            for cid in winner_ids:
                if cid in characters:
                    pvp_service.record_win(characters[cid])
                    daily_progress_by_cid[cid] = await daily_service.record_pvp_win(db, characters[cid])
            for cid in dead_ids:
                if cid in characters:
                    pvp_service.record_loss(characters[cid])

        # PTS: каждая гибель - очки тем, кто бил жертву, по доле урона. Ничья -
        # без PTS (2026-10-13).
        pts_deltas: dict[int, int] = {}
        if not result.draw:
            await pts_service.season_rollover(db)
            for character in characters.values():
                await db.refresh(character, ["pts", "pts_season"])
            pts_deltas = pts_service.apply_mass(characters, dead_ids, battle.damage_by_pair, battle.side_of)
        pts_lines = {cid: pts_service.delta_line(d, characters[cid]) for cid, d in pts_deltas.items()}
        transfer_lines: dict[int, list[str]] = {}
        pk_lines: dict[int, list[str]] = {}
        pk_outcomes: dict[int, list] = {}
        orderer_notes: list[tuple[int, str]] = []
        for victim_cid in dead_ids:
            victim = characters.get(victim_cid)
            if victim is None:
                continue
            victim_costly = pk_service.costly_death(victim)
            # Кровавое клеймо: каждый, кто бил жертву, отвечает за её смерть.
            hitters = sorted(
                (a for a in survivor_ids if battle.damage_by_pair.get((a, victim_cid), 0) > 0 and a in characters),
                key=lambda a: -battle.damage_by_pair.get((a, victim_cid), 0),
            )
            if not result.draw:
                for attacker_cid in hitters:
                    pk = await pk_service.on_pvp_kill(
                        db, characters[attacker_cid], victim, victim_attacked=battle.side_of.get(victim_cid) == 0,
                    )
                    pk_outcomes.setdefault(attacker_cid, []).append(pk)
                    pk_lines.setdefault(victim_cid, []).extend(pk.victim_lines)
                # Заказ на игрока: доля - каждому взявшему заказ, кто бил цель.
                from services import contract_service

                payout = await contract_service.on_kill(db, victim, hitters)
                for hunter_cid, hunter_lines in payout.hunter_lines.items():
                    pk_lines.setdefault(hunter_cid, []).extend(hunter_lines)
                pk_lines.setdefault(victim_cid, []).extend(payout.victim_lines)
                orderer_notes.extend(payout.orderer_notes)
            shares: dict[int, float] = {}
            for attacker_cid in survivor_ids:
                dmg = battle.damage_by_pair.get((attacker_cid, victim_cid), 0)
                if dmg <= 0:
                    continue
                attacker = characters.get(attacker_cid)
                if attacker is None or (
                    pvp_service.no_reward_for_kill(attacker.level, victim.level) and not victim_costly
                ):
                    continue
                shares[attacker_cid] = dmg
            moved = await trophy_service.split_among(db, victim_cid, shares) if shares else {}
            # Патч 58: садок пропадает и в массовом PvP, по тому же правилу.
            await fishing_service.drop_bag(db, victim_cid)
            victim_character = await db.get(Character, victim_cid)
            if victim_character is not None:
                await mining_service.cancel_dig(db, victim_character)
            for winner_cid, drop in moved.items():
                line = pvp._format_transfer_line(drop)
                if line:
                    transfer_lines.setdefault(winner_cid, []).append(f"{victim.name}: {line}")
            death_service.apply_pvp_death(victim)
            await admin_service.log_death(db, victim, "pvp")
            respawn_handlers.register_pvp_death(battle.participants[victim_cid].peer_id)
        # Клеймо за массовый бой - одной сводкой на убийцу.
        for attacker_cid, outcomes in pk_outcomes.items():
            pk_lines.setdefault(attacker_cid, []).extend(
                pk_service.mass_killer_lines(characters[attacker_cid], outcomes)
            )

        # Испытания «победи выше уровнем»: павший враг выше тебя, по которому
        # ты попал (2026-10-13).
        trial_lines: dict[int, list[str]] = {}
        for cid in winner_ids:
            me = characters.get(cid)
            if me is None or subclass_service.buff_pool(me) is None:
                continue
            top = max(
                (characters[v].level for v in dead_ids
                 if v in characters and battle.damage_by_pair.get((cid, v), 0) > 0),
                default=0,
            )
            if top > me.level:
                trial_lines[cid] = [
                    f"📖 Испытание пройдено. Открыт бафф: {trial_service.buff_name(b)}."
                    for b in await trial_service.record_level_kill(db, me, top)
                ]
        await pvp_service.log_battle(db, "mass", list(battle.participants), winner_ids)
        has_mount_by_cid = {
            cid: await mount_service.has_any_mount(db, cid) for cid in survivor_ids if cid in characters
        }
        await db.commit()
        positions = {cid: (c.pos_x, c.pos_y) for cid, c in characters.items()}

    # Патч 30: ничья (взаимное истощение ИЛИ лимит ходов) — раньше этот случай
    # никак не отличался от обычного финала, и выжившие получали "ты
    # победил", даже когда бой на самом деле закончился вничью.
    draw_text = (
        bc.PVP_DRAW_TURN_LIMIT_TEXT if result.draw_reason == "turn_limit"
        else "🤝 Ничья: взаимное истощение. Трофеи остаются при каждом."
    )
    shielded = pvp._grant_draw_shield(battle, survivor_ids) if result.draw else []
    for cid, participant in list(battle.participants.items()):
        if result.draw and cid in dead_ids:
            # Павший до конца боя умер по-настоящему (2026-10-18, баг-репорт:
            # ему же приходило «Ничья. Списки остались нетронутыми»).
            await pvp._bot_api.messages.send(
                peer_id=participant.peer_id, random_id=0, keyboard=kb.waiting_keyboard(),
                message="☠ Тебя одолели в бою. Остальные разошлись вничью, но для тебя бой кончился раньше."
                + ("\n\n" + "\n".join(pk_lines[cid]) if pk_lines.get(cid) else ""),
            )
        elif result.draw:
            pos = positions.get(cid, (0, 0))
            keyboard = kb.movement_keyboard(*pos, participant.peer_id, has_mount=has_mount_by_cid.get(cid, False))
            text = draw_text if not dead_ids else (
                "🤝 Ничья: выжившие расходятся, но павшие в этом бою ушли во тьму."
            )
            if transfer_lines.get(cid):
                text += "\n\n" + "\n".join(transfer_lines[cid])
            if cid in shielded:
                text += f"\n\n{pvp.DRAW_SHIELD_LINE}"
            await pvp._bot_api.messages.send(peer_id=participant.peer_id, random_id=0, keyboard=keyboard, message=text)
        elif cid in survivor_ids:
            text = "🏆 Бой окончен - твоя сторона побеждает!"
            lines = transfer_lines.get(cid, [])
            if lines:
                text += "\n\n" + "\n".join(lines)
            if pts_lines.get(cid):
                text += f"\n\n{pts_lines[cid]}"
            daily_progress = daily_progress_by_cid.get(cid)
            daily_notice = dailies_texts.progress_notice(daily_progress) if daily_progress else None
            if daily_notice:
                text += f"\n\n{daily_notice}"
            if trial_lines.get(cid):
                text += "\n\n" + "\n".join(trial_lines[cid])
            if pk_lines.get(cid):
                text += "\n\n" + "\n".join(pk_lines[cid])
            pos = positions.get(cid, (0, 0))
            await pvp._bot_api.messages.send(
                peer_id=participant.peer_id, message=text, random_id=0,
                keyboard=kb.movement_keyboard(
                    *pos, participant.peer_id, has_mount=has_mount_by_cid.get(cid, False)
                ),
            )
            if daily_progress:
                for c in daily_progress.completed:
                    await stats_window.notify_levelup(participant.peer_id, c.levels_gained, c.new_level)
        elif cid in dead_ids:
            await pvp._bot_api.messages.send(
                peer_id=participant.peer_id,
                message="☠ Тебя одолели в бою. Ты уходишь во тьму."
                + (f"\n\n{pts_lines[cid]}" if pts_lines.get(cid) else "")
                + ("\n\n" + "\n".join(pk_lines[cid]) if pk_lines.get(cid) else ""),
                random_id=0, keyboard=kb.waiting_keyboard(),
            )
    await _notify_orderers(orderer_notes)


# --- Итог сезона PvP (2026-10-30, владелец) ---


def season_result_text(result) -> str:
    from game import plural
    from services import title_service

    return (
        f"🏆 Сезон PvP {result.season} окончен: ты на {result.place} месте, "
        f"{result.pts} PTS за {plural.count(result.fights, 'бой', 'боя', 'боёв')}.\n"
        f"Титул «{title_service.name_of(result.title_id)}» твой на весь новый сезон, "
        f"на счёт пришло 💎 {result.gems}. Чтобы оставить титул, войди в пятёрку снова."
    )


async def notify_season_results() -> None:
    """Личное сообщение каждому призёру сезона, один раз (notified)."""
    from sqlalchemy import select

    from models import PvpSeasonResult, User

    async with pvp.get_session_factory()() as db:
        rows = (await db.scalars(select(PvpSeasonResult).where(PvpSeasonResult.notified.is_(False)))).all()
        for result in rows:
            character = await db.get(Character, result.character_id)
            user = await db.get(User, character.user_id) if character is not None else None
            result.notified = True
            if user is None:
                continue
            try:
                await pvp._bot_api.messages.send(peer_id=user.vk_id, random_id=0, message=season_result_text(result))
            except Exception:
                logger.warning("Сезон PvP: итог не доставлен {}", user.vk_id)
        await db.commit()
