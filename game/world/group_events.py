"""Групповые события исследования: чистая логика без БД.

Групповое исследование раньше всегда заканчивалось боем. Теперь часть
бросков - событие, где решают все сразу: каждый выбирает в своём диалоге,
по таймеру выборы раскрываются, и исход зависит от того, что выбрала
группа целиком. Такого в соло нет и быть не может.

Механики (поле mechanic в content/events/group_scenes.json):
- split     - делёж находки: поровну или забрать себе;
- vote      - тайное голосование у развилки; ничья - решает лидер группы;
- roles     - каждому роль, каждой роли нужно хватить людей;
- rescue    - тонет один, остальные тянут или уходят со своим;
- volunteer - алтарь требует крови: вызвавшиеся делят цену, иначе берёт сам;
- circle    - камни на всех, каждый должен встать на свой;
- pot       - общий котёл костей: чем больше поставивших, тем лучше шанс;
- branches  - группа делится на ветки, лучшая награда - когда справились все;
- nest      - гнездо в несколько заходов, тревога растёт от числа лезущих;
- siege     - осада в несколько этапов голосованием, трофей растёт.

nest и siege идут в несколько раундов: resolve получает и возвращает
state, а Outcome.next_round говорит, что событие продолжается.

Награды - в «мобах», как у соло-событий (game/world/scene_events.py), и
дополнительно умножаются на GROUP_REWARD_MULT: игра в группе обязана быть
выгоднее одиночной. Котёл костей не умножается - иначе ставка стала бы
беспроигрышной. Смертей нет: худшее - разорение, как в соло.

Запись в БД - services/scene_event_service.apply_result, показ и таймер -
bot/handlers/group_events.py.
"""

import math
import random
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel, Field

from game.content_loader import CONTENT_DIR, _load_json_dict
from game.world import scene_events as se
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
VOLUNTEER, SILENT = "volunteer", "silent"
NEST_CLIMB, NEST_LEAVE = "climb", "leave"
NO_STAKE = "0"


class Option(BaseModel):
    """Вариант голосования: подпись и исходы, один из которых выпадет."""

    label: str
    outcomes: list[SceneResult]


class Role(BaseModel):
    id: str
    label: str
    #: Сколько людей нужно: число (0 - роль необязательная) или "half".
    need: int | str = 1
    #: Что будет со всеми, если на роль не хватило людей.
    shortfall: SceneResult | None = None
    #: Добавка тем, кто взял роль, если всё удалось.
    bonus: SceneResult | None = None


class Stake(BaseModel):
    id: str
    label: str
    gold: float = 0.0                 # в «мобах» золота


class Branch(BaseModel):
    id: str
    label: str
    chance: float = 0.5               # с одним человеком в ветке
    per_member: float = 0.15          # прибавка за каждого следующего
    success: SceneResult
    failure: SceneResult


class SiegeOption(BaseModel):
    id: str
    label: str
    retreat: bool = False
    risk: float = 0.0
    gain: float = 0.0                 # прибавка к общему трофею, в мобах
    fail: SceneResult | None = None


class SiegeStage(BaseModel):
    text: str
    options: list[SiegeOption]


class GroupEvent(BaseModel):
    id: str
    title: str
    mechanic: str
    text: str
    weight: float = 1.0
    rings: list[int] | None = None
    regions: list[str] | None = None
    image: str | None = None
    min_members: int = 2

    # split
    share_label: str = "Поровну"
    take_label: str = "Забрать себе"
    all_share: SceneResult | None = None
    taker: SceneResult | None = None
    robbed: SceneResult | None = None
    greedy: SceneResult | None = None

    # vote
    options: list[Option] = Field(default_factory=list)

    # roles
    roles: list[Role] = Field(default_factory=list)
    success: SceneResult | None = None
    #: вместо одного success - взвешенные исходы удачи
    success_outcomes: list[SceneResult] = Field(default_factory=list)

    # rescue
    victim_text: str = ""
    pull_label: str = "Тянуть"
    leave_label: str = "Уйти со своим"
    pull_need: int | str = "half"
    saved: SceneResult | None = None
    left: SceneResult | None = None
    drowned: SceneResult | None = None
    strained: SceneResult | None = None

    # volunteer
    volunteer_label: str = "Вызваться"
    silent_label: str = "Промолчать"
    toll_pct: float = 40.0            # % макс. HP, делится между вызвавшимися
    toll_min: float = 10.0
    volunteer_text: str = ""
    blessing: SceneResult | None = None
    taken_text: str = ""

    # circle
    stones: list[str] = Field(default_factory=list)
    lit_all: SceneResult | None = None
    lit_partial: SceneResult | None = None
    dark: SceneResult | None = None

    # pot
    stakes: list[Stake] = Field(default_factory=list)
    pot_chance: float = 0.38
    pot_per_staker: float = 0.05
    pot_max: float = 0.60
    win_text: str = ""
    lose_text: str = ""

    # branches
    branches: list[Branch] = Field(default_factory=list)
    joint: SceneResult | None = None

    # nest
    climb_label: str = "Лезть выше"
    nest_leave_label: str = "Уйти с добычей"
    step_reward: float = 0.6
    risk_base: float = 0.10
    risk_per_climber: float = 0.08
    risk_per_round: float = 0.05
    max_rounds: int = 5
    round_text: str = ""
    cash_text: str = ""
    fail_text: str = ""

    # siege
    stages: list[SiegeStage] = Field(default_factory=list)
    final: SceneResult | None = None
    retreat_text: str = ""


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
    return max(0, int(need))


def initial_state(event: GroupEvent, member_ids: list[int]) -> dict:
    if event.mechanic == "nest":
        return {"round": 1, "bank": {cid: 0.0 for cid in member_ids}, "active": list(member_ids)}
    if event.mechanic == "siege":
        return {"stage": 0, "bank": 0.0}
    return {}


def choices_of(event: GroupEvent, member_id: int, victim_id: int | None,
               state: dict | None = None, members: int = 0) -> list[tuple[str, str]]:
    """[(значение, подпись)] - кнопки участника в текущем раунде."""
    state = state or {}
    mech = event.mechanic
    if mech == "split":
        return [(SPLIT_SHARE, event.share_label), (SPLIT_TAKE, event.take_label)]
    if mech == "vote":
        return [(str(i), o.label) for i, o in enumerate(event.options)]
    if mech == "roles":
        return [(r.id, r.label) for r in event.roles]
    if mech == "rescue":
        if member_id == victim_id:
            return []
        return [(RESCUE_PULL, event.pull_label), (RESCUE_LEAVE, event.leave_label)]
    if mech == "volunteer":
        return [(VOLUNTEER, event.volunteer_label), (SILENT, event.silent_label)]
    if mech == "circle":
        count = max(members, 1)
        return [(str(i), label) for i, label in enumerate(event.stones[:count])]
    if mech == "pot":
        return [(s.id, s.label) for s in event.stakes]
    if mech == "branches":
        return [(b.id, b.label) for b in event.branches]
    if mech == "nest":
        if member_id not in state.get("active", []):
            return []
        return [(NEST_CLIMB, event.climb_label), (NEST_LEAVE, event.nest_leave_label)]
    if mech == "siege":
        stage = event.stages[state.get("stage", 0)]
        return [(o.id, o.label) for o in stage.options]
    return []


def default_choice(event: GroupEvent) -> str | None:
    """Что «выбрал» тот, кто не успел. Промолчавший в делёже не жадничает,
    в котле не ставит, в гнезде уходит со своим; в остальных механиках он
    просто не участвует."""
    return {
        "split": SPLIT_SHARE, "volunteer": SILENT, "pot": NO_STAKE, "nest": NEST_LEAVE,
    }.get(event.mechanic)


def round_prompt(event: GroupEvent, state: dict) -> str:
    """Текст следующего раунда многоходового события."""
    if event.mechanic == "nest":
        return event.round_text.format(round=state["round"], rounds=event.max_rounds)
    if event.mechanic == "siege":
        stage = event.stages[state["stage"]]
        taken = "Добыча пока не взята." if state["bank"] <= 0 else "Добыча растёт с каждым ярусом."
        return f"{stage.text}\n\n{taken}"
    return event.text


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
    #: событие продолжается следующим раундом с участниками active
    next_round: bool = False
    active: list[int] = field(default_factory=list)
    state: dict = field(default_factory=dict)
    #: применять ли групповую надбавку к наградам (у котла - нет)
    scaled: bool = True
    #: котёл: сколько «мобов» золота списать с каждого до раздачи
    charges: dict[int, float] = field(default_factory=dict)


def resolve(
    event: GroupEvent, members: dict[int, str], choices: dict[int, str | None],
    rng: random.Random, leader_id: int | None = None, victim_id: int | None = None,
    state: dict | None = None,
) -> Outcome:
    """members - {id: имя} участников раунда; choices - {id: выбор или None}."""
    resolver = {
        "split": _resolve_split, "vote": _resolve_vote, "roles": _resolve_roles,
        "rescue": _resolve_rescue, "volunteer": _resolve_volunteer, "circle": _resolve_circle,
        "pot": _resolve_pot, "branches": _resolve_branches, "nest": _resolve_nest,
        "siege": _resolve_siege,
    }[event.mechanic]
    return resolver(event, members, choices, rng, leader_id, victim_id, dict(state or {}))


def _names(members: dict[int, str], ids) -> str:
    ids = list(ids)
    if not ids:
        return "никто"
    return ", ".join(members[i] for i in sorted(ids, key=lambda i: members[i]))


def merge(a: SceneResult | None, b: SceneResult | None) -> SceneResult | None:
    """Два исхода одному участнику: награды складываются, тексты - подряд."""
    if a is None or b is None:
        return a or b
    return SceneResult(
        text="\n".join(t for t in (a.text, b.text) if t),
        reward=a.reward + b.reward, xp=a.xp + b.xp, gold=a.gold + b.gold,
        elixir=a.elixir or b.elixir, item=a.item or b.item, ore=a.ore + b.ore,
        damage=a.damage or b.damage, ruin=a.ruin or b.ruin, combat=a.combat or b.combat,
        effect=a.effect or b.effect, trail=a.trail or b.trail,
    )


def _pick(rng: random.Random, outcomes: list[SceneResult]) -> SceneResult:
    return rng.choices(outcomes, weights=[o.weight for o in outcomes])[0]


def _tally(options_count: int, members, choices, leader_id, rng, out: Outcome) -> tuple[int, list[int]]:
    """Тайное голосование: индекс победившего варианта. Ничья - лидер, иначе случай."""
    counts = [0] * options_count
    for i in members:
        value = choices.get(i)
        if value is not None and value.isdigit() and int(value) < options_count:
            counts[int(value)] += 1
    top = max(counts)
    leaders = [k for k, n in enumerate(counts) if n == top]
    if len(leaders) == 1:
        return leaders[0], counts
    leader_vote = choices.get(leader_id) if leader_id is not None else None
    if leader_vote is not None and leader_vote.isdigit() and int(leader_vote) in leaders:
        out.summary.append("Голоса разделились - решает лидер.")
        return int(leader_vote), counts
    out.summary.append("Голоса разделились - решает случай.")
    return rng.choice(leaders), counts


def _resolve_split(event, members, choices, rng, leader_id, victim_id, state) -> Outcome:
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


def _resolve_vote(event, members, choices, rng, leader_id, victim_id, state) -> Outcome:
    out = Outcome()
    winner, counts = _tally(len(event.options), members, choices, leader_id, rng, out)
    # Голосование тайное: видно, сколько за что, но не кто.
    out.summary.insert(0, "🗳 " + " · ".join(
        f"{o.label}: {n}" for o, n in zip(event.options, counts, strict=True)
    ))
    option = event.options[winner]
    result = _pick(rng, option.outcomes)
    out.summary.append(f"Группа выбирает: {option.label}.")
    out.results = {i: result for i in members}
    out.combat = result.combat is not None
    return out


def _resolve_roles(event, members, choices, rng, leader_id, victim_id, state) -> Outcome:
    people = len(members)
    out = Outcome()
    short = None
    for role in event.roles:
        taken = [i for i in members if choices.get(i) == role.id]
        need = need_count(role.need, people)
        if need:
            mark = "✅" if len(taken) >= need else "❌"
            out.summary.append(f"{mark} {role.label} ({len(taken)}/{need}): {_names(members, taken)}")
        else:
            out.summary.append(f"▫️ {role.label}: {_names(members, taken)}")
        if len(taken) < need and short is None:
            short = role
    if short is not None:
        result = short.shortfall
        out.results = {i: result for i in members} if result is not None else {}
        out.combat = result is not None and result.combat is not None
        return out
    result = _pick(rng, event.success_outcomes) if event.success_outcomes else event.success
    for i in members:
        role = next((r for r in event.roles if r.id == choices.get(i)), None)
        personal = merge(result, role.bonus if role is not None and not (result and result.combat) else None)
        if personal is not None:
            out.results[i] = personal
    out.combat = result is not None and result.combat is not None
    return out


def _resolve_rescue(event, members, choices, rng, leader_id, victim_id, state) -> Outcome:
    others = [i for i in members if i != victim_id]
    pullers = [i for i in others if choices.get(i) == RESCUE_PULL]
    leavers = [i for i in others if i not in pullers]
    need = need_count(event.pull_need, len(others))
    out = Outcome()
    out.summary.append(f"🪢 Тянули ({len(pullers)}/{need}): {_names(members, pullers)}")
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


def _resolve_volunteer(event, members, choices, rng, leader_id, victim_id, state) -> Outcome:
    volunteers = [i for i in members if choices.get(i) == VOLUNTEER]
    out = Outcome()
    if volunteers:
        # Цена одна на всех вызвавшихся: чем больше рук, тем меньше с каждого.
        pct = max(event.toll_min, event.toll_pct / len(volunteers))
        out.summary.append(f"🩸 Вызвались: {_names(members, volunteers)} (по {round(pct)}% здоровья)")
        paid = SceneResult(text=event.volunteer_text, damage=[pct, pct])
        for i in members:
            out.results[i] = merge(paid, event.blessing) if i in volunteers else event.blessing
        out.results = {i: r for i, r in out.results.items() if r is not None}
        return out
    chosen = rng.choice(sorted(members))
    pct = min(event.toll_pct * 2, 80.0)
    out.summary.append(f"Никто не вызвался. Алтарь выбирает сам: {members[chosen]}.")
    out.results[chosen] = SceneResult(text=event.taken_text, damage=[pct, pct])
    return out


def _resolve_circle(event, members, choices, rng, leader_id, victim_id, state) -> Outcome:
    stones = event.stones[:len(members)]
    on_stone: dict[int, list[int]] = {k: [] for k in range(len(stones))}
    for i in members:
        value = choices.get(i)
        if value is not None and value.isdigit() and int(value) in on_stone:
            on_stone[int(value)].append(i)
    out = Outcome()
    lit_people: set[int] = set()
    for k, label in enumerate(stones):
        people = on_stone[k]
        if len(people) == 1:
            state_word = "горит"
            lit_people.update(people)
        elif people:
            state_word = "погас"
        else:
            state_word = "пуст"
        out.summary.append(f"{label}: {_names(members, people)} - {state_word}")
    if len(lit_people) == len(members):
        out.summary.append("Круг замкнулся.")
        out.results = {i: event.lit_all for i in members if event.lit_all is not None}
        return out
    out.summary.append("Круг не замкнулся.")
    for i in members:
        result = event.lit_partial if i in lit_people else event.dark
        if result is not None:
            out.results[i] = result
    return out


def _resolve_pot(event, members, choices, rng, leader_id, victim_id, state) -> Outcome:
    stakes = {s.id: s for s in event.stakes}
    out = Outcome(scaled=False)
    stakers = {i: stakes[choices[i]] for i in members
               if choices.get(i) in stakes and stakes[choices[i]].gold > 0}
    chance = min(event.pot_max, event.pot_chance + event.pot_per_staker * len(stakers))
    for i, stake in stakers.items():
        out.charges[i] = stake.gold
    if stakers:
        out.summary.append("💰 В котле: " + ", ".join(
            f"{members[i]} - {stakers[i].label}" for i in sorted(stakers, key=lambda i: members[i])
        ))
    else:
        out.summary.append("Котёл пуст - никто не поставил.")
        return out
    won, mine, theirs = se.roll_dice(rng, chance)
    out.summary.append(
        f"🎲 Шанс {round(chance * 100)}%. Вы: {mine[0]} и {mine[1]}, кости: {theirs[0]} и {theirs[1]}."
    )
    for i, stake in stakers.items():
        out.results[i] = (
            SceneResult(text=event.win_text, gold=stake.gold * 2) if won
            else SceneResult(text=event.lose_text)
        )
    return out


def _resolve_branches(event, members, choices, rng, leader_id, victim_id, state) -> Outcome:
    out = Outcome()
    all_ok = True
    took_part: list[int] = []
    for branch in event.branches:
        people = [i for i in members if choices.get(i) == branch.id]
        if not people:
            all_ok = False
            out.summary.append(f"{branch.label}: никто")
            continue
        took_part += people
        chance = min(0.95, branch.chance + branch.per_member * (len(people) - 1))
        ok = rng.random() < chance
        all_ok = all_ok and ok
        out.summary.append(f"{branch.label}: {_names(members, people)} - {'удалось' if ok else 'не вышло'}")
        for i in people:
            out.results[i] = branch.success if ok else branch.failure
    if all_ok and event.joint is not None:
        out.summary.append("Обе ветки сошлись.")
        for i in took_part:
            out.results[i] = merge(out.results.get(i), event.joint)
    out.combat = any(r.combat for r in out.results.values() if r is not None)
    return out


def _resolve_nest(event, members, choices, rng, leader_id, victim_id, state) -> Outcome:
    bank = dict(state["bank"])
    active = [i for i in state["active"] if i in members]
    round_no = state["round"]
    climbers = [i for i in active if choices.get(i) == NEST_CLIMB]
    leavers = [i for i in active if i not in climbers]
    out = Outcome()
    if climbers:
        out.summary.append(f"🧗 Полезли: {_names(members, climbers)}")
    if leavers:
        out.summary.append(f"🚶 Ушли с добычей: {_names(members, leavers)}")
    for i in leavers:
        out.results[i] = SceneResult(text=event.cash_text, reward=bank.get(i, 0.0))
    if not climbers:
        return out
    # Тревога растёт от числа лезущих, а не от одного игрока: жадность
    # группы делится на всех, кто полез.
    risk = event.risk_base + event.risk_per_climber * len(climbers) + event.risk_per_round * (round_no - 1)
    risk = min(risk, 0.9)
    if rng.random() < risk:
        out.summary.append(f"🔔 Тревога ({round(risk * 100)}%): гнездо проснулось.")
        if round_no >= 4:
            failed = SceneResult(text=event.fail_text, ruin=True)
        elif round_no >= 2:
            failed = SceneResult(text=event.fail_text, damage=[15, 25])
        else:
            failed = SceneResult(text=event.fail_text, damage=[5, 10])
        for i in climbers:
            out.results[i] = failed
        return out
    out.summary.append(f"Тихо. Тревога была {round(risk * 100)}%.")
    for i in climbers:
        bank[i] = bank.get(i, 0.0) + event.step_reward
    if round_no >= event.max_rounds:
        out.summary.append("Глубже лезть некуда.")
        for i in climbers:
            out.results[i] = SceneResult(text=event.cash_text, reward=bank[i])
        return out
    out.next_round = True
    out.active = climbers
    out.state = {"round": round_no + 1, "bank": bank, "active": climbers}
    return out


def _resolve_siege(event, members, choices, rng, leader_id, victim_id, state) -> Outcome:
    stage_no = state["stage"]
    bank = state["bank"]
    stage = event.stages[stage_no]
    out = Outcome()
    winner, counts = _tally(len(stage.options), members,
                            {i: _option_index(stage, choices.get(i)) for i in members}, leader_id, rng, out)
    out.summary.insert(0, "🗳 " + " · ".join(
        f"{o.label}: {n}" for o, n in zip(stage.options, counts, strict=True)
    ))
    option = stage.options[winner]
    out.summary.append(f"Группа выбирает: {option.label}.")
    if option.retreat:
        cash = SceneResult(text=event.retreat_text, reward=bank) if bank > 0 else SceneResult(text=event.retreat_text)
        out.results = {i: cash for i in members}
        return out
    if rng.random() < option.risk:
        kept = bank * 0.5
        out.summary.append("Не вышло.")
        fail = merge(option.fail, SceneResult(reward=kept) if kept > 0 else None) or SceneResult()
        out.results = {i: fail for i in members}
        out.combat = fail.combat is not None
        return out
    bank += option.gain
    stage_no += 1
    if stage_no >= len(event.stages):
        out.summary.append("Башня взята.")
        win = merge(event.final, SceneResult(reward=bank))
        out.results = {i: win for i in members}
        return out
    out.summary.append("Удалось.")
    out.next_round = True
    out.active = list(members)
    out.state = {"stage": stage_no, "bank": bank}
    return out


def _option_index(stage: SiegeStage, value: str | None) -> str | None:
    for k, o in enumerate(stage.options):
        if o.id == value:
            return str(k)
    return None


def scale(result: SceneResult) -> SceneResult:
    """Групповая надбавка к награде: опыт, трофеи и золото."""
    return result.model_copy(update={
        "reward": result.reward * GROUP_REWARD_MULT,
        "xp": result.xp * GROUP_REWARD_MULT,
        "gold": result.gold * GROUP_REWARD_MULT,
    })
