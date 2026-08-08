export function SceneViewport() {
  return (
    <section className="scene" aria-label="Игровая сцена">
      <div className="scene__grid" aria-hidden="true" />
      <div className="scene__empty">
        <span className="scene__eyebrow">Сцена готова</span>
        <h2>Добавьте карту из библиотеки</h2>
        <p>Следующий вертикальный срез подключит PixiJS, сетку и объекты сцены.</p>
        <button type="button">Открыть библиотеку</button>
      </div>
    </section>
  );
}
