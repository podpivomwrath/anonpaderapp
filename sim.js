// Симулятор боевых формул текстовой MMORPG
// Запуск: node sim.js

// ---------- Константы ----------

const TIERS = {
  gray:   { name: 'Серый',     mult: 1.0 },
  white:  { name: 'Белый',     mult: 1.15 },
  green:  { name: 'Зелёный',   mult: 1.35 },
  blue:   { name: 'Синий',     mult: 1.6 },
  purple: { name: 'Фиолетовый', mult: 2.0 },
  orange: { name: 'Оранжевый', mult: 2.5 },
};

// Ступенчатая функция «нормальный тир шмота по уровню»
function tierByLevel(level) {
  if (level <= 15) return TIERS.gray;
  if (level <= 30) return TIERS.white;
  if (level <= 45) return TIERS.green;
  if (level <= 60) return TIERS.blue;
  if (level <= 80) return TIERS.purple;
  return TIERS.orange;
}

const STAT_NAMES = ['STR', 'AGI', 'INT', 'VIT', 'WIL'];

// Суммарный пул очков на уровне: 75 старт + 3 за уровень
function statPool(level) {
  return 75 + 3 * level;
}

// ---------- Распределения статов ----------

// Поровну между всеми 5 статами (остаток — по одному в первые статы)
function balancedStats(level) {
  const pool = statPool(level);
  const base = Math.floor(pool / 5);
  let rest = pool - base * 5;
  const stats = {};
  for (const s of STAT_NAMES) {
    stats[s] = base + (rest > 0 ? 1 : 0);
    if (rest > 0) rest--;
  }
  return stats;
}

// Моностат: 80% в основной стат, остальное поровну между остальными 4
function monoStats(level, primary) {
  const pool = statPool(level);
  const main = Math.floor(pool * 0.8);
  const others = pool - main;
  const base = Math.floor(others / 4);
  let rest = others - base * 4;
  const stats = {};
  for (const s of STAT_NAMES) {
    if (s === primary) {
      stats[s] = main;
    } else {
      stats[s] = base + (rest > 0 ? 1 : 0);
      if (rest > 0) rest--;
    }
  }
  return stats;
}

// ---------- Формулы ----------

function maxHP(level, vit) {
  return 80 + 15 * level + 12 * vit;
}

function weaponBase(level, tierMult) {
  return 2.2 * level * tierMult;
}

// K_dmg: 2 для STR и INT, 1.5 для AGI
function kDmg(primary) {
  return primary === 'AGI' ? 1.5 : 2;
}

function critChance(agi) {
  return Math.min(0.003 * agi, 0.6);
}

const CRIT_MULT = 1.5;

function mitigation(vit) {
  return Math.min(0.002 * vit, 0.5);
}

function controlResist(wil) {
  return Math.min(0.01 * wil, 0.75);
}

function supportPower(wil) {
  return 0.005 * wil; // без потолка
}

// ---------- Персонажи ----------

function makeCharacter(name, level, stats, primary, tier) {
  return {
    name,
    level,
    stats,
    primary,
    tier,
    maxHP: maxHP(level, stats.VIT),
    hp: maxHP(level, stats.VIT),
    baseDamage: weaponBase(level, tier.mult) + kDmg(primary) * stats[primary],
    critChance: critChance(stats.AGI),
    mitigation: mitigation(stats.VIT),
    controlResist: controlResist(stats.WIL),
    supportPower: supportPower(stats.WIL),
  };
}

function makePlayer(level, build /* 'mono' | 'balanced' */) {
  const primary = 'STR'; // усреднённый воин
  const stats = build === 'mono' ? monoStats(level, primary) : balancedStats(level);
  const tier = tierByLevel(level); // игрок тоже в «норм. тире» своего уровня
  const label = build === 'mono' ? 'Игрок (моностат)' : 'Игрок (баланс)';
  return makeCharacter(label, level, stats, primary, tier);
}

function spawnWolf(level) {
  const stats = balancedStats(level); // «средний сбалансированный игрок»
  const tier = tierByLevel(level);
  return makeCharacter('Волк', level, stats, 'STR', tier); // урон через STR-эквивалент, K_dmg=2
}

// ---------- RNG (seeded, чтобы прогоны были воспроизводимы) ----------

function mulberry32(seed) {
  let a = seed >>> 0;
  return function () {
    a |= 0; a = (a + 0x6D2B79F5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// ---------- Бой ----------

// Удар attacker → defender: возвращает { dmg, crit }
function rollHit(attacker, defender, rng) {
  let dmg = attacker.baseDamage;
  const crit = rng() < attacker.critChance;
  if (crit) dmg *= CRIT_MULT;
  dmg = dmg * (1 - defender.mitigation);
  return { dmg: Math.round(dmg), crit };
}

function pct(hp, max) {
  return ((Math.max(hp, 0) / max) * 100).toFixed(1);
}

// Пошаговый бой: оба бьют одновременно каждый тик, урон вычитается одновременно
function simulateFight(player, wolf, { verbose = true, rng = mulberry32(42), maxTicks = 200 } = {}) {
  const p = { ...player, hp: player.maxHP };
  const w = { ...wolf, hp: wolf.maxHP };
  let tick = 0;

  while (tick < maxTicks) {
    tick++;
    const pHit = rollHit(p, w, rng);
    const wHit = rollHit(w, p, rng);

    // одновременный резолв
    w.hp -= pHit.dmg;
    p.hp -= wHit.dmg;

    if (verbose) {
      console.log(`Тик ${tick}: ${p.name} бьёт Волка на ${pHit.dmg}${pHit.crit ? ' (крит!)' : ''} → Волк: ${Math.max(w.hp, 0)}/${w.maxHP} HP (${pct(w.hp, w.maxHP)}%)`);
      console.log(`Тик ${tick}: Волк кусает Игрока на ${wHit.dmg}${wHit.crit ? ' (крит!)' : ''} → Игрок: ${Math.max(p.hp, 0)}/${p.maxHP} HP (${pct(p.hp, p.maxHP)}%)`);
    }

    const pDead = p.hp <= 0;
    const wDead = w.hp <= 0;
    if (pDead && wDead) {
      if (verbose) console.log(`Бой окончен за ${tick} тиков. Ничья (оба пали одновременно)`);
      return { ticks: tick, winner: 'draw' };
    }
    if (wDead) {
      if (verbose) console.log(`Бой окончен за ${tick} тиков. Победитель: ${p.name}`);
      return { ticks: tick, winner: 'player' };
    }
    if (pDead) {
      if (verbose) console.log(`Бой окончен за ${tick} тиков. Победитель: Волк`);
      return { ticks: tick, winner: 'wolf' };
    }
  }
  if (verbose) console.log(`Бой не завершён за ${maxTicks} тиков (лимит)`);
  return { ticks: maxTicks, winner: 'timeout' };
}

// ---------- Калибровка ----------

const RUNS_PER_CELL = 500;

// Средние тики победы + винрейт по множеству прогонов (крит рандомный)
function calibrateCell(level, build, seedBase) {
  const player = makePlayer(level, build);
  const wolf = spawnWolf(level);
  let totalTicks = 0, wins = 0, losses = 0, draws = 0;
  for (let i = 0; i < RUNS_PER_CELL; i++) {
    const r = simulateFight(player, wolf, { verbose: false, rng: mulberry32(seedBase + i) });
    totalTicks += r.ticks;
    if (r.winner === 'player') wins++;
    else if (r.winner === 'wolf') losses++;
    else draws++;
  }
  return {
    avgTicks: totalTicks / RUNS_PER_CELL,
    winRate: wins / RUNS_PER_CELL,
    lossRate: losses / RUNS_PER_CELL,
    drawRate: draws / RUNS_PER_CELL,
  };
}

function runCalibration() {
  const levels = [10, 30, 50, 70, 100];

  console.log('='.repeat(70));
  console.log('КАЛИБРОВКА: игрок (воин STR) vs волк того же уровня');
  console.log(`(${RUNS_PER_CELL} прогонов на ячейку, средние тики и % побед игрока)`);
  console.log('='.repeat(70));
  console.log();
  console.log('Уровень | Моностат (тиков) | Сбалансированный (тиков)');
  console.log('--------|------------------|-------------------------');

  const details = [];
  for (const level of levels) {
    const mono = calibrateCell(level, 'mono', 1000 + level);
    const bal = calibrateCell(level, 'balanced', 5000 + level);
    details.push({ level, mono, bal });
    console.log(
      `${String(level).padEnd(7)} | ${mono.avgTicks.toFixed(1).padEnd(16)} | ${bal.avgTicks.toFixed(1)}`
    );
  }

  console.log();
  console.log('Подробно (винрейт игрока / ничьи):');
  for (const { level, mono, bal } of details) {
    console.log(
      `  ур.${String(level).padEnd(3)} моностат: побед ${(mono.winRate * 100).toFixed(0)}%, ничьих ${(mono.drawRate * 100).toFixed(1)}% | ` +
      `баланс: побед ${(bal.winRate * 100).toFixed(0)}%, ничьих ${(bal.drawRate * 100).toFixed(1)}%`
    );
  }

  return details;
}

// ---------- Прогон ----------

function printCharacter(c) {
  const s = c.stats;
  console.log(
    `${c.name} [ур.${c.level}, ${c.tier.name}]: ` +
    `STR ${s.STR} / AGI ${s.AGI} / INT ${s.INT} / VIT ${s.VIT} / WIL ${s.WIL} | ` +
    `HP ${c.maxHP}, урон ${c.baseDamage.toFixed(1)}, крит ${(c.critChance * 100).toFixed(1)}%, ` +
    `митигация ${(c.mitigation * 100).toFixed(1)}%, резист контролю ${(c.controlResist * 100).toFixed(1)}%, ` +
    `сила саппорта ${(c.supportPower * 100).toFixed(1)}%`
  );
}

function main() {
  // Демо-бой с подробным логом
  console.log('='.repeat(70));
  console.log('ДЕМО-БОЙ: игрок-моностат 30 ур. vs волк 30 ур.');
  console.log('='.repeat(70));
  const demoPlayer = makePlayer(30, 'mono');
  const demoWolf = spawnWolf(30);
  printCharacter(demoPlayer);
  printCharacter(demoWolf);
  console.log();
  simulateFight(demoPlayer, demoWolf, { verbose: true, rng: mulberry32(42) });
  console.log();

  runCalibration();
}

main();
