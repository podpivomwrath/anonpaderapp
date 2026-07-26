import { useState } from 'react';
import { Tabs, TabsItem } from '@vkontakte/vkui';
import StatsTab from './StatsTab.jsx';
import PresetsTab from './PresetsTab.jsx';
import TrialsTab from './TrialsTab.jsx';

// Патч 14, ч.1: Характеристики + Пресеты + Испытания объединены в одну
// вкладку «Персонаж», переключаемые под-табами.
const SECTIONS = [
  { id: 'stats', label: 'Характеристики' },
  { id: 'presets', label: 'Пресеты' },
  { id: 'trials', label: 'Испытания' },
];

export default function CharacterTab({ character, onCharacterUpdate }) {
  const [section, setSection] = useState('stats');

  return (
    <>
      <Tabs>
        {SECTIONS.map((s) => (
          <TabsItem key={s.id} selected={section === s.id} onClick={() => setSection(s.id)}>
            {s.label}
          </TabsItem>
        ))}
      </Tabs>
      {section === 'stats' && <StatsTab character={character} onCharacterUpdate={onCharacterUpdate} />}
      {section === 'presets' && <PresetsTab character={character} />}
      {section === 'trials' && <TrialsTab />}
    </>
  );
}
