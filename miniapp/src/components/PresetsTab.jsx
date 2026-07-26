import { useEffect, useState } from 'react';
import { Group, Header, Div, Text, Spinner, Placeholder, Button, Input, Checkbox } from '@vkontakte/vkui';
import { getPresets, savePreset, switchPreset, buyPresetSlot } from '../api.js';

const CATEGORY_LABELS = {
  damage: 'Урон',
  defense: 'Оборона',
  control_utility: 'Контроль/утилити',
  group_support: 'Поддержка группы',
};

export default function PresetsTab({ character }) {
  const [data, setData] = useState(null);
  const [status, setStatus] = useState('loading'); // loading | ready | error
  const [editingId, setEditingId] = useState(undefined); // undefined — не редактируем; null — новый; число — существующий
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

  if (!character.subclass) {
    return (
      <Placeholder icon={<div style={{ fontSize: 48 }}>⚔️</div>}>
        Твоя Метка ещё не обрела форму. Возвращайся, когда кровь потребует имени.
      </Placeholder>
    );
  }

  if (status === 'loading') {
    return (
      <Div style={{ display: 'flex', justifyContent: 'center', paddingTop: 48 }}>
        <Spinner size="l" />
      </Div>
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
      setErrorMsg('Не удалось сохранить: проверь состав (3-5 баффов, хотя бы один не-урон) и золото.');
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
      setErrorMsg('Не удалось переключить пресет.');
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
      setErrorMsg('Не хватило золота на слот.');
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
        <Div style={{ fontSize: 13, opacity: 0.7 }}>Выбери 3-5 баффов (хотя бы один — не урон):</Div>
        {data.buffs.map((b) => (
          <div className="stat-row" key={b.id}>
            <Checkbox disabled={!b.unlocked} checked={editBuffs.includes(b.id)} onChange={() => toggleBuff(b.id)}>
              {b.unlocked ? '' : '🔒 '}
              {b.name}
              <span style={{ opacity: 0.6 }}> · {CATEGORY_LABELS[b.category] || b.category}</span>
            </Checkbox>
          </div>
        ))}
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

  const slots = [];
  for (let i = 0; i < data.preset_slots; i++) {
    slots.push(data.presets[i] || null);
  }

  return (
    <>
      <Group
        header={
          <Header>
            Пресеты ({data.presets.length}/{data.preset_slots})
          </Header>
        }
      >
        {slots.map((preset, idx) => (
          <div className="stat-row" key={preset ? preset.id : `empty-${idx}`}>
            <div>
              <div className="stat-row__label">
                {preset ? `${preset.is_active ? '✅ ' : ''}${idx + 1}. ${preset.name}` : `${idx + 1}. Пусто`}
              </div>
              {preset && (
                <Text style={{ opacity: 0.7, fontSize: 13 }}>
                  {preset.buff_ids.map((id) => data.buffs.find((b) => b.id === id)?.name || id).join(', ')}
                </Text>
              )}
            </div>
            <div style={{ display: 'flex', gap: 6 }}>
              {preset ? (
                <>
                  {!preset.is_active && (
                    <Button mode="secondary" size="s" disabled={busy} onClick={() => handleSwitch(preset.id)}>
                      Активировать
                    </Button>
                  )}
                  <Button mode="tertiary" size="s" disabled={busy} onClick={() => startEdit(preset)}>
                    Изменить
                  </Button>
                </>
              ) : (
                <Button mode="secondary" size="s" disabled={busy} onClick={() => startEdit(null)}>
                  Собрать
                </Button>
              )}
            </div>
          </div>
        ))}
      </Group>

      {data.next_slot_cost !== null && (
        <Div>
          <Button mode="secondary" loading={busy} onClick={handleBuySlot} stretched>
            Купить слот — {data.next_slot_cost} зол.
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
