import { useEffect, useState } from 'react';
import { Group, Header, Div, Text, Placeholder, Button, Input } from '@vkontakte/vkui';
import { getPresets, savePreset, switchPreset, buyPresetSlot } from '../api.js';
import Skeleton from './Skeleton.jsx';
import { SectionHead } from './ui.jsx';

// Коды ошибок сервера, у которых нет человеческого текста на той стороне.
const ERROR_TEXTS = {
  not_enough_gold: 'Не хватило золота.',
  no_subclass: 'Сначала выбери подкласс.',
  bad_request: 'Не удалось сохранить: проверь название и состав.',
};

// Цвет бафа по категории (2026-10-22): урон, оборона, лечение и прочее
// различаются с первого взгляда. Класс CSS, а не текст на экране.
const CATEGORY_TONE = {
  damage: 'red', defense: 'blue', healing: 'green', control_utility: 'violet', group_support: 'gold',
};
const tone = (b) => CATEGORY_TONE[b?.category] || 'gray';

function BuffChip({ buff }) {
  return <span className={`buff-chip buff-chip--${tone(buff)}`}>{buff?.name || '?'}</span>;
}

function saveErrorText(err) {
  const code = err?.message;
  if (!code) return 'Не удалось сохранить пресет.';
  // Ошибки валидации приходят готовой фразой на русском - показываем как есть.
  return ERROR_TEXTS[code] || code;
}

export default function PresetsTab({ character }) {
  const [data, setData] = useState(null);
  const [status, setStatus] = useState('loading'); // loading | ready | error
  const [editingId, setEditingId] = useState(undefined); // undefined - не редактируем; null - новый; число - существующий
  const [editName, setEditName] = useState('');
  const [editBuffs, setEditBuffs] = useState([]);
  const [busy, setBusy] = useState(false);
  const [errorMsg, setErrorMsg] = useState(null);

  function load() {
    setStatus('loading');
    getPresets()
      .then((res) => {
        setData(res);
        setStatus('ready');
      })
      .catch(() => setStatus('error'));
  }

  useEffect(load, []);

  if (!character.subclass && !character.buff_pool) {
    return (
      <Placeholder icon={<div style={{ fontSize: 48 }}>⚔️</div>}>
        Твоя Метка ещё не обрела форму. Возвращайся, когда кровь потребует имени.
      </Placeholder>
    );
  }

  if (status === 'loading') {
    return (
      <Skeleton />
    );
  }

  if (status === 'error' || !data) {
    return <Placeholder icon={<div style={{ fontSize: 48 }}>⚔️</div>}>Не удалось загрузить пресеты.</Placeholder>;
  }

  function startEdit(preset) {
    setEditingId(preset ? preset.id : null);
    setEditName(preset ? preset.name : '');
    setEditBuffs(preset ? [...preset.buff_ids] : []);
    setErrorMsg(null);
  }

  function cancelEdit() {
    setEditingId(undefined);
    setErrorMsg(null);
  }

  function toggleBuff(buffId) {
    setEditBuffs((prev) => (prev.includes(buffId) ? prev.filter((id) => id !== buffId) : [...prev, buffId]));
  }

  async function handleSave() {
    setBusy(true);
    setErrorMsg(null);
    try {
      await savePreset(editName.trim(), editBuffs, editingId ?? undefined);
      setEditingId(undefined);
      load();
    } catch (err) {
      // Сервер присылает точную причину (состав, слоты, золото) - раньше она
      // выбрасывалась, и игрок читал общую догадку вместо конкретики.
      setErrorMsg(saveErrorText(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleSwitch(presetId) {
    setBusy(true);
    setErrorMsg(null);
    try {
      await switchPreset(presetId);
      load();
    } catch (err) {
      setErrorMsg(saveErrorText(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleBuySlot() {
    setBusy(true);
    setErrorMsg(null);
    try {
      await buyPresetSlot();
      load();
    } catch (err) {
      setErrorMsg(saveErrorText(err));
    } finally {
      setBusy(false);
    }
  }

  if (editingId !== undefined) {
    return (
      <Group header={<Header>{editingId === null ? 'Новый пресет' : 'Изменить пресет'}</Header>}>
        <Div>
          <Input placeholder="Название" value={editName} onChange={(e) => setEditName(e.target.value)} />
        </Div>
        <Div style={{ fontSize: 13, opacity: 0.7 }}>{data.rule_hint}</Div>
        <div className="buff-pick">
          {data.buffs.map((b) => {
            const on = editBuffs.includes(b.id);
            return (
              <button
                type="button" key={b.id} disabled={!b.unlocked} aria-pressed={on}
                className={`buff-tile buff-tile--${tone(b)}${on ? ' buff-tile--on' : ''}`}
                onClick={() => toggleBuff(b.id)}
              >
                <span className="buff-tile__head">
                  <b>{b.unlocked ? '' : '🔒 '}{b.name}</b>
                  <span className="buff-tile__check" aria-hidden="true">{on ? '✓' : ''}</span>
                </span>
                <small className="buff-tile__cat">{b.category_label}</small>
                {/* без описания пресет собирался вслепую, по одним названиям */}
                {b.description && <small className="buff-tile__desc">{b.description}</small>}
              </button>
            );
          })}
        </div>
        {errorMsg && (
          <Div>
            <Text style={{ color: '#c81e3a' }}>{errorMsg}</Text>
          </Div>
        )}
        <Div style={{ display: 'flex', gap: 8 }}>
          <Button mode="secondary" disabled={busy} onClick={cancelEdit} stretched>
            Отмена
          </Button>
          <Button mode="primary" loading={busy} onClick={handleSave} stretched>
            Сохранить
          </Button>
        </Div>
      </Group>
    );
  }

  const active = data.presets.find((p) => p.is_active) || null;
  const slots = [];
  for (let i = 0; i < data.preset_slots; i++) {
    slots.push(data.presets[i] || null);
  }

  return (
    <>
      <SectionHead
        kind="trials" icon="⚔️" value={active ? active.name : 'нет'}
        label="активный пресет"
        aside={<>{data.presets.length}/{data.preset_slots}<br /><small>слотов занято</small></>}
      />
      <Group header={<Header>Пресеты</Header>}>
        <div className="card-list">
          {slots.map((preset, idx) => (preset ? (
            <div className={`preset-card${preset.is_active ? ' preset-card--active' : ''}`} key={preset.id}>
              <span className="preset-card__num">{idx + 1}</span>
              <div className="preset-card__body">
                <b className="preset-card__name">
                  {preset.name}
                  {preset.is_active && <span className="preset-card__badge">активен</span>}
                </b>
                <span className="preset-card__chips">
                  {preset.buff_ids.map((id) => <BuffChip key={id} buff={data.buffs.find((x) => x.id === id)} />)}
                </span>
                <span className="preset-card__actions">
                  {!preset.is_active && (
                    <button type="button" className="pill-btn pill-btn--main" disabled={busy} onClick={() => handleSwitch(preset.id)}>
                      Активировать
                    </button>
                  )}
                  <button type="button" className="pill-btn" disabled={busy} onClick={() => startEdit(preset)}>
                    ✎ Изменить
                  </button>
                </span>
              </div>
            </div>
          ) : (
            <button type="button" className="preset-card preset-card--empty" key={`empty-${idx}`} disabled={busy} onClick={() => startEdit(null)}>
              <span className="preset-card__num">{idx + 1}</span>
              <span className="preset-card__plus">+ Собрать пресет</span>
            </button>
          )))}
        </div>
      </Group>

      {data.next_slot_cost !== null && (
        <Div>
          <Button mode="secondary" loading={busy} onClick={handleBuySlot} stretched>
            Купить слот - {data.next_slot_cost} зол.
          </Button>
        </Div>
      )}

      {errorMsg && (
        <Div>
          <Text style={{ color: '#c81e3a' }}>{errorMsg}</Text>
        </Div>
      )}
    </>
  );
}
