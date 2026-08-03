"""Тексты уведомлений ежедневных заданий и наград за вход (патч 23)."""

from game.economy import dailies_config as dc
from services import elixir_service
from services.daily_service import DailiesOverview, DailyProgressResult, LoginCycleState


def progress_notice_from(completed: list, streak_notice: str | None) -> str | None:
    """Текст для чата при завершении ежедневки(ек) этим действием + (если
    сработал рубеж стрика) отдельная строка про рубеж. None — ничего не
    произошло (обычный случай — большинство действий не завершают задание)."""
    if not completed and streak_notice is None:
        return None
    lines = []
    for c in completed:
        lines.append(f"✅ Ежедневка «{c.quest_title}» выполнена! +{c.xp} опыта, +{c.gold} золота.")
    if streak_notice:
        lines.append(streak_notice)
    return "\n".join(lines)


def progress_notice(result: DailyProgressResult) -> str | None:
    return progress_notice_from(result.completed, result.streak_notice)


def _reward_preview(reward: dict) -> str:
    parts = []
    if "gold" in reward:
        parts.append(f"{reward['gold']} золота")
    if "gems" in reward:
        parts.append(f"💎 {reward['gems']} самоцветов")
    if "elixir" in reward:
        elixir_id, count = reward["elixir"]
        edef = elixir_service.elixir_def(elixir_id)
        name = f"{edef.emoji} {edef.name}" if edef is not None else elixir_id
        parts.append(f"{name} ×{count}")
    if "elixirs_random_combat" in reward:
        parts.append(f"{reward['elixirs_random_combat']} случайных боевых эликсира (по 2 шт. каждого)")
    if "title" in reward:
        parts.append(f"титул «{dc.TITLE_NAMES.get(reward['title'], reward['title'])}»")
    return ", ".join(parts)


def dailies_overview_text(overview: DailiesOverview) -> str:
    lines = ["📜 Ежедневные задания", ""]
    for q in overview.quests:
        mark = "✅" if q.completed else "▫️"
        lines.append(f"{mark} {q.title}: {q.progress}/{q.target} — {q.progress_label}")
        if not q.completed:
            lines.append(f"    Награда: +{q.xp_reward} опыта, +{q.gold_reward} золота")
    lines.append("")
    lines.append(f"🔥 Стрик ежедневок: {overview.daily_streak} дней")
    if overview.next_milestone_day is not None:
        lines.append(
            f"Следующий рубеж: день {overview.next_milestone_day} — "
            f"{_reward_preview(overview.next_milestone_reward)}"
        )
    hours, rem = divmod(max(overview.seconds_until_reset, 0), 3600)
    minutes = rem // 60
    lines.append(f"⏳ До сброса дня: {hours}ч {minutes}м")
    return "\n".join(lines)


def login_overview_text(state: LoginCycleState) -> str:
    lines = ["📅 Награда за вход", "", f"Стрик входа: {state.login_streak} дней"]
    lines.append(f"День цикла: {state.cycle_day}/{state.cycle_length}")
    if state.today_reward is not None:
        status = "уже получена сегодня" if state.claimed_today else "будет выдана автоматически"
        lines.append(f"Награда дня: {_reward_preview(state.today_reward)} ({status})")
    next_day = state.cycle_day % state.cycle_length + 1
    next_reward = state.rewards.get(next_day)
    if next_reward is not None:
        lines.append(f"Завтра (день {next_day}): {_reward_preview(next_reward)}")
    return "\n".join(lines)
