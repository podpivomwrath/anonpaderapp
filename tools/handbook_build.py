"""Справочник для мини-аппа из HTML путеводителя (2026-10-23).

Путеводитель жил артефактом на claude.ai и статьёй VK. Теперь он раздел
мини-аппа: глава - своя страница. Этот скрипт берёт HTML путеводителя и
раскладывает его в miniapp/src/handbook.json - главы и блоки (абзац,
подзаголовок, список, таблица, заметка, список событий, лесенка, свёрнутый
блок). В тексте остаётся только <b>: мини-апп рисует его сам, без innerHTML.

    python tools/handbook_build.py путь/к/guide.html

Дальше текст правится прямо в handbook.json; скрипт нужен, только если
путеводитель снова пересобирают целиком.
"""

import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "miniapp" / "src" / "handbook.json"
VOID = {"br", "img", "meta", "link", "hr", "input"}


class Node:
    def __init__(self, tag, attrs, parent=None):
        self.tag, self.attrs, self.parent, self.children = tag, dict(attrs), parent, []

    @property
    def cls(self) -> set[str]:
        return set((self.attrs.get("class") or "").split())


class Tree(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("root", [])
        self.cur = self.root

    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs, self.cur)
        self.cur.children.append(node)
        if tag not in VOID:
            self.cur = node

    def handle_endtag(self, tag):
        node = self.cur
        while node is not self.root and node.tag != tag:
            node = node.parent
        if node is not self.root:
            self.cur = node.parent

    def handle_data(self, data):
        self.cur.children.append(data)


def inline(node) -> str:
    """Текст узла; <b>/<strong> остаются тегом <b>, остальное - текстом."""
    out = []
    for ch in node.children:
        if isinstance(ch, str):
            out.append(ch)
        elif ch.tag in ("b", "strong"):
            out.append(f"<b>{inline(ch)}</b>")
        elif ch.tag == "br":
            out.append("\n")
        else:
            out.append(inline(ch))
    return re.sub(r"[ \t\r\n]+", " ", "".join(out)).strip()


def kids(node):
    return [c for c in node.children if not isinstance(c, str)]


def block(node) -> dict | None:
    t, cls = node.tag, node.cls
    if t == "p" and "levels" in cls:
        return {"t": "levels", "text": inline(node)}  # уровни подраздела
    if t == "p":
        return {"t": "p", "text": inline(node)}
    if t in ("h3", "h4"):
        return {"t": t, "text": inline(node)}
    if t in ("ul", "ol"):
        return {"t": t, "items": [inline(li) for li in kids(node) if li.tag == "li"]}
    if t == "blockquote":
        return {"t": "quote", "text": inline(node)}
    if t == "div" and "note" in cls:
        return {"t": "note", "text": inline(node)}
    if t == "div" and "ladder" in cls:
        return {"t": "ladder", "items": [inline(s) for s in kids(node)],
                "peak": [i for i, s in enumerate(kids(node)) if "peak" in s.cls]}
    if t == "div" and "scroller" in cls:
        table = next((c for c in kids(node) if c.tag == "table"), None)
        return block(table) if table is not None else None
    if t == "table":
        rows = []
        for tr in _find(node, "tr"):
            cells = [c for c in kids(tr) if c.tag in ("td", "th")]
            rows.append({"head": all(c.tag == "th" for c in cells), "cells": [inline(c) for c in cells]})
        head = rows[0]["cells"] if rows and rows[0]["head"] else None
        return {"t": "table", "head": head, "rows": [r["cells"] for r in rows if not r["head"]]}
    if t == "dl":
        items, term = [], None
        for c in kids(node):
            if c.tag == "dt":
                term = inline(c)
            elif c.tag == "dd":
                items.append([term or "", inline(c)])
        return {"t": "dl", "items": items}
    if t == "details":
        summary = next((c for c in kids(node) if c.tag == "summary"), None)
        inner = [b for c in kids(node) if c.tag != "summary" and (b := block(c))]
        return {"t": "details", "title": inline(summary) if summary else "", "blocks": inner}
    if t == "div":
        inner = [b for c in kids(node) if (b := block(c))]
        return {"t": "group", "blocks": inner} if inner else None
    return None


def _find(node, tag):
    for c in kids(node):
        if c.tag == tag:
            yield c
        yield from _find(c, tag)


def build(html: str) -> dict:
    tree = Tree()
    tree.feed(html)
    main = next(_find(tree.root, "main"))
    intro = {
        "title": inline(next(_find(main, "h1"))),
        "lede": inline(next(n for n in _find(main, "p") if "lede" in n.cls)),
    }
    chapters = []
    for sec in _find(main, "section"):
        if "chapter" not in sec.cls:
            continue
        no = next((c for c in kids(sec) if "chapter-no" in c.cls), None)
        # Уровни главы - строка сразу под заголовком; дальше они относятся
        # к подразделу («Торговля - с 10 уровня») и остаются в тексте.
        head = []
        for c in kids(sec):
            if c.tag in ("h3", "h4"):
                break
            head.append(c)
        levels = next((c for c in head if c.tag == "p" and "levels" in c.cls), None)
        blocks = []
        for c in kids(sec):
            if c.tag == "h2" or "chapter-no" in c.cls or c is levels:
                continue
            b = block(c)
            if b is None:
                continue
            blocks.extend(b["blocks"] if b["t"] == "group" else [b])
        chapters.append({
            "id": sec.attrs.get("id"),
            "no": inline(no).replace("Глава", "").strip() if no else "",
            "title": inline(next(_find(sec, "h2"))),
            "levels": inline(levels) if levels else None,
            "blocks": blocks,
        })
    return {"intro": intro, "chapters": chapters}


if __name__ == "__main__":
    data = build(Path(sys.argv[1]).read_text(encoding="utf-8"))
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{len(data['chapters'])} глав -> {OUT}")
