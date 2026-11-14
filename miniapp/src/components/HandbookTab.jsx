import { createContext, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { SectionHead } from './ui.jsx';
import data from '../handbook.json';
import { buildRules, linkify, sectionId } from '../handbookLinks.js';
import { buildIndex, marks, search } from '../handbookSearch.js';
import '../handbook.css';

// Путеводитель Меченого (2026-10-23): раньше - статья VK и артефакт, теперь
// раздел мини-аппа. Не сплошной текст: оглавление, глава - своя страница,
// внизу переход к соседним. Названия в тексте - ссылки на свой раздел
// (handbookLinks.js), после перехода есть «Назад». Текст - handbook.json
// (tools/handbook_build.py собирает его из HTML путеводителя), в строках
// только <b>.

const KEY = 'handbook:chapter';
const RULES = buildRules(data.chapters);
// Поиск (2026-11-14): индекс блоков строится при первом запросе.
let INDEX = null;

function placesWord(n) {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return 'место';
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return 'места';
  return 'мест';
}

function Marked({ text, words }) {
  return marks(text, words).map((p, i) => (p.hit ? <mark key={i}>{p.text}</mark> : <span key={i}>{p.text}</span>));
}

function SearchBox({ query, onQuery }) {
  return (
    <div className="hb-search">
      <span className="hb-search__icon" aria-hidden="true">🔍</span>
      <input
        type="search" className="hb-search__input" value={query} placeholder="Поиск по путеводителю"
        aria-label="Поиск по путеводителю" enterKeyHint="search"
        onChange={(e) => onQuery(e.target.value)}
      />
      {query && (
        <button type="button" className="hb-search__clear" aria-label="Очистить" onClick={() => onQuery('')}>✕</button>
      )}
    </div>
  );
}

function Results({ query, onHit }) {
  const found = useMemo(() => {
    if (!INDEX) INDEX = buildIndex(data.chapters);
    return search(INDEX, data.chapters, query);
  }, [query]);
  if (!found.words.length) {
    return <p className="hb-search__note">Введите хотя бы две буквы.</p>;
  }
  if (!found.hits.length) {
    return (
      <p className="hb-search__note">
        Ничего не нашлось. Попробуйте начало слова: «руд» найдёт и «руда», и «руды».
      </p>
    );
  }
  return (
    <>
      <p className="hb-search__note">
        Нашлось {found.total} {placesWord(found.total)}{found.more ? `, показаны первые ${found.hits.length}` : ''}.
      </p>
      <div className="hb-hits">
        {found.hits.map((h) => (
          <button
            key={`${h.chapter}:${h.block}`} type="button" className="hb-hit"
            onClick={() => onHit(h.chapter, h.block)}
          >
            <small className="hb-hit__where">
              Глава {h.no} · {h.title}{h.section && h.section !== h.title ? ` · ${h.section}` : ''}
            </small>
            <span className="hb-hit__text"><Marked text={h.snippet} words={found.words} /></span>
          </button>
        ))}
      </div>
    </>
  );
}

// Страница: какие ссылки уже стоят, где мы сейчас, куда переходить.
const LinkCtx = createContext(null);

/** Строка с <b>…</b> и ссылками - без innerHTML. */
function Rich({ text, plain = false }) {
  const ctx = useContext(LinkCtx);
  const parts = String(text).split(/(<b>.*?<\/b>)/g).filter(Boolean);
  const render = (s, k) => {
    if (plain || !ctx) return s;
    return ctx.link(s).map((piece, i) => (
      typeof piece === 'string' ? piece : (
        <a
          key={`${k}-${i}`} className="hb-link" href={`#${ctx.target(piece.chapter, piece.section)}`}
          onClick={(e) => { e.preventDefault(); ctx.go(piece.chapter, piece.section); }}
        >{piece.text}</a>
      )
    ));
  };
  return parts.map((part, i) => (
    part.startsWith('<b>')
      ? <b key={i}>{render(part.slice(3, -4), i)}</b>
      : <span key={i}>{render(part, i)}</span>
  ));
}

function Block({ b, chapterId }) {
  switch (b.t) {
    case 'p': return <p><Rich text={b.text} /></p>;
    case 'h3': return <h3 id={sectionId(chapterId, b.text)}><Rich text={b.text} plain /></h3>;
    case 'h4': return <h4 id={sectionId(chapterId, b.text)}><Rich text={b.text} plain /></h4>;
    case 'levels': return <p className="hb-levels">{b.text}</p>;
    case 'quote': return <blockquote className="hb-quote"><Rich text={b.text} /></blockquote>;
    case 'note': return <div className="hb-note"><Rich text={b.text} /></div>;
    case 'ul':
      return <ul>{b.items.map((it, i) => <li key={i}><Rich text={it} /></li>)}</ul>;
    case 'ol':
      return <ol>{b.items.map((it, i) => <li key={i}><Rich text={it} /></li>)}</ol>;
    case 'ladder':
      return (
        <div className="hb-ladder">
          {b.items.map((it, i) => (
            <span key={i} className={b.peak.includes(i) ? 'hb-ladder__peak' : undefined}>{it}</span>
          ))}
        </div>
      );
    case 'dl':
      return (
        <dl className="hb-dl">
          {b.items.map(([term, def], i) => (
            <div key={i}><dt><Rich text={term} plain /></dt><dd><Rich text={def} /></dd></div>
          ))}
        </dl>
      );
    case 'table':
      return (
        <div className="hb-table">
          <table>
            {b.head && <thead><tr>{b.head.map((h, i) => <th key={i}><Rich text={h} plain /></th>)}</tr></thead>}
            <tbody>
              {b.rows.map((row, r) => (
                <tr key={r}>{row.map((cell, c) => <td key={c}><Rich text={cell} /></td>)}</tr>
              ))}
            </tbody>
          </table>
        </div>
      );
    case 'details':
      return (
        <details className="hb-details">
          <summary><Rich text={b.title} plain /></summary>
          {b.blocks.map((inner, i) => <Block key={i} b={inner} chapterId={chapterId} />)}
        </details>
      );
    default:
      return null;
  }
}

function Contents({ onOpen, query, onQuery, onHit }) {
  const searching = query.trim().length > 0;
  return (
    <>
      <SectionHead kind="handbook" icon="📖" value={data.intro.title} label={`${data.chapters.length} глав`} />
      {!searching && <p className="hb-lede">{data.intro.lede}</p>}
      <SearchBox query={query} onQuery={onQuery} />
      {searching && <Results query={query} onHit={onHit} />}
      {!searching && <nav className="hb-contents" aria-label="Главы">
        {data.chapters.map((ch, i) => (
          <button key={ch.id} type="button" className="hb-chapter-btn" onClick={() => onOpen(i)}>
            <span className="hb-chapter-btn__no">{ch.no}</span>
            <span className="hb-chapter-btn__text">
              <b>{ch.title}</b>
              {ch.levels && <small>{ch.levels}</small>}
            </span>
            <span className="hb-chapter-btn__go" aria-hidden="true">›</span>
          </button>
        ))}
      </nav>}
    </>
  );
}

function Chapter({ index, onOpen, onBack, onReturn, go }) {
  const ch = data.chapters[index];
  const prev = data.chapters[index - 1];
  const next = data.chapters[index + 1];
  // Подраздел, в котором стоит блок: из него не ссылаемся на него же.
  const blocks = useMemo(() => {
    let section = null;
    return ch.blocks.map((b) => {
      if (b.t === 'h3' || b.t === 'h4') section = b.text;
      return { b, section };
    });
  }, [ch]);
  // Поставленные ссылки и уже разобранные строки - на страницу целиком.
  // Разбор кэшируется: повторный рендер (StrictMode, обновление) должен
  // дать те же ссылки, а не решить, что первое упоминание уже было.
  // 2026-10-24, владелец: «гиперссылки везде» - термин ссылкой в каждом
  // абзаце, пункте и строке таблицы, а не только первый раз на странице.
  const linker = useMemo(() => ({ used: new Map(), cache: new Map() }), [index]);
  const linkFor = (here) => (text) => {
    const key = `${here.block}|${here.section}|${text}`;
    if (!linker.used.has(here.block)) linker.used.set(here.block, new Set());
    if (!linker.cache.has(key)) linker.cache.set(key, linkify(text, RULES, linker.used.get(here.block), here));
    return linker.cache.get(key);
  };
  const target = (chapter, section) => {
    const id = data.chapters[chapter].id;
    return section ? sectionId(id, section) : `hb-${id}`;
  };
  return (
    <article className="hb-page">
      <button type="button" className="hb-back" onClick={onBack}>‹ Оглавление</button>
      {/* После перехода по ссылке ты посреди чужой главы - «Назад» всегда под рукой. */}
      {onReturn && <button type="button" className="hb-return" onClick={onReturn}>↩ Назад</button>}
      <span className="hb-stamp">Глава {ch.no}</span>
      <h2>{ch.title}</h2>
      {ch.levels && <p className="hb-levels">{ch.levels}</p>}
      {blocks.map(({ b, section }, i) => (
        <LinkCtx.Provider key={i} value={{ go, target, link: linkFor({ chapter: index, section, block: i }) }}>
          {/* Обёртка - чтобы поиск мог прокрутить к блоку и подсветить его. */}
          <div className="hb-block" data-block={i}>
            <Block b={b} chapterId={ch.id} />
          </div>
        </LinkCtx.Provider>
      ))}
      <div className="hb-pager">
        {prev ? (
          <button type="button" onClick={() => onOpen(index - 1)}>
            <small>‹ Глава {prev.no}</small><b>{prev.title}</b>
          </button>
        ) : <span />}
        {next ? (
          <button type="button" className="hb-pager__next" onClick={() => onOpen(index + 1)}>
            <small>Глава {next.no} ›</small><b>{next.title}</b>
          </button>
        ) : <span />}
      </div>
    </article>
  );
}

function savedIndex() {
  try {
    const raw = localStorage.getItem(KEY);
    const saved = raw === null ? NaN : Number(raw);
    return Number.isInteger(saved) && saved >= 0 && saved < data.chapters.length ? saved : null;
  } catch {
    return null;
  }
}

export default function HandbookTab() {
  // Открытая глава переживает выход из раздела - вернёшься туда же.
  const [view, setView] = useState(() => ({ index: savedIndex(), section: null, y: null, block: null, seq: 0 }));
  // Откуда пришли по ссылкам: «↩ Назад» возвращает на место.
  const [trail, setTrail] = useState([]);
  // Запрос живёт здесь: «↩ Назад» из найденного места возвращает к тем же результатам.
  const [query, setQuery] = useState('');
  const top = useRef(null);

  const show = (index, section = null, y = null, block = null) => {
    setView((v) => ({ index, section, y, block, seq: v.seq + 1 }));
    try {
      if (index === null) localStorage.removeItem(KEY); else localStorage.setItem(KEY, String(index));
    } catch { /* без памяти - просто с оглавления */ }
  };
  const open = (index) => { setTrail([]); show(index); };
  const go = (index, section) => {
    setTrail((t) => [...t, { index: view.index, y: window.scrollY }]);
    show(index, section);
  };
  const back = () => {
    const last = trail[trail.length - 1];
    setTrail((t) => t.slice(0, -1));
    show(last.index, null, last.y);
  };
  // Найденное место: глава, прокрутка к блоку, подсветка.
  const hit = (index, block) => {
    setTrail((t) => [...t, { index: view.index, y: window.scrollY }]);
    show(index, null, null, block);
  };

  useEffect(() => {
    if (view.y !== null) {
      window.scrollTo(0, view.y);
      return undefined;
    }
    if (view.block !== null && top.current) {
      const el = top.current.querySelector(`.hb-page [data-block="${view.block}"]`);
      if (el) {
        el.querySelectorAll('details').forEach((d) => { d.open = true; });
        el.scrollIntoView({ block: 'center' });
        el.classList.add('hb-block--hit');
        const id = setTimeout(() => el.classList.remove('hb-block--hit'), 2400);
        return () => clearTimeout(id);
      }
    }
    const target = view.section && view.index !== null
      ? document.getElementById(sectionId(data.chapters[view.index].id, view.section))
      : null;
    (target || top.current)?.scrollIntoView({ block: 'start' });
    return undefined;
  }, [view]);

  return (
    <div className="handbook" ref={top}>
      {view.index === null
        ? <Contents onOpen={open} query={query} onQuery={setQuery} onHit={hit} />
        : (
          <Chapter
            key={view.index} index={view.index} onOpen={open} go={go}
            onBack={() => open(null)} onReturn={trail.length ? back : null}
          />
        )}
    </div>
  );
}
