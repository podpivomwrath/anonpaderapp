"""Удаление ОДНОГО персонажа целиком (игрок хочет пересоздать персонажа).

Основной путь - кнопка «Обнулить персонажа» в админ-панели мини-аппа. Скрипт -
запасной, из консоли сервера; логика общая: services/character_reset_service.py.

Запуск (по умолчанию - только сводка, ничего не меняется):
    python scripts/delete_character.py --name Кригер
    python scripts/delete_character.py --character-id 123

Само удаление:
    ALLOW_DELETE_CHARACTER=true python scripts/delete_character.py --name Кригер --yes
    (вместо ввода YES можно добавить --confirm-name Кригер)

Запись users (vk_id) остаётся: следующее сообщение игрока автоматически
запускает онбординг (bot/handlers/fallback.py), как после вайпа. Игрок на
момент удаления не должен быть в бою - бой живёт в памяти бота.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

try:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
except NameError:  # запуск через `python -` (скрипт из stdin): корень проекта - текущая папка
    pass

from services.character_reset_service import (  # noqa: E402,F401
    Ref,
    Summary,
    character_refs,
    find_by_name,
    purge,
    summarize,
)


def _print_summary(summary: Summary) -> None:
    print(f"Персонаж: {summary.name!r} (id={summary.character_id}, vk_id={summary.vk_id}, уровень {summary.level})")
    print(f"Кошелёк: золото {summary.farm_currency}, донат {summary.donate_currency}")
    print("Связанные строки:")
    for key, n in sorted(summary.counts.items()):
        print(f"  {key}: {n}")
    for warning in summary.warnings:
        print(f"! {warning}")


async def _run(args: argparse.Namespace) -> int:
    from services.db import dispose_engine, get_session_factory

    try:
        async with get_session_factory()() as db:
            if args.character_id is not None:
                ids = [args.character_id]
            else:
                found = await find_by_name(db, args.name)
                ids = [c.id for c in found]
                if len(found) != 1:
                    print(f"Нужен ровно один персонаж с именем {args.name!r}, найдено: {len(found)}")
                    for c in found:
                        print(f"  id={c.id}, имя={c.name!r}, уровень {c.level}, user_id={c.user_id}")
                    return 1
            summary = await summarize(db, ids[0])
            _print_summary(summary)
            if not args.yes:
                print("\nСухой прогон: ничего не изменено. Для удаления добавьте --yes.")
                return 0
            if os.environ.get("ALLOW_DELETE_CHARACTER") != "true":
                print("\nУдаление заблокировано: нет ALLOW_DELETE_CHARACTER=true в окружении.")
                return 1
            if args.confirm_name is not None:
                # Подтверждение аргументом (когда stdin занят, напр. при запуске
                # в контейнере): имя в аргументе обязано совпасть с найденным.
                if args.confirm_name.strip().casefold() != summary.name.strip().casefold():
                    print(f"Подтверждение не совпало: ожидалось имя {summary.name!r}.")
                    return 1
            elif input(
                f'\nУдалить {summary.name!r} без возможности восстановления? Введи "YES": '
            ).strip() != "YES":
                print("Отменено.")
                return 1
            removed = await purge(db, ids[0])
            await db.commit()
            print("Удалено:")
            for key, n in sorted(removed.items()):
                print(f"  {key}: {n}")
    finally:
        await dispose_engine()
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Удалить одного персонажа целиком.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--name", help="Точное имя персонажа (без учёта регистра)")
    group.add_argument("--character-id", type=int, help="id персонажа")
    parser.add_argument("--yes", action="store_true", help="Выполнить удаление (иначе только сводка)")
    parser.add_argument(
        "--confirm-name", default=None,
        help="Подтвердить удаление именем персонажа (вместо ввода YES в консоли)",
    )
    sys.exit(asyncio.run(_run(parser.parse_args())))


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()
    main()
