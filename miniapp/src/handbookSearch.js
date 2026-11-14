// Поиск по путеводителю (2026-11-14, владелец): 56 разделов, оглавления мало.
// Ищем по каждому блоку главы (абзац, список, таблица, раскрывашка целиком);
// блок подходит, если в нём есть все слова запроса. Регистр и «ё» не важны.

const MAX_HITS = 40;

/** Нижний регистр и «ё» -> «е»: длина строки не меняется, позиции совпадают. */
export function fold(s) {
  return String(s).toLowerCase().replace(/ё/g, 'е');
}

function plain(s) {
  return String(s).replace(/<\/?b>/g, '');
}

function blockText(b) {
  switch (b.t) {
    case 'ul': case 'ol': case 'ladder':
      return b.items.map(plain).join(' · ');
    case 'dl':
      return b.items.map(([term, def]) => `${plain(term)} - ${plain(def)}`).join(' · ');
    case 'table':
      return [...(b.head ? [b.head] : []), ...b.rows].map((row) => row.map(plain).join(' | ')).join(' · ');
    case 'details':
      return [plain(b.title), ...b.blocks.map(blockText)].join(' · ');
    default:
      return plain(b.text ?? '');
  }
}

/** Плоский список блоков всех глав - строится один раз. */
export function buildIndex(chapters) {
  const rows = [];
  chapters.forEach((ch, chapter) => {
    let section = null;
    ch.blocks.forEach((b, block) => {
      if (b.t === 'h3' || b.t === 'h4') section = plain(b.text);
      const text = blockText(b);
      if (text) rows.push({ chapter, block, section, text, folded: fold(text) });
    });
  });
  return rows;
}

export function queryWords(query) {
  return fold(query).split(/\s+/).filter((w) => w.length >= 2);
}

/** Кусок текста вокруг первого совпадения, обрезанный по словам. */
function snippet(text, at, len) {
  const from = Math.max(0, at - 50);
  const to = Math.min(text.length, at + len + 110);
  let start = from;
  let end = to;
  if (start > 0) {
    const sp = text.indexOf(' ', start);
    if (sp !== -1 && sp < at) start = sp + 1;
  }
  if (end < text.length) {
    const sp = text.lastIndexOf(' ', end);
    if (sp > at + len) end = sp;
  }
  return `${start > 0 ? '…' : ''}${text.slice(start, end)}${end < text.length ? '…' : ''}`;
}

export function search(index, chapters, query) {
  const words = queryWords(query);
  if (!words.length) return { words, hits: [], more: false };
  const hits = [];
  let total = 0;
  for (const row of index) {
    if (!words.every((w) => row.folded.includes(w))) continue;
    total += 1;
    if (hits.length >= MAX_HITS) continue;
    const at = row.folded.indexOf(words[0]);
    hits.push({
      chapter: row.chapter, block: row.block, section: row.section,
      title: chapters[row.chapter].title, no: chapters[row.chapter].no,
      snippet: snippet(row.text, at, words[0].length),
    });
  }
  return { words, hits, total, more: total > hits.length };
}

/** Разбить строку на куски с отметкой «совпадение» - для подсветки. */
export function marks(text, words) {
  const folded = fold(text);
  const spans = [];
  for (const w of words) {
    let i = folded.indexOf(w);
    while (i !== -1) {
      spans.push([i, i + w.length]);
      i = folded.indexOf(w, i + w.length);
    }
  }
  spans.sort((a, b) => a[0] - b[0]);
  const parts = [];
  let pos = 0;
  for (const [s, e] of spans) {
    if (e <= pos) continue;
    const from = Math.max(s, pos);
    if (from > pos) parts.push({ text: text.slice(pos, from) });
    parts.push({ text: text.slice(from, e), hit: true });
    pos = e;
  }
  if (pos < text.length) parts.push({ text: text.slice(pos) });
  return parts;
}
