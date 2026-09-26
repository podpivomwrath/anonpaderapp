"""Загрузка картинок игры в альбом группы ВК (патч 100).

Запуск на сервере, внутри контейнера бота:

    python tools/vk_upload.py --check                 проверить токен
    python tools/vk_upload.py картинка1.jpg ...       залить, напечатать номера

Печатает JSON {имя файла: номер фото}. Номера того же вида, что у картинок,
залитых в альбом руками: photo-<группа>_<номер> (bot/vk_media.py).

Грузит ТОКЕНОМ ПОЛЬЗОВАТЕЛЯ (VK_USER_TOKEN), а не токеном бота. Проверено на
проде: токену сообщества VK не даёт ни грузить в альбом, ни даже читать его
(ошибка 27), а фото «для сообщений» ложатся на личный аккаунт админа, а не на
группу - по номеру группы игра их не нашла бы, и ВК отклонил бы сообщение
целиком.

Альбом берётся тот же, где уже лежат картинки игры: по фото-образцу (пролог
рейда). Так новые картинки не заводят в группе отдельный альбом.

Ужимать заранее, локально (в образе бота нет Pillow):
    python tools/vk_upload.py --prepare img/*.png
кладёт рядом JPEG до 1600 пикселей - оригиналы весят по 2-3 МБ, а ВК всё
равно пережмёт их сам.
"""

import asyncio
import io
import json
import sys
from pathlib import Path

import aiohttp

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import get_settings

API = "https://api.vk.com/method/"
VERSION = "5.199"
MAX_SIDE = 1600
#: Фото игры, по которому находится её альбом (пролог рейда).
REFERENCE_PHOTO_ID = "457239133"
#: Попыток на одну картинку - каждая с новым сервером загрузки.
ATTEMPTS = 6


class VkError(RuntimeError):
    pass


async def _call(session: aiohttp.ClientSession, token: str, method: str, **params):
    params.update(access_token=token, v=VERSION)
    async with session.post(API + method, data=params) as response:
        body = await response.json(content_type=None)
    if "error" in body:
        raise VkError(f"{method}: {body['error'].get('error_msg')}")
    return body["response"]


def _jpeg(path: Path) -> bytes:
    """JPEG до MAX_SIDE. Без Pillow - файл как есть (уже ужатый заранее)."""
    try:
        from PIL import Image
    except ImportError:
        return path.read_bytes()
    with Image.open(path) as image:
        image = image.convert("RGB")
        image.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)
        buffer = io.BytesIO()
        image.save(buffer, "JPEG", quality=90, optimize=True)
        return buffer.getvalue()


def prepare(paths: list[Path]) -> list[Path]:
    out = []
    for path in paths:
        target = path.with_suffix(".jpg")
        target.write_bytes(_jpeg(path))
        out.append(target)
    return out


async def check_token(session: aiohttp.ClientSession, token: str, group_id: int) -> str:
    """Кому принадлежит токен и может ли он грузить в группу. Сам токен не
    печатается никогда."""
    (user,) = await _call(session, token, "users.get")
    groups = await _call(session, token, "groups.get", filter="admin,editor", count=1000)
    if group_id not in groups.get("items", []):
        raise VkError(
            f"токен принадлежит {user['first_name']} {user['last_name']}, "
            f"но этот аккаунт не админ и не редактор группы {group_id}"
        )
    return f"{user['first_name']} {user['last_name']} (id {user['id']})"


async def game_album(session: aiohttp.ClientSession, token: str, group_id: int) -> int:
    (photo,) = await _call(
        session, token, "photos.getById", photos=f"-{group_id}_{REFERENCE_PHOTO_ID}"
    )
    return photo["album_id"]


async def upload_one(
    session: aiohttp.ClientSession, token: str, group_id: int, album_id: int, path: Path,
) -> dict:
    """Одна картинка в альбом группы.

    По одной, хотя документация ВК описывает до пяти файлов за запрос:
    поштучно номер фото однозначно привязан к своему файлу, без расчёта на
    порядок в пачке.

    Имя файла в запросе латиницей: кириллическое уходит в заголовок в
    кодировке RFC 2231, и полагаться на её разбор незачем - имя ВК не нужно.
    """
    uploaded = None
    # Сервер загрузки ВК выдаётся наугад и через раз отвечает пустым
    # photos_list, ничего не объясняя. На проде поле `file` на одних серверах
    # прошло, на других нет; `file1` из документации тоже давал пустой ответ.
    # Поэтому - повтор с НОВЫМ сервером, чередуя оба имени поля. Пустой ответ
    # ничего не сохраняет (сохраняет только photos.save ниже), так что повтор
    # безопасен и дублей в альбоме не даёт.
    for attempt in range(ATTEMPTS):
        server = await _call(
            session, token, "photos.getUploadServer", album_id=album_id, group_id=group_id
        )
        field = ("file", "file1")[attempt % 2]
        form = aiohttp.FormData()
        form.add_field(field, _jpeg(path), filename="image.jpg", content_type="image/jpeg")
        async with session.post(server["upload_url"], data=form) as response:
            answer = await response.json(content_type=None)
        if answer.get("photos_list") and answer["photos_list"] != "[]":
            uploaded = answer
            break
        await asyncio.sleep(1)
    if uploaded is None:
        raise VkError(f"{path.name}: сервер загрузки не принял файл за {ATTEMPTS} попыток")
    saved = await _call(
        session, token, "photos.save", album_id=album_id, group_id=group_id,
        server=uploaded["server"], photos_list=uploaded["photos_list"], hash=uploaded["hash"],
    )
    if len(saved) != 1:
        raise VkError(f"{path.name}: ожидалось одно фото, сохранено {len(saved)}")
    photo = saved[0]
    # Игра собирает вложение как фото ГРУППЫ. Чужое фото по этой строке не
    # найдётся, и ВК отклонит сообщение целиком.
    if photo["owner_id"] != -group_id:
        raise VkError(f"{path.name}: фото принадлежит {photo['owner_id']}, а не группе")
    return photo


async def main(paths: list[Path]) -> dict[str, int]:
    settings = get_settings()
    token = settings.vk_user_token
    if not token:
        raise SystemExit("VK_USER_TOKEN не задан в .env на сервере")
    group_id = int(settings.vk_group_id)
    result: dict[str, int] = {}
    async with aiohttp.ClientSession() as session:
        print("токен:", await check_token(session, token, group_id), file=sys.stderr)
        album_id = await game_album(session, token, group_id)
        print("альбом игры:", album_id, file=sys.stderr)
        for path in paths:
            photo = await upload_one(session, token, group_id, album_id, path)
            result[path.name] = photo["id"]
            print(f"  {path.name} -> {photo['id']}", file=sys.stderr)
    return result


async def _check() -> None:
    settings = get_settings()
    if not settings.vk_user_token:
        raise SystemExit("VK_USER_TOKEN не задан в .env на сервере")
    group_id = int(settings.vk_group_id)
    async with aiohttp.ClientSession() as session:
        print("токен:", await check_token(session, settings.vk_user_token, group_id))
        print("альбом игры:", await game_album(session, settings.vk_user_token, group_id))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    args = sys.argv[1:]
    if args[:1] == ["--prepare"]:
        for jpg in prepare([Path(p) for p in args[1:]]):
            print(jpg, jpg.stat().st_size // 1024, "КБ")
    elif args[:1] == ["--check"]:
        asyncio.run(_check())
    elif args:
        print(json.dumps(asyncio.run(main([Path(p) for p in args])), ensure_ascii=False, indent=2))
    else:
        raise SystemExit("укажи файлы картинок, --check или --prepare")
