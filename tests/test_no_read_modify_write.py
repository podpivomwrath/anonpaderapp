"""Списания не должны читать число в питон и писать обратно (патч 94).

Вебхук запускает каждое событие отдельной задачей, так что два быстрых
нажатия идут одновременно. Схема «прочитать -> уменьшить -> заплатить»
между чтением и записью отдаёт управление, и оба нажатия видят одно и то же
число. На боевом Postgres до исправления это давало:

  - трофеи: 10 штук за 20 золота приносили 80-120;
  - предмет: один и тот же продан 10 раз из 10;
  - садок: 44 золота превращались в 440;
  - эликсир: одну склянку выпивали дважды.

Кошелёк и руду от этого вылечили раньше (атомарный UPDATE с порогом), а
продажи и эликсиры остались. Настоящая гонка проверяется в
tests/test_postgres_concurrency.py, но тот стенд требует локальный Postgres и
обычно пропускается. Эта проверка работает везде и следит за тем, чтобы
защита не пропала при следующей правке.

Проверяется МЕХАНИЗМ в теле функции без комментариев - не слова рядом с ним:
в этом проекте тесты уже трижды ловили объяснение вместо правила.
"""

import ast
import inspect
import textwrap

import pytest

from services import elixir_service, fishing_service, item_service, promo_service, trophy_service


def _code(func) -> str:
    """Тело функции без комментариев и докстрингов."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(func)))
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if (
            isinstance(body, list) and body
            and isinstance(body[0], ast.Expr)
            and isinstance(getattr(body[0], "value", None), ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            body.pop(0)
    return ast.unparse(tree)


@pytest.mark.parametrize(
    ("func", "mechanism", "why"),
    [
        (trophy_service._lock_rows, "with_for_update",
         "строки трофеев без блокировки - два нажатия продадут один стак дважды"),
        (fishing_service.sell_bag, "with_for_update",
         "садок без блокировки - два нажатия продадут одну рыбу дважды"),
        (item_service.sell_item, "rowcount",
         "золото платится, не проверив, что предмет действительно забран"),
        (elixir_service.consume, "rowcount",
         "склянка списывается в питоне - последнюю можно выпить дважды"),
        (promo_service.activate_code, "with_for_update",
         "промокод без блокировки - лимит 3 давал 10 активаций из 10"),
    ],
)
def test_consumption_is_atomic(func, mechanism, why) -> None:
    assert mechanism in _code(func), why


def test_trophy_sales_go_through_the_lock() -> None:
    """Блокировка есть, но продажа могла бы читать мимо неё - как раньше,
    через get_stock. Тогда защита стояла бы, а гонка оставалась."""
    for func in (trophy_service.sell_all, trophy_service.sell_one, trophy_service.transfer_all):
        code = _code(func)
        assert "_lock_rows" in code, f"{func.__name__} читает трофеи мимо блокировки"
        assert "get_stock" not in code, f"{func.__name__} снова читает стак без блокировки"


def test_elixir_is_not_decremented_in_python() -> None:
    assert "count -= 1" not in _code(elixir_service.consume)


def test_wallet_is_changed_only_through_wallet_service() -> None:
    """Баланс меняется ТОЛЬКО атомарными операциями wallet_service (патч 96).

    Прямая правка `wallet.farm_currency -= cost` читает баланс в питон и
    пишет обратно целым числом. Два одновременных изменения тогда теряют
    одно из них, а проверка «хватает ли» проходит у обоих. Так были
    устроены ставки PvP и биржа золото-самоцветы - первая молча съедала
    продажу, совпавшую с концом дуэли, вторая дала бы дюп самоцветов в день
    подключения.
    """
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    pattern = re.compile(r"\.(farm_currency|donate_currency)\s*(\+=|-=|\*=)")
    offenders = []
    for folder in ("services", "game", "bot"):
        for path in (root / folder).rglob("*.py"):
            if path.name == "wallet_service.py":
                continue
            code = re.sub(r"#[^\n]*", "", path.read_text(encoding="utf-8"))
            for number, line in enumerate(code.split("\n"), 1):
                if pattern.search(line):
                    offenders.append(f"{path.relative_to(root)}:{number} {line.strip()}")
    assert not offenders, "баланс правится мимо wallet_service:\n" + "\n".join(offenders)
