export function PreparationSteps({ hasMap, onStep }: { hasMap: boolean; onStep(step: "scene" | "cards" | "import" | "people"): void }) {
  return <details className="preparation-steps">
    <summary>Подготовка первого стола</summary>
    <p>Готовая карта → сетка → карточки и токены → приглашение. Любой шаг можно пропустить и продолжить позже.</p>
    <ol>
      <li><button type="button" onClick={() => onStep("scene")}>1. Карта и сцена</button><span>{hasMap ? "Карта добавлена" : "Добавьте своё изображение"}</span></li>
      <li><button type="button" onClick={() => onStep("scene")}>2. Сетка</button><span>Проверьте размер клетки</span></li>
      <li><button type="button" onClick={() => onStep("import")}>3. Импорт карточек</button><button type="button" onClick={() => onStep("cards")}>Создать вручную</button></li>
      <li><button type="button" onClick={() => onStep("people")}>4. Пригласить игроков</button><span>Приглашение доступно в любой момент</span></li>
    </ol>
    <button type="button" onClick={() => onStep("people")}>Пропустить подготовку и продолжить</button>
  </details>;
}
