import { useEffect, useState } from 'react';
import { Group, Header, Div, Text, Placeholder, Button, Input } from '@vkontakte/vkui';
import { getPresets, savePreset, switchPreset, buyPresetSlot, rememberPresetRunes } from '../api.js';
import Skeleton from './Skeleton.jsx';
import { SectionHead } from './ui.jsx';

// Коды ошибок сервера, у которых нет человеческого текста на той стороне.
const ERROR_TEXTS = {
  not_enough_gold: 'Не хватило золота.',
  bad_request: 'Не удалось сохранить: проверьте название.',
};

// Руны-навыки (2026-11-10): микробаффов больше нет - пресет это имя и
// запомненная раскладка рун (навыки, огранки, руны героя и экипировки).
// Переключение в родном городе расставляет руны само.

// Склонялка рядом (как в CraftGear.jsx): 1 руна, 2 руны, 5 рун.
function runesWord(n) {
  const d = n % 10;
  if (d === 1 && n % 100 !== 11) return 'руна';
  return d >= 2 && d <= 4 && (n % 100 < 12 || n % 100 > 14) ? 'руны' : 'рун';
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
  const [busy, setBusy] = useState(false);
  const [errorMsg, setErrorMsg] = useState(null);
  const [note, setNote] = useState(null);

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
    setErrorMsg(null);
  }

  function cancelEdit() {
    setEditingId(undefined);
    setErrorMsg(null);
  }

  async function handleSave() {
    setBusy(true);
    setErrorMsg(null);
    try {
      await savePreset(editName.trim(), [], editingId ?? undefined);
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
    setNote(null);
    try {
      const res = await switchPreset(presetId);
      setNote(res?.note || null);
      load();
    } catch (err) {
      setErrorMsg(saveErrorText(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleRunes(presetId, keep) {
    setBusy(true);
    setErrorMsg(null);
    setNote(null);
    try {
      await rememberPresetRunes(presetId, keep);
      setNote(keep ? '🔮 Руны запомнены: при переключении на этот пресет в родном городе встанут сами.' : null);
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
        <Div style={{ fontSize: 13, opacity: 0.7 }}>
          {editingId === null
            ? 'Новый пресет сразу запомнит руны, что стоят у вас сейчас.'
            : 'Здесь меняется название. Чтобы пресет запомнил нынешние руны, нажмите «Запомнить руны».'}
        </Div>
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
                {preset.runes !== null && preset.runes !== undefined && (
                  <small className="preset-card__runes">
                    🔮 {preset.runes ? `Запомнено: ${preset.runes} ${runesWord(preset.runes)}` : 'Запомнено: без рун'}
                  </small>
                )}
                <span className="preset-card__actions">
                  {!preset.is_active && (
                    <button type="button" className="pill-btn pill-btn--main" disabled={busy} onClick={() => handleSwitch(preset.id)}>
                      Активировать
                    </button>
                  )}
                  <button type="button" className="pill-btn" disabled={busy} onClick={() => startEdit(preset)}>
                    ✎ Название
                  </button>
                  <button type="button" className="pill-btn" disabled={busy} onClick={() => handleRunes(preset.id, true)}>
                    🔮 Запомнить руны
                  </button>
                  {preset.runes !== null && preset.runes !== undefined && (
                    <button type="button" className="pill-btn" disabled={busy} onClick={() => handleRunes(preset.id, false)}>
                      Забыть руны
                    </button>
                  )}
                </span>
              </div>
            </div>
          ) : (
            <button type="button" className="preset-card preset-card--empty" key={`empty-${idx}`} disabled={busy} onClick={() => startEdit(null)}>
              <span className="preset-card__num">{idx + 1}</span>
              <span className="preset-card__plus">+ Запомнить раскладку</span>
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

      {note && (
        <Div>
          <Text>{note}</Text>
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
