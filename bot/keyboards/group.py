"""Клавиатуры групп (патч 51, ч.2): приглашение (прямо в сообщении) и
подтверждение выхода."""

from vkbottle import Keyboard, KeyboardButtonColor, Text


def group_invite_keyboard(invite_id: int) -> str:
    kb = Keyboard(inline=True)
    kb.add(
        Text("Принять", payload={"type": "group_invite_accept", "invite_id": invite_id}),
        color=KeyboardButtonColor.POSITIVE,
    )
    kb.add(
        Text("Отклонить", payload={"type": "group_invite_decline", "invite_id": invite_id}),
        color=KeyboardButtonColor.NEGATIVE,
    )
    return kb.get_json()


def leave_confirm_keyboard() -> str:
    kb = Keyboard(inline=True)
    kb.add(
        Text("Подтвердить выход", payload={"type": "group_leave_confirm"}),
        color=KeyboardButtonColor.NEGATIVE,
    )
    kb.add(Text("Отмена", payload={"type": "group_leave_cancel"}), color=KeyboardButtonColor.SECONDARY)
    return kb.get_json()
