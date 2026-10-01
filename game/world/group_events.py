"""Групповые события исследования: чистая логика без БД.

Групповое исследование раньше всегда заканчивалось боем. Теперь часть
бросков - событие, где решают все сразу: каждый выбирает в своём диалоге,
по таймеру выборы раскрываются, и исход зависит от того, что выбрала
группа целиком. Такого в соло нет и быть не может.

Механики (поле mechanic в content/events/group_scenes.json):
- split  - делёж находки: поровну или забрать себе (дилемма заключённого);
- vote   - голосование у развилки, тайное; ничья - решает лидер группы;
- roles  - каждому роль, каждой роли нужно хватить людей;
- rescue - тонет один, остальные тянут или уходят со своим.

Награды - в «мобах», как у соло-событий (game/world/scene_events.py), и
дополнительно умножаются на GROUP_REWARD_MULT: игра в группе обязана быть
выгоднее одиночной, иначе её не выбирают. Смертей нет: худшее - разорение
(HP до 1% и часть трофеев), как в соло.

Запись в БД - через services/scene_event_service.apply_result (тот же
расчёт наград), показ и таймер - bot/handlers/group_events.py.
"""

import math
import random
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel, Field

from game.content_loader import CONTENT_DIR, _load_json_dict
from game.world.scene_events import SceneResult

#: Во сколько раз групповое событие щедрее соло-события с теми же числами
#: в контенте. Применяется к опыту, трофеям и золоту каждого участника.
GROUP_REWARD_MULT = 1.5

#: Доля групповых исследований, которые становятся событием, а не боем.
GROUP_EVENT_CHANCE = 0.35

#: Сколько ждём выборов. Как ход группового боя: кто не успел - выбрал
#: вариант по умолчанию.
DECISION_SECONDS = 60

SPLIT_SHARE, SPLIT_TAKE = "share", "take"
RESCUE_PULL, RESCUE_LEAVE = "pull", "leave"


class Option(BaseModel):
    """Вариант голосования: подпись и исходы, один из которых выпадет."""

    label: str
    outcomes: list[SceneResult]


class Role(BaseModel):
    id: str
    label: str
    #: Сколько людей нужно: число или "half" - половина группы с округлением вверх.
    need: int | str = 1
    #: Что будет со всеми, если на роль не хватило людей.
    shortfall: SceneResult


class GroupEvent(BaseModel):
    id: str
    title: str
    mechanic: str                        # split | vote | roles | rescue
    text: str
    weight: float = 1.0
    rings: list[int] | None = None
    regions: list[str] | None = None
    image: str | None = None
    min_members: int = 2

    # split
    share_label: str = "Поровну"
    take_label: str = "Забрать себе"
    all_share: SceneResult | None = None     # каждому
    taker: SceneResult | None = None         # одному забравшему
    robbed: SceneResult | None = None        # остальным, когда забрал один
    greedy: SceneResult | None = None        # всем, когда забрать решили двое и больше

    # vote
    options: list[Option] = Field(default_factory=list)

    # roles
    roles: list[Role] = Field(default_factory=list)
    success: SceneResult | None = None       # всем, если каждой роли хватило

    # rescue: тонет один, остальные решают
    victim_text: str = ""
    pull_label: str = "Тянуть"
    leave_label: str = "Уйти со своим"
    #: Сколько тянущих нужно: число или "half" (половина остальных, вверх).
    pull_need: int | str = "half"
    saved: SceneResult | None = None         # всем, кто остался с ним, и ему
    left: SceneResult | None = None          # ушедшему: своё, независимо от исхода
    drowned: SceneResult | None = None       # жертве, если вытянуть не смогли
    strained: SceneResult | None = None      # тянувшим впустую


class GroupContent(BaseModel):
    events: list[GroupEvent]


_content: GroupContent | None = None


def load(content_dir: Path = CONTENT_DIR) -> GroupContent:
    return GroupContent(**_load_json_dict(content_dir / "events" / "group_scenes.json"))


def content() -> GroupContent:
    global _content
    if _content is None:
        _content = load()
    return _content


def event_by_id(event_id: str) -> GroupEvent | None:
    return next((e for e in content().events if e.id == event_id), None)


def pick_event(rng: random.Random, ring: int, region: str, members: int) -> GroupEvent | None:
    pool = [
        e for e in content().events
        if (e.rings is None or ring in e.rings)
        and (e.regions is None or region in e.regions)
        and members >= e.min_members
    ]
    if not pool:
        return None
    return rng.choices(pool, weights=[e.weight for e in pool])[0]


def need_count(need: int | str, people: int) -> int:
    if need == "half":
        return max(1, math.ceil(people / 2))
    return max(1, int(need))


def choices_of(event: GroupEvent, member_id: int, victim_id: int | None) -> list[tuple[str, str]]:
    """[(значение, подпись)] - кнопки участника. У жертвы в спасении кнопок нет."""
    if event.mechanic == "split":
        return [(SPLIT_SHARE, event.share_label), (SPLIT_TAKE, event.take_label)]
    if event.mechanic == "vote":
        return [(str(i), o.label) for i, o in enumerate(event.options)]
    if event.mechanic == "roles":
        return [(r.id, r.label) for r in event.roles]
    if event.mechanic == "rescue":
        if member_id == victim_id:
            return []
        return [(RESCUE_PULL, event.pull_label), (RESCUE_LEAVE, event.leave_label)]
    return []


def default_choice(event: GroupEvent) -> str | None:
    """Что «выбрал» тот, кто не успел. Промолчавший в делёже не жадничает,
    в остальных механиках - просто не участвует."""
    return SPLIT_SHARE if event.mechanic == "split" else None


# --- Итог ------------------------------------------------------------------------


@dataclass
class Outcome:
    """Кому что достаётся и что рассказать всем."""

    #: {id участника: исход} - исход применяется к каждому отдельно
    results: dict[int, SceneResult] = field(default_factory=dict)
    #: строки итога, одинаковые для всех (кто что выбрал, чем кончилось)
    summary: list[str] = field(default_factory=list)
    #: группа попала в засаду - после итога начинается групповой бой
    combat: bool = False


def resolve(
    event: GroupEvent, members: dict[int, str], choices: dict[int, str | None],
    rng: random.Random, leader_id: int | None = None, victim_id: int | None = None,
) -> Outcome:
    """members - {id: имя} всех участников; choices - {id: выбор или None}."""
    resolver = {
        "split": _resolve_split, "vote": _resolve_vote,
        "roles": _resolve_roles, "rescue": _resolve_rescue,
    }[event.mechanic]
    return resolver(event, members, choices, rng, leader_id, victim_id)


def _names(members: dict[int, str], ids) -> str:
    return ", ".join(members[i] for i in sorted(ids, key=lambda i: members[i]))


def _resolve_split(event, members, choices, rng, leader_id, victim_id) -> Outcome:
    takers = [i for i in members if choices.get(i) == SPLIT_TAKE]
    sharers = [i for i in members if i not in takers]
    out = Outcome()
    if sharers:
        out.summary.append(f"🤝 Поровну: {_names(members, sharers)}")
    if takers:
        out.summary.append(f"✋ Себе: {_names(members, takers)}")
    if not takers:
        out.results = {i: event.all_share for i in members}
    elif len(takers) == 1:
        out.results = {i: (event.taker if i in takers else event.robbed) for i in members}
    else:
        out.results = {i: event.greedy for i in members}
    out.results = {i: r for i, r in out.results.items() if r is not None}
    return out


def _resolve_vote(event, members, choices, rng, leader_id, victim_id) -> Outcome:
    counts = [0] * len(event.options)
    for i in members:
        value = choices.get(i)
        if value is not None and value.isdigit() and int(value) < len(counts):
            counts[int(value)] += 1
    top = max(counts)
    leaders = [k for k, n in enumerate(counts) if n == top]
    out = Outcome()
    # Голосование тайное: видно, сколько за что, но не кто.
    out.summary.append("🗳 " + " · ".join(f"{o.label}: {n}" for o, n in zip(event.options, counts, strict=True)))
    if len(leaders) == 1:
        winner = leaders[0]
    else:
        leader_vote = choices.get(leader_id) if leader_id is not None else None
        if leader_vote is not None and leader_vote.isdigit() and int(leader_vote) in leaders:
            winner = int(leader_vote)
            out.summary.append("Голоса разделились - решает лидер.")
        else:
            winner = rng.choice(leaders)
            out.summary.append("Голоса разделились - решает случай.")
    option = event.options[winner]
    result = rng.choices(option.outcomes, weights=[o.weight for o in option.outcomes])[0]
    out.summary.append(f"Группа выбирает: {option.label}.")
    out.results = {i: result for i in members}
    out.combat = result.combat is not None
    return out


def _resolve_roles(event, members, choices, rng, leader_id, victim_id) -> Outcome:
    people = len(members)
    out = Outcome()
    short = None
    for role in event.roles:
        taken = [i for i in members if choices.get(i) == role.id]
        need = need_count(role.need, people)
        mark = "✅" if len(taken) >= need else "❌"
        who = _names(members, taken) if taken else "никто"
        out.summary.append(f"{mark} {role.label} ({len(taken)}/{need}): {who}")
        if len(taken) < need and short is None:
            short = role
    result = short.shortfall if short is not None else event.success
    out.results = {i: result for i in members} if result is not None else {}
    out.combat = result is not None and result.combat is not None
    return out


def _resolve_rescue(event, members, choices, rng, leader_id, victim_id) -> Outcome:
    others = [i for i in members if i != victim_id]
    pullers = [i for i in others if choices.get(i) == RESCUE_PULL]
    leavers = [i for i in others if i not in pullers]
    need = need_count(event.pull_need, len(others))
    out = Outcome()
    out.summary.append(f"🪢 Тянули ({len(pullers)}/{need}): {_names(members, pullers) if pullers else 'никто'}")
    if leavers:
        out.summary.append(f"🚶 Ушли: {_names(members, leavers)}")
    saved = len(pullers) >= need
    for i in leavers:
        if event.left is not None:
            out.results[i] = event.left
    if saved:
        for i in [*pullers, victim_id]:
            if event.saved is not None and i is not None:
                out.results[i] = event.saved
    else:
        if victim_id is not None and event.drowned is not None:
            out.results[victim_id] = event.drowned
        for i in pullers:
            if event.strained is not None:
                out.results[i] = event.strained
    return out


def scale(result: SceneResult) -> SceneResult:
    """Групповая надбавка к награде: опыт, трофеи и золото."""
    return result.model_copy(update={
        "reward": result.reward * GROUP_REWARD_MULT,
        "xp": result.xp * GROUP_REWARD_MULT,
        "gold": result.gold * GROUP_REWARD_MULT,
    })
