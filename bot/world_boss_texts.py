"""Тексты мировых боссов (патч 104). Коротко: заходы повторяются, лор - только
в объявлении, которое приходит раз на босса."""

from datetime import datetime, timezone

from game.economy import world_boss_config as wbc
from game.world import world_boss
from services import elixir_service, item_service, trophy_service

COMMANDS = ["Босс", "босс", "/босс", "/boss"]
BTN_ATTACK = "⚔️ Напасть"


def _pct(hp: int, max_hp: int) -> int:
    return round(100 * hp / max_hp) if max_hp else 0


def _where(boss) -> str:
    return f"кольцо {wbc.RING_NAMES[boss.ring]}, клетка ({boss.x};{boss.y})"


def _time_left(boss, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    expires = boss.expires_at if boss.expires_at.tzinfo else boss.expires_at.replace(tzinfo=timezone.utc)
    minutes = max(0, int((expires - now).total_seconds() // 60))
    hours, minutes = divmod(minutes, 60)
    return f"{hours} ч {minutes} мин" if hours else f"{minutes} мин"


def announce_text(boss) -> str:
    boss_def = world_boss.boss_def(boss.boss_id)
    return (
        f"👹 Мировой босс: {boss_def.name}\n\n{boss_def.flavor}\n\n"
        f"📍 {_where(boss)}. Уйдёт через {_time_left(boss)}.\n"
        f"Заход - {wbc.ATTEMPT_TURNS} ходов раз в час. Награда делится по урону.\n"
        f"Команда «Босс» - где он и сколько у него осталось."
    )


def here_text(boss) -> str:
    name = world_boss.boss_def(boss.boss_id).name
    return f"👹 {name} здесь. Здоровье {_pct(boss.hp, boss.max_hp)}%, уйдёт через {_time_left(boss)}."


def status_text(boss, my_damage: int, cooldown: int, can_attack: bool) -> str:
    if boss is None:
        return "Мировых боссов сейчас нет. Они приходят, когда в мире много исследуют."
    name = world_boss.boss_def(boss.boss_id).name
    lines = [
        f"👹 {name}: {_where(boss)}.",
        f"Здоровье {boss.hp}/{boss.max_hp} ({_pct(boss.hp, boss.max_hp)}%), уйдёт через {_time_left(boss)}.",
    ]
    if not can_attack:
        lines.append(f"Этот босс для уровня до {world_boss.max_attacker_level(boss.ring)}.")
        return "\n".join(lines)
    if my_damage:
        lines.append(f"Твой урон: {my_damage}.")
    if cooldown:
        lines.append(f"Следующий заход через {cooldown} мин.")
    return "\n".join(lines)


def refusal_text(reason: str, minutes_left: int = 0, ring: int | None = None) -> str:
    if reason == "cooldown":
        return f"Следующий заход через {minutes_left} мин."
    if reason == "level":
        return f"Этот босс для уровня до {world_boss.max_attacker_level(ring)}."
    if reason == "not_here":
        return "Босса на этой клетке нет."
    return "Босса уже нет."


def intro_text(boss) -> str:
    """Одна строка: заход повторяется каждый час, а описание босса игрок уже
    прочёл в объявлении."""
    return (
        f"Босс не отвечает на удары. У тебя {wbc.ATTEMPT_TURNS} ходов, "
        f"у него {boss.hp}/{boss.max_hp} здоровья."
    )


def turn_header(tick: int) -> str:
    return f"⚔️ БОЙ - ход {tick}/{wbc.ATTEMPT_TURNS}"


def contribution_lines(attempt: int, total: int) -> str:
    """Вклад в босса - только когда он больше этого захода: на первом заходе
    это одно и то же число."""
    line = f"🗡 Урон за заход: {attempt}"
    if total > attempt:
        line += f"\n📊 Вклад в босса: {total}"
    return line


def attempt_over_text(boss_gone: bool) -> str:
    """Цифры урона уже в логе последнего хода - здесь только что дальше."""
    if boss_gone:
        return "Заход окончен: босса больше нет."
    return f"Заход окончен. Следующий - через {wbc.ATTEMPT_COOLDOWN_MINUTES} мин."


def reward_lines(got) -> list[str]:
    lines = []
    if got.xp:
        lines.append(f"✨ Опыт +{got.xp}")
    for item in got.items:
        lines.append(f"🎁 {item_service.format_item_label(item)}")
    drop = trophy_service.format_drop_line(got.trophies, source="world_boss")
    if drop:
        lines.append(drop)
    elixirs = []
    for elixir_id, amount in got.elixirs.items():
        elixir = elixir_service.elixir_def(elixir_id)
        if elixir is not None:
            elixirs.append(f"{elixir.emoji} {elixir.name}" + (f" ×{amount}" if amount > 1 else ""))
    if elixirs:
        lines.append("🎒 " + ", ".join(elixirs) + ".")
    return lines


def end_text(boss, got, total_damage: int) -> str:
    boss_def = world_boss.boss_def(boss.boss_id)
    name, fem = boss_def.name, boss_def.feminine
    if boss.status == "killed":
        head = f"☠ {name} {'пала' if fem else 'пал'}!"
    else:
        removed = _pct(boss.max_hp - boss.hp, boss.max_hp)
        head = (
            f"{name} {'ушла' if fem else 'ушёл'}. С {'неё' if fem else 'него'} сняли {removed}% "
            f"здоровья - разыграна такая же часть награды."
        )
    share = _pct(got.damage, total_damage)
    lines = [head, f"Твой урон: {got.damage} ({share}% от всех)."]
    rewards = reward_lines(got)
    lines += rewards if rewards else ["В этот раз тебе ничего не выпало."]
    return "\n".join(lines)
