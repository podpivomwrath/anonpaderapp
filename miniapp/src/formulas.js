/**
 * Живой предпросмотр производных характеристик - ЗЕРКАЛО game/combat/formulas.py
 * и game/combat/balance_config.py. Канонический пересчёт (то, что реально
 * применяется и списывается) всегда происходит на сервере при сохранении;
 * этот файл только рисует "было -> станет" ДО отправки запроса.
 *
 * При изменении констант баланса на бэкенде - обновить и здесь.
 */

export const TIER_MULTIPLIERS = {
  grey: 1.0,
  white: 1.15,
  green: 1.35,
  blue: 1.6,
  epic: 2.0,
  legendary: 2.5,
};

const HP_BASE = 60;
const HP_PER_LEVEL = 22;
const HP_PER_VIT = 8;
const HP_PER_TIER = 30;

const WEAPON_BASE_PER_TIER = 10;
const K_DMG = { str: 2.0, int: 2.0, agi: 1.5 };

// Ребаланс статов 2026-10-24 - зеркало game/combat/stat_model.py::GAME.
// Проценты с убывающей отдачей: cap * x / (x + k).
const CRIT_CAP = 0.6;
const CRIT_K = 200;
// Пассивки базовых классов до подкласса - зеркало
// game/combat/balance_config.py::BASE_CLASS_HP_MULT / BASE_CLASS_CRIT_BONUS.
const BASE_CLASS_HP_MULT = { warrior: 1.1 };
const BASE_CLASS_CRIT_BONUS = { rogue: 0.1 };

const MITIGATION_CAP = 0.5;
const MITIGATION_K = 250;

// Урон основного стата: до порога 30 + 2 x уровень - полностью, сверх - 0.35.
const PRIMARY_SOFT_BASE = 30;
const PRIMARY_SOFT_PER_LEVEL = 2;
const PRIMARY_OVER = 0.35;

// С убывающей отдачей (2026-10-29), как в stat_model.GAME.
const CONTROL_RESIST_K = 50;
const CONTROL_RESIST_CAP = 0.75;

// Сила поддержки - с убывающей отдачей от Воли (2026-10-29), как в stat_model.GAME.
const SUPPORT_CAP = 1.0;
const SUPPORT_K = 125;

// Сила яда Отравителя. Считается НЕ от урона атаки, а от Воли и Ловкости,
// причём Воля весит больше, хотя основной стат подкласса - Ловкость.
const POISON_PER_WIL = 0.7125;
const POISON_PER_AGI = 0.4875;
const POISON_MAX_STACKS = 3;

// Уворот - от Воли (2026-10-24, было от Ловкости).
const DODGE_CAP = 0.45;
// Подклассы разбойника: крит и уворот сверху (stat_model.GAME.base_crit/base_dodge).
const SUBCLASS_CRIT = { shadow_blade: 0.15, poisoner: 0.1 };
const SUBCLASS_DODGE = { shadow_blade: 0.05, poisoner: 0.05 };
const DODGE_K = 250;
const ABILITY_DODGE_RATIO = 0.25;
// Баффы уворота против навыков - вдвое слабее; общий потолок уворота.
const EFFECT_ABILITY_DODGE_RATIO = 0.5;
const DODGE_HARD_CAP = 0.8;

const hyper = (x, cap, k) => (x > 0 ? (cap * x) / (x + k) : 0);

// Порог Ловкости выше в 2/1.5 раза - одинаковый по урону с Силой и Интеллектом.
const PRIMARY_SOFT_STAT_MULT = { agi: 4 / 3 };

export function primaryEffective(value, level, stat = 'str') {
  const threshold = (PRIMARY_SOFT_BASE + PRIMARY_SOFT_PER_LEVEL * level) * (PRIMARY_SOFT_STAT_MULT[stat] ?? 1);
  return value <= threshold ? value : threshold + (value - threshold) * PRIMARY_OVER;
}

export const PRIMARY_STAT_BY_CLASS = { warrior: 'str', rogue: 'agi', mage: 'int' };

/**
 * Округление «половина к чётному» - то же, что делает round() в Python.
 * Math.round() округляет половину ВВЕРХ, поэтому на ровном .5 предпросмотр
 * расходился с сервером: 526.5 HP показывалось как 527, а сервер давал 526.
 */
function roundHalfToEven(value) {
  const floor = Math.floor(value);
  const diff = value - floor;
  if (Math.abs(diff - 0.5) > Number.EPSILON) return Math.round(value);
  return floor % 2 === 0 ? floor : floor + 1;
}

export function tierForLevel(level) {
  if (level <= 15) return 'grey';
  if (level <= 30) return 'white';
  if (level <= 45) return 'green';
  if (level <= 60) return 'blue';
  if (level <= 80) return 'epic';
  return 'legendary';
}

// gearBonus (патч 32, баг 1) - сумма статов надетой экипировки
// (services/item_service.py::gear_bonus, приходит с сервером как
// character.gear_bonus), прибавляется к статам ДО расчёта формул - как и на
// сервере (services/derived_stats_service.py::compute). Без этого "до"
// (derived с сервера, уже учитывает экипировку) и "после" (этот предпросмотр)
// расходились у любого игрока с надетыми вещами.
// mods - баффы пресета и еды, которые видны в сводке (character.derived_mods,
// services/derived_stats_service.py::SHOWN_MODS), как в бою.
export function computeDerived({ level, baseClass, subclass = null, stats, gearBonus = {}, mods = null }) {
  const m = mods ?? {};
  const tierMult = TIER_MULTIPLIERS[tierForLevel(level)];
  const primaryStat = PRIMARY_STAT_BY_CLASS[baseClass] ?? 'str';

  const str = stats.str + (gearBonus.str ?? 0);
  const agi = stats.agi + (gearBonus.agi ?? 0);
  const int_ = stats.int + (gearBonus.int ?? 0);
  const vit = stats.vit + (gearBonus.vit ?? 0);
  const wil = stats.wil + (gearBonus.wil ?? 0);
  const primaryValue = { str, agi, int: int_ }[primaryStat] ?? 0;
  const kDmg = K_DMG[primaryStat];

  const hpMult = (subclass ? 1 : (BASE_CLASS_HP_MULT[baseClass] ?? 1));
  const buffHpMult = 1 + (m.max_hp_bonus ?? 0);
  const dmgMult = (1 + (m.damage_bonus ?? 0)) * (1 + (m.reckless_damage_bonus ?? 0));
  const critBonus = subclass ? 0 : (BASE_CLASS_CRIT_BONUS[baseClass] ?? 0);
  const maxHp = roundHalfToEven(
    roundHalfToEven((HP_BASE + HP_PER_LEVEL * level + HP_PER_VIT * vit + HP_PER_TIER * tierMult) * hpMult) * buffHpMult,
  );
  const damage = roundHalfToEven(
    (WEAPON_BASE_PER_TIER * tierMult + kDmg * primaryEffective(primaryValue, level, primaryStat)) * dmgMult * 10,
  ) / 10;
  const critChance = Math.min(
    hyper(agi, CRIT_CAP, CRIT_K) + critBonus + (SUBCLASS_CRIT[subclass] ?? 0) + (m.crit_chance_bonus ?? 0), 1,
  );
  const mitigation = 1 - (1 - hyper(vit, MITIGATION_CAP, MITIGATION_K)) * (1 - (m.incoming_damage_reduction ?? 0));
  const controlResist = hyper(wil, CONTROL_RESIST_CAP, CONTROL_RESIST_K);
  const supportPower = hyper(wil, SUPPORT_CAP, SUPPORT_K);
  // урон за ход при полном числе стаков: делится на стаки и тут же
  // умножается обратно, но так формула читается так же, как в движке
  const poisonPower =
    ((POISON_PER_WIL * wil + POISON_PER_AGI * agi) / POISON_MAX_STACKS) * POISON_MAX_STACKS;
  // Прибавка подкласса - к обоим уворотам целиком, как в бою (skills.compute_hit).
  const subclassDodge = SUBCLASS_DODGE[subclass] ?? 0;
  const extraDodge = m.dodge_bonus ?? 0;
  const dodgeChance = Math.min(hyper(wil, DODGE_CAP, DODGE_K) + subclassDodge + extraDodge, DODGE_HARD_CAP);
  const abilityDodgeChance = Math.min(
    hyper(wil, DODGE_CAP, DODGE_K) * ABILITY_DODGE_RATIO + subclassDodge + extraDodge * EFFECT_ABILITY_DODGE_RATIO,
    DODGE_HARD_CAP,
  );

  return {
    maxHp, damage, critChance, mitigation, controlResist, supportPower,
    dodgeChance, abilityDodgeChance, poisonPower,
  };
}
