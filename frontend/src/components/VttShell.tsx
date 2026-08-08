import { SceneViewport } from "./SceneViewport";

const tools = ["Выбор", "Рука", "Указатель", "Линейка", "Рисование", "Туман"];

export function VttShell({ userLabel }: { userLabel: string }) {
  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <span className="brand-mark">D20</span>
          <strong>DnD VTT</strong>
        </div>
        <div className="room-state">
          <span className="room-state__dot" />
          Foundation room
        </div>
        <div className="user-chip">{userLabel}</div>
      </header>

      <aside className="toolbar" aria-label="Инструменты сцены">
        {tools.map((tool, index) => (
          <button
            className={index === 0 ? "toolbar__button toolbar__button--active" : "toolbar__button"}
            type="button"
            key={tool}
            aria-label={tool}
            title={tool}
          >
            {tool.slice(0, 1)}
          </button>
        ))}
      </aside>

      <SceneViewport />

      <aside className="inspector" aria-label="Инспектор">
        <span className="panel-label">Инспектор</span>
        <h3>Ничего не выбрано</h3>
        <p>Выберите объект на сцене, чтобы изменить его видимость, слой и положение.</p>
      </aside>

      <nav className="asset-dock" aria-label="Библиотека материалов">
        <button className="asset-dock__tab asset-dock__tab--active" type="button">Сцены</button>
        <button className="asset-dock__tab" type="button">Карты</button>
        <button className="asset-dock__tab" type="button">Персонажи</button>
        <button className="asset-dock__tab" type="button">Объекты</button>
        <button className="asset-dock__add" type="button">
          <span aria-hidden="true">＋</span>
          <span className="asset-dock__add-label">Добавить</span>
        </button>
      </nav>
    </main>
  );
}
