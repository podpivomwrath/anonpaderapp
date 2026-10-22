/**
 * Заготовка раздела на время загрузки (2026-10-22): серые контуры блоков с
 * бегущим отблеском вместо пустоты и спиннера посреди экрана.
 */
export default function Skeleton({ rows = 4 }) {
  return (
    <div className="skeleton-list" aria-busy="true" aria-label="Загрузка">
      <div className="skeleton skeleton-line--short" />
      {Array.from({ length: rows }, (_, i) => <div key={i} className="skeleton skeleton-line" />)}
    </div>
  );
}
