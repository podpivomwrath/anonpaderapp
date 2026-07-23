import { Placeholder } from '@vkontakte/vkui';

export default function StubTab({ text }) {
  return (
    <Placeholder className="stub-placeholder" icon={<div style={{ fontSize: 48 }}>🕯️</div>}>
      {text}
    </Placeholder>
  );
}
