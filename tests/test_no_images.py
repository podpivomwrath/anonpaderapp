"""«Убрать картинки в игре»: фото вырезаются из отправки тем, кто их выключил."""

from bot import no_images


def setup_function():
    no_images._muted.clear()


def test_others_get_pictures():
    no_images.set_muted(1, True)
    data = {"peer_id": 2, "message": "привет", "attachment": "photo-1_2"}
    assert no_images.strip("messages.send", data) is data


def test_photo_removed_other_attachments_kept():
    no_images.set_muted(1, True)
    data = {"peer_id": 1, "message": "бой", "attachment": "photo-1_2,doc-1_3"}
    out = no_images.strip("messages.send", data)
    assert out["attachment"] == "doc-1_3"
    assert data["attachment"] == "photo-1_2,doc-1_3"  # исходные данные не трогаем


def test_edit_also_stripped():
    no_images.set_muted(1, True)
    out = no_images.strip("messages.edit", {"peer_id": 1, "message": "ход", "attachment": "photo-1_2"})
    assert out["attachment"] == ""


def test_picture_only_message_is_kept():
    """Без картинки сообщение пустое - VK его не примет, шлём как есть."""
    no_images.set_muted(1, True)
    data = {"peer_id": 1, "attachment": "photo-1_2"}
    assert no_images.strip("messages.send", data) is data


def test_group_send_stripped_only_if_all_muted():
    no_images.set_muted(1, True)
    data = {"peer_ids": "1,2", "message": "рейд", "attachment": "photo-1_2"}
    assert no_images.strip("messages.send", data) is data
    no_images.set_muted(2, True)
    assert no_images.strip("messages.send", data)["attachment"] == ""


def test_switch_off():
    no_images.set_muted(1, True)
    no_images.set_muted(1, False)
    data = {"peer_id": 1, "message": "x", "attachment": "photo-1_2"}
    assert no_images.strip("messages.send", data) is data
