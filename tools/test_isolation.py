"""Скрытые зависимости тестов (2026-10-21): каждый файл тестов - отдельным
запуском, в случайном порядке файлов. Тест, который проходит только в общем
прогоне, молча опирается на чужие импорты или состояние - так тест блока в
дуэли зависел от того, что подклассы зарегистрировал кто-то до него.

Запуск: python tools/test_isolation.py [-j 6]
"""

from __future__ import annotations

import argparse
import random
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(path: Path) -> tuple[Path, int, str]:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(path)],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    return path, proc.returncode, proc.stdout[-1500:]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("-j", type=int, default=6)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--whole", action="store_true", help="один общий прогон в перемешанном порядке файлов")
    args = parser.parse_args()
    files = sorted((ROOT / "tests").glob("test_*.py"))
    seed = args.seed if args.seed is not None else random.randrange(10**6)
    random.Random(seed).shuffle(files)
    if args.whole:
        # Утечки состояния МЕЖДУ тестами: чужой тест оставил след - этот падает.
        print(f"общий прогон, порядок файлов: seed {seed}", flush=True)
        proc = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *map(str, files)],
                              cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
        print(proc.stdout[-3000:])
        return proc.returncode
    print(f"файлов: {len(files)}, порядок: seed {seed}", flush=True)
    bad = []
    with ThreadPoolExecutor(args.j) as pool:
        for path, code, out in pool.map(run, files):
            if code not in (0, 5):  # 5 - в файле нет тестов
                bad.append(path.name)
                print(f"\n=== {path.name} (код {code})\n{out}", flush=True)
    print(f"\nитого: {len(bad)} файл(ов) падают поодиночке: {', '.join(bad) or '-'}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
