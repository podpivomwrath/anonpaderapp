"""Списание золота считает баланс в БД, а не в памяти процесса.

Вебхук обрабатывает каждое событие VK отдельной задачей, то есть два
нажатия «Купить» идут ПАРАЛЛЕЛЬНО, каждое в своей сессии. Пока charge читал
баланс в питон и писал обратно, оба обработчика видели 100, оба записывали
40, и игрок получал две покупки по цене одной.

Настоящую параллельность на SQLite не изобразить (см. комментарий в тесте
ниже), поэтому проверяем две вещи по отдельности: обычную арифметику
списания - поведением, и место принятия решения - структурно.
"""

import textwrap

import pytest

from services import wallet_service


def test_charge_decides_inside_one_update_not_in_python() -> None:
    """Проверка structural, и это осознанно.

    Настоящую гонку на SQLite не воспроизвести: попытка изобразить её даёт
    либо сериализацию (и тогда тест зелёный даже на СТАРОМ коде - проверено),
    либо «database is locked», что к делу не относится. Postgres здесь ведёт
    себя иначе, чем тестовая БД, поэтому проверяем не поведение под нагрузкой,
    а то единственное, от чего оно зависит: решение «хватает ли» обязано жить
    в SQL, рядом со списанием, а не в питоне между SELECT и COMMIT.
    """
    import ast
    import inspect

    source = inspect.getsource(wallet_service.charge)
    tree = ast.parse(textwrap.dedent(source))
    calls = [ast.unparse(n) for n in ast.walk(tree) if isinstance(n, ast.Call)]

    assert any("update(Wallet)" in c for c in calls), "списание должно идти через UPDATE"
    assert ">= amount" in ast.unparse(tree), "порог обязан быть условием того же UPDATE"
    assert "setattr" not in ast.unparse(tree), "присваивание в питоне возвращает гонку"
    assert "rowcount" in ast.unparse(tree), "решение принимается по результату UPDATE"


async def test_charge_leaves_exact_remainder(db_session, make_character) -> None:
    character = await make_character()
    await wallet_service.deposit(db_session, character.id, "farm", 100)
    wallet = await wallet_service.charge(db_session, character.id, "farm", 60)
    assert wallet.farm_currency == 40


async def test_charge_of_whole_balance_is_allowed(db_session, make_character) -> None:
    character = await make_character()
    await wallet_service.deposit(db_session, character.id, "farm", 100)
    wallet = await wallet_service.charge(db_session, character.id, "farm", 100)
    assert wallet.farm_currency == 0


async def test_charge_never_goes_negative(db_session, make_character) -> None:
    character = await make_character()
    await wallet_service.deposit(db_session, character.id, "farm", 30)
    with pytest.raises(wallet_service.NotEnoughCurrency):
        await wallet_service.charge(db_session, character.id, "farm", 31)
    wallet = await wallet_service.get_wallet(db_session, character.id)
    assert wallet.farm_currency == 30


async def test_deposit_accumulates(db_session, make_character) -> None:
    character = await make_character()
    for _ in range(5):
        await wallet_service.deposit(db_session, character.id, "farm", 7)
    wallet = await wallet_service.get_wallet(db_session, character.id)
    assert wallet.farm_currency == 35


async def test_donate_and_farm_do_not_mix(db_session, make_character) -> None:
    character = await make_character()
    await wallet_service.deposit(db_session, character.id, "donate", 50)
    with pytest.raises(wallet_service.NotEnoughCurrency):
        await wallet_service.charge(db_session, character.id, "farm", 1)
    wallet = await wallet_service.charge(db_session, character.id, "donate", 50)
    assert wallet.donate_currency == 0
    assert wallet.farm_currency == 0
