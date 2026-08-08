/**
 * Живой предпросмотр производных характеристик — ЗЕРКАЛО game/combat/formulas.py
 * и game/combat/balance_config.py. Канонический пересчёт (то, что реально
 * применяется и списывается) всегда происходит на сервере при сохранении;
 * этот файл только рисует "было -> станет" ДО отправки запроса.
 *
 * При изменении констант баланса на бэкенде — обновить и здесь.
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

const CRIT_PER_AGI = 0.003;
const CRIT_CAP = 0.6;

const MITIGATION_PER_VIT = 0.002;
const MITIGATION_CAP = 0.5;

const CONTROL_RESIST_PER_WIL = 0.01;
const CONTROL_RESIST_CAP = 0.75;

const SUPPORT_POWER_PER_WIL = 0.005;

export const PRIMARY_STAT_BY_CLASS = { warrior: 'str', rogue: 'agi', mage: 'int' };

export function tierForLevel(level) {
  if (level <= 15) return 'grey';
  if (level <= 30) return 'white';
  if (level <= 45) return 'green';
  if (level <= 60) return 'blue';
  if (level <= 80) return 'epic';
  return 'legendary';
}

// gearBonus (патч 32, баг 1) — сумма статов надетой экипировки
// (services/item_service.py::gear_bonus, приходит с сервером как
// character.gear_bonus), прибавляется к статам ДО расчёта формул — как и на
// сервере (services/derived_stats_service.py::compute). Без этого "до"
// (derived с сервера, уже учитывает экипировку) и "после" (этот предпросмотр)
// расходились у любого игрока с надетыми вещами.
export function computeDerived({ level, baseClass, stats, gearBonus = {} }) {
  const tierMult = TIER_MULTIPLIERS[tierForLevel(level)];
  const primaryStat = PRIMARY_STAT_BY_CLASS[baseClass] ?? 'str';

  const str = stats.str + (gearBonus.str ?? 0);
  const agi = stats.agi + (gearBonus.agi ?? 0);
  const int_ = stats.int + (gearBonus.int ?? 0);
  const vit = stats.vit + (gearBonus.vit ?? 0);
  const wil = stats.wil + (gearBonus.wil ?? 0);
  const primaryValue = { str, agi, int: int_ }[primaryStat] ?? 0;
  const kDmg = K_DMG[primaryStat];

  const maxHp = Math.round(HP_BASE + HP_PER_LEVEL * level + HP_PER_VIT * vit + HP_PER_TIER * tierMult);
  const damage = Math.round((WEAPON_BASE_PER_TIER * tierMult + kDmg * primaryValue) * 10) / 10;
  const critChance = Math.min(CRIT_PER_AGI * agi, CRIT_CAP);
  const mitigation = Math.min(MITIGATION_PER_VIT * vit, MITIGATION_CAP);
  const controlResist = Math.min(CONTROL_RESIST_PER_WIL * wil, CONTROL_RESIST_CAP);
  const supportPower = SUPPORT_POWER_PER_WIL * wil;

  return { maxHp, damage, critChance, mitigation, controlResist, supportPower };
}
