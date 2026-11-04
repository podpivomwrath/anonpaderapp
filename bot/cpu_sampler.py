"""Профилировщик в процессе (2026-11-05, аудит нагрузки): py-spy в контейнер
без прав на ptrace не пускают, поэтому снимаем стеки сами.

Поток раз в INTERVAL секунд смотрит, какой код выполняет основной поток
(sys._current_frames), и считает самые глубокие кадры нашего кода. Ожидание
событий (selector.select) - простой, его не считаем. Работает DURATION секунд
через DELAY после старта, пишет в журнал TOP самых частых мест и выключается.
"""

import sys
import threading
import time
from collections import Counter

from loguru import logger

DELAY = 120
DURATION = 600
INTERVAL = 0.02
TOP = 25
_OURS = ("/app/bot/", "/app/game/", "/app/services/", "/app/models/", "/app/main.py")
_IDLE = ("select", "_run_once", "poll")


def _where(frame) -> str | None:
    """Цепочка из трёх наших кадров сверху стека: «файл:функция < ...»."""
    chain = []
    while frame is not None and len(chain) < 3:
        path = frame.f_code.co_filename.replace("\\", "/")
        if any(p in path for p in _OURS):
            chain.append(f"{path.rsplit('/', 1)[-1]}:{frame.f_code.co_name}")
        frame = frame.f_back
    return " < ".join(chain) if chain else None


def _run(main_id: int) -> None:
    time.sleep(DELAY)
    busy, idle, other = Counter(), 0, 0
    end = time.monotonic() + DURATION
    while time.monotonic() < end:
        frame = sys._current_frames().get(main_id)
        if frame is not None:
            if frame.f_code.co_name in _IDLE:
                idle += 1
            else:
                where = _where(frame)
                if where:
                    busy[where] += 1
                else:
                    # Только библиотеки (опрос VK, планировщик, aiohttp): кто именно.
                    other += 1
                    path = frame.f_code.co_filename.replace("\\", "/").rsplit("/", 2)
                    busy[f"[lib] {'/'.join(path[-2:])}:{frame.f_code.co_name}"] += 1
        time.sleep(INTERVAL)
    total = idle + sum(busy.values()) or 1
    ours = sum(busy.values()) - other
    lines = [(f"CPU-снимок за {DURATION} с: простой {100 * idle / total:.0f}%, "
              f"только библиотеки {100 * other / total:.0f}%, наш код {100 * ours / total:.0f}%")]
    lines += [f"  {100 * n / total:5.1f}%  {where}" for where, n in busy.most_common(TOP)]
    logger.info("\n".join(lines))


def start() -> None:
    threading.Thread(target=_run, args=(threading.main_thread().ident,), daemon=True, name="cpu_sampler").start()
