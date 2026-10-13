"""Клавиатура списка зелий/эликсиров в бою (патч 16). INLINE — окно
редактируется на месте (патч 13, ч.1)."""

from vkbottle import Keyboard, KeyboardButtonColor, Text

from game.content_loader import ElixirDef


#: Предметов на странице сумки. Inline-клавиатура VK - не больше 10 кнопок:
#: 8 предметов + «◀ Назад» и «Вперёд ▶» (2026-10-13: со свитками видов
#: стало 13, и полный набор в одно окно не влезал).
PAGE_SIZE = 8
BTN_PAGE_NEXT = "Вперёд ▶"
BTN_PAGE_PREV = "◀ Назад"


def paged_items_keyboard(stock: list, use_type: str, page_type: str, page: int = 0) -> str:
    """Страница сумки: по 2 предмета в ряд, внизу листание. use_type - payload
    кнопки предмета, page_type - payload листания (несёт номер страницы)."""
    pages = max(1, -(-len(stock) // PAGE_SIZE))
    page = max(0, min(page, pages - 1))
    chunk = stock[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]
    kb = Keyboard(inline=True)
    for idx, (elixir, count) in enumerate(chunk):
        kb.add(
            Text(f"{elixir.emoji} {elixir.name} ×{count}", payload={"type": use_type, "id": elixir.id}),
            color=KeyboardButtonColor.SECONDARY,
        )
        if idx % 2 == 1 and idx != len(chunk) - 1:
            kb.row()
    if pages > 1:
        kb.row()
        if page > 0:
            kb.add(Text(BTN_PAGE_PREV, payload={"type": page_type, "page": page - 1}),
                   color=KeyboardButtonColor.PRIMARY)
        if page < pages - 1:
            kb.add(Text(BTN_PAGE_NEXT, payload={"type": page_type, "page": page + 1}),
                   color=KeyboardButtonColor.PRIMARY)
    return kb.get_json()


def page_of(message) -> int | None:
    """Номер страницы из нажатия листания; None - сумку открыли заново."""
    try:
        page = (message.get_payload_json() or {}).get("page")
    except Exception:
        return None
    return page if isinstance(page, int) else None


def combat_items_keyboard(stock: list[tuple[ElixirDef, int]], page: int = 0) -> str:
    return paged_items_keyboard(stock, "use_item", "combat_items_page", page)
