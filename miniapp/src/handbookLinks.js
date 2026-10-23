// Ссылки внутри путеводителя (2026-10-23, владелец: «названия - кнопки-
// ссылки туда, на что они ссылаются»). Слово в тексте - основа с любым
// окончанием (русские падежи), цель - глава по id и, если есть, подраздел по
// тексту его заголовка в handbook.json. Ссылкой становится только первое
// упоминание на странице и не внутри того раздела, куда она ведёт.

const W = '[а-яёa-z-]*';

/** [основа(ы) через |, id главы, заголовок подраздела или null] */
const TERMS = [
  [`кровав${W} клейм${W}|клейм${W}`, 'group', 'Кровавое клеймо'],
  [`арен${W}`, 'group', 'Арена'],
  [`заказ${W} на игрок${W}`, 'group', 'Заказы на игроков'],
  ['pvp', 'group', 'PvP'],
  [`групп${W}`, 'group', 'Группа'],
  [`кровав${W} разлом${W}|разлом${W}`, 'rifts', null],
  [`путь без подкласса|отказ${W} от подкласса`, 'path', 'Путь без подкласса'],
  [`микробафф${W}|испытани${W}`, 'path', 'Микробаффы и испытания'],
  [`пресет${W}`, 'path', 'Пресеты'],
  [`подкласс${W}`, 'path', null],
  [`турбоишак${W}|маунт${W}`, 'world', 'Как перемещаться'],
  [`мирн${W} зон${W}`, 'world', 'Где не нападают'],
  [`сюжет${W}|наставник${W}`, 'world', 'Сюжет и наставники'],
  [`отдых${W}`, 'fight', 'Отдых'],
  [`смерт${W}|возрожден${W}`, 'fight', 'Смерть'],
  [`пепельн${W} менял${W}`, 'explore', 'Как устроены события'],
  [`исследова${W}`, 'explore', null],
  ['мощь', 'gear', null],
  [`уникальн${W} вещ${W}`, 'gear', null],
  [`рыбалк${W}`, 'crafts', 'Рыбалка'],
  [`озёр${W}|озер${W}`, 'crafts', 'Озёра'],
  [`садок${W}|садк${W}`, 'crafts', 'Уровень рыбалки и садок'],
  [`горн${W} дел${W}`, 'crafts', 'Уровень горного дела'],
  [`рудник${W}`, 'crafts', 'Рудники'],
  [`руд[аеуы]|руду|рудой`, 'crafts', 'Руда'],
  [`торгов${W} фирм${W}|торговл${W}`, 'crafts', 'Торговля'],
  [`повозк${W}|повозок`, 'crafts', 'Повозка'],
  [`процветани${W}`, 'crafts', 'Процветание городов'],
  [`долг${W} пут${W}`, 'voyage', null],
  [`гильди${W}`, 'guild', null],
  [`ежедневк${W}|ежедневн${W} задани${W}`, 'daily', null],
  [`титул${W}`, 'daily', null],
  [`миров${W} босс${W}`, 'endgame', 'Мировые боссы'],
  [`ключ${W} монолита|рейд${W}`, 'endgame', 'Ключ Монолита и рейды'],
  [`ковк${W}|перековк${W}|выкова${W}`, 'craft', 'Ковка'],
  [`мастерск${W}`, 'craft', null],
  [`магазин${W}|настойк${W} пепла|секретн${W} карман${W}`, 'extra', 'Магазин'],
  [`бирж${W}|самоцвет${W}`, 'extra', null],
  [`метк${W} хранителя`, 'extra', null],
  [`оглушени${W}|заморозк${W}`, 'skills', 'Оглушение и заморозка'],
  [`кровав${W} рыцар${W}`, 'skills', 'Кровавый рыцарь'],
  [`т[её]мн${W} мистик${W}`, 'skills', 'Тёмный мистик'],
  [`элементалист${W}`, 'skills', 'Элементалист'],
  [`отравител${W}`, 'skills', 'Отравитель'],
  [`клин${W} теней`, 'skills', 'Клинок теней'],
];

const ROMAN = /^[IVXL]+$/;
// «глава VII», «главе XVI», «главах XIII и XIV».
const CHAPTER_REF = 'глав(?:а|е|ы|у|ой|ах)?\\s+[IVXL]+(?:\\s+и\\s+[IVXL]+)?';

export function sectionId(chapterId, title) {
  return `hb-${chapterId}-${title.toLowerCase().replace(/[^a-zа-яё0-9]+/gi, '-')}`;
}

/** Правила для данных путеводителя: регулярка и куда ведёт. */
export function buildRules(chapters) {
  const byId = Object.fromEntries(chapters.map((c, i) => [c.id, i]));
  const byNo = Object.fromEntries(chapters.map((c, i) => [c.no, i]));
  const rules = TERMS
    .filter(([, ch]) => ch in byId)
    .map(([stem, ch, sec]) => ({
      key: `${ch}|${sec || ''}`,
      re: new RegExp(`(?<![а-яёa-z0-9-])(?:${stem})(?![а-яёa-z0-9])`, 'iu'),
      chapter: byId[ch],
      section: sec,
    }));
  return { rules, byNo, chapterRef: new RegExp(CHAPTER_REF, 'u') };
}

/**
 * Разрезать строку на куски: текст и ссылки {text, chapter, section}.
 * used - уже поставленные на странице ссылки (по ключу цели), here - где
 * стоит текст: {chapter, section} - туда же не ссылаемся.
 */
export function linkify(text, { rules, byNo, chapterRef }, used, here) {
  const out = [];
  let rest = text;
  while (rest) {
    let best = null;
    const ref = chapterRef.exec(rest);
    if (ref) best = { index: ref.index, length: ref[0].length, ref: ref[0] };
    for (const rule of rules) {
      if (used.has(rule.key)) continue;
      if (rule.chapter === here.chapter && (rule.section === null || rule.section === here.section)) continue;
      const m = rule.re.exec(rest);
      if (m && (!best || m.index < best.index)) best = { index: m.index, length: m[0].length, rule };
    }
    if (!best) {
      out.push(rest);
      break;
    }
    if (best.index) out.push(rest.slice(0, best.index));
    const piece = rest.slice(best.index, best.index + best.length);
    if (best.rule) {
      used.add(best.rule.key);
      out.push({ text: piece, chapter: best.rule.chapter, section: best.rule.section });
    } else {
      // «главах XIII и XIV» - каждая цифра своей ссылкой.
      const parts = piece.split(/(\s+)/);
      let word = '';
      for (const p of parts) {
        if (ROMAN.test(p) && p in byNo) {
          if (word) out.push(word);
          word = '';
          out.push({ text: p, chapter: byNo[p], section: null });
        } else {
          word += p;
        }
      }
      if (word) out.push(word);
    }
    rest = rest.slice(best.index + best.length);
  }
  return out;
}
