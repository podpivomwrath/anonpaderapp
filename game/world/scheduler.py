"""Обобщённый планировщик отложенных событий на игрока (peer_id).

Используется и для прибытия после перемещения, и для завершения
исследования клетки — оба через APScheduler + async-колбэк (тот же паттерн,
что в боевых движках). Один peer_id = максимум один отложенный job на префикс.
"""

from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger

PeerCallback = Callable[[int], Awaitable[None]]


class PeerScheduler:
    def __init__(
        self,
        callback: PeerCallback,
        job_prefix: str,
        scheduler: AsyncIOScheduler | None = None,
    ) -> None:
        self.callback = callback
        self.job_prefix = job_prefix
        self.scheduler = scheduler or AsyncIOScheduler()

    def start(self) -> None:
        if not self.scheduler.running:
            self.scheduler.start()

    def shutdown(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

    def _job_id(self, peer_id: int) -> str:
        return f"{self.job_prefix}:{peer_id}"

    def schedule(self, peer_id: int, delay_seconds: float) -> None:
        run_at = datetime.now(timezone.utc) + timedelta(seconds=delay_seconds)
        self.scheduler.add_job(
            self.callback,
            trigger=DateTrigger(run_date=run_at),
            args=[peer_id],
            id=self._job_id(peer_id),
            replace_existing=True,
            misfire_grace_time=30,
        )

    def cancel(self, peer_id: int) -> None:
        try:
            self.scheduler.remove_job(self._job_id(peer_id))
        except Exception:
            pass
