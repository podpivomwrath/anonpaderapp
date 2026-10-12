"""/баг принимает скриншоты, картинки и видео (2026-10-12): сообщение с
вложением пересылается администратору, след вложений - в снимке репорта."""

from types import SimpleNamespace as NS

from bot.handlers import moderation


def _message(*attachments):
    return NS(attachments=list(attachments))


def test_photo_takes_largest_size_and_video_keeps_id() -> None:
    photo = NS(type="photo", photo=NS(sizes=[
        NS(width=130, height=90, url="small"), NS(width=1280, height=960, url="big"),
    ]))
    video = NS(type="video", video=NS(owner_id=5, id=77))
    doc = NS(type="doc", doc=NS(url="file", title="log.txt"))
    summary = moderation._attachments_summary(_message(photo, video, doc))
    assert summary == [
        {"type": "photo", "url": "big"},
        {"type": "video", "id": "video5_77"},
        {"type": "doc", "url": "file", "title": "log.txt"},
    ]


def test_no_attachments_is_empty() -> None:
    assert moderation._attachments_summary(_message()) == []
    assert moderation._attachments_summary(NS(attachments=None)) == []


def test_ask_text_mentions_attachments() -> None:
    assert "Скриншот" in moderation.BUG_ASK_TEXT
