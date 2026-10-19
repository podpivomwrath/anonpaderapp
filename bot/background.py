"""Фоновые задачи «запустил и забыл» (2026-10-19, аудит).

asyncio держит запущенную задачу только СЛАБОЙ ссылкой: если на неё больше
никто не ссылается, сборщик мусора может прибить её посреди работы - без
ошибки и без следа в логах (уведомление о левелапе, автопропуск хода и т.п.
молча не случались бы). Здесь задачи живут в множестве, пока не закончатся,
а упавшая пишет в лог, а не теряет исключение.
"""

import asyncio
from collections.abc import Coroutine

from loguru import logger

_tasks: set[asyncio.Task] = set()


def spawn(coro: Coroutine, name: str | None = None) -> asyncio.Task:
    task = asyncio.get_running_loop().create_task(coro, name=name)
    _tasks.add(task)
    task.add_done_callback(_done)
    return task


def _done(task: asyncio.Task) -> None:
    _tasks.discard(task)
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        logger.opt(exception=exc).error("Фоновая задача {} упала", task.get_name())
