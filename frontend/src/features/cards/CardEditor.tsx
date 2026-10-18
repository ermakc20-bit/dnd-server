import { flushSync } from "react-dom";
import { useState, type ReactNode, type FormEvent } from "react";
import { AbilityGeometryEditor } from "../ability-geometry/AbilityGeometryEditor";
import type { ParticipantSummary } from "../campaigns/api";
import { cardApi } from "./api";
import { kinds, type Ability, type CardData, type Resource, type Visibility } from "./types";

export function VisibilitySelect({ label, value, onChange }: { label: string; value: Visibility; onChange(value: Visibility): void }) {
  return <label>{label}<select value={value} onChange={(event) => onChange(event.target.value as Visibility)}>
    <option value="everyone">Всем</option><option value="owner_only">Назначенному игроку</option><option value="gm_only">Только мастеру</option>
  </select></label>;
}
const key = () => `custom_${crypto.randomUUID().replaceAll("-", "")}`;

function EditorEntry({ title, empty, children }: { title: string; empty: boolean; children: ReactNode }) {
  const [open, setOpen] = useState(empty);
  return <details className="card-entry" open={open} onToggle={(event) => setOpen(event.currentTarget.open)}>
    <summary>{title || "Без названия"}</summary><div className="entry-fields">{children}</div>
  </details>;
}

function revealInvalid(event: FormEvent<HTMLFormElement>) {
  let parent = (event.target as HTMLElement).parentElement;
  while (parent && parent !== event.currentTarget) {
    if (parent instanceof HTMLDetailsElement) parent.open = true;
    parent = parent.parentElement;
  }
}

export function CardEditor({ initial, disabled, players, onLoadPlayers, onSave, onCancel, isNew = false }: {
  initial: CardData; isNew?: boolean; disabled: boolean; players: ParticipantSummary[]; onLoadPlayers(): void;
  onSave(data: CardData): Promise<void>; onCancel(): void;
}) {
  const [card, setCard] = useState(initial);
  const [section, setSection] = useState("basics");
  const [visibilityChosen, setVisibilityChosen] = useState(!isNew);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  function patch(value: Partial<CardData>) { setCard((previous) => ({ ...previous, ...value })); }
  function patchAbility(index: number, change: Partial<Ability>) {
    patch({ abilities: card.abilities.map((entry, i) => i === index ? { ...entry, ...change } : entry) });
  }
  function patchUses(index: number, change: Partial<Resource>) {
    const uses = card.abilities[index]?.uses;
    if (uses) patchAbility(index, { uses: { ...uses, ...change } });
  }
  async function addDefaults() {
    setLoading(true); setError(null);
    try {
      const pack = await cardApi.schema(card.system_id);
      setCard((previous) => ({ ...previous, fields: [...previous.fields, ...pack.defaults.fields.filter((entry) => !previous.fields.some((existing) => existing.key === entry.key))],
        resources: [...previous.resources, ...pack.defaults.resources.filter((entry) => !previous.resources.some((existing) => existing.key === entry.key))],
        skills: [...previous.skills, ...pack.defaults.skills.filter((entry) => !previous.skills.some((existing) => existing.key === entry.key))] }));
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Пакет недоступен"); }
    finally { setLoading(false); }
  }
  return <form className="card-editor" onInvalidCapture={(event) => {
    const targetSection = (event.target as HTMLElement).closest<HTMLElement>("[data-editor-section]")?.dataset.editorSection;
    if (targetSection) flushSync(() => setSection(targetSection));
    revealInvalid(event);
  }} onSubmit={(event) => { event.preventDefault(); void onSave(card); }}>
    <fieldset disabled={disabled || loading}>
      <legend className="visually-hidden">Конструктор карточки</legend>
      <nav className="editor-navigation" aria-label="Разделы карточки">{[
        ["basics", "Основное"], ["fields", `Поля ${card.fields.length}`], ["resources", `Ресурсы ${card.resources.length}`],
        ["extra", "Навыки, инвентарь и способности"], ["notes", "Заметки"],
      ].map(([id, title]) => <button key={id} type="button" aria-pressed={section === id} onClick={() => setSection(id)}>{title}</button>)}</nav>
      <div data-editor-section="basics" hidden={section !== "basics"}><section className="editor-basics"><h3>Основное</h3><div className="editor-basics-grid">
      <label>Название карточки<input required maxLength={160} value={card.name} onChange={(event) => patch({ name: event.target.value })} /></label>
      <label>Вид карточки<select value={card.kind} onChange={(event) => {
        const kind = event.target.value as CardData["kind"];
        patch({ kind, ...(!visibilityChosen ? { visibility: kind === "npc" || kind === "mob" ? "gm_only" : "everyone" } : {}) });
      }}>
        {Object.entries(kinds).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      </select></label>
      <label>Подзаголовок<input value={card.subtitle ?? ""} maxLength={240} onChange={(event) => patch({ subtitle: event.target.value || null })} /></label>
      </div></section>
      <details className="editor-section"><summary>Игровой пакет и доступ</summary><div className="entry-fields">
      <label>Игровой пакет<select value={card.system_id} onChange={(event) => patch({ system_id: event.target.value })}>
        <option value="neutral">Нейтральный</option><option value="dnd-like">Приключения · d20</option>
      </select></label>
      <p>Поля необязательны. Пользовательские поля сохраняются при добавлении пакета.</p>
      <button type="button" onClick={() => void addDefaults()}>Добавить поля пакета</button>
      {error ? <p role="alert">{error}</p> : null}
      <VisibilitySelect label="Видимость карточки" value={card.visibility} onChange={(visibility) => { setVisibilityChosen(true); patch({ visibility }); }} />
      <button type="button" onClick={onLoadPlayers}>Обновить участников</button>
      <label>Назначить карточку<select value={card.owner_participant_id ?? ""} onChange={(event) => patch({ owner_participant_id: event.target.value || null })}>
        <option value="">Только мастер</option>
        {card.owner_participant_id && !players.some((player) => player.id === card.owner_participant_id)
          ? <option value={card.owner_participant_id}>Назначенный участник</option> : null}
        {players.map((player) => <option key={player.id} value={player.id}>{player.display_name}</option>)}
      </select></label>
      <label className="scene-checkbox"><input type="checkbox" checked={card.allow_player_export}
        onChange={(event) => patch({ allow_player_export: event.target.checked })} />Разрешить экспорт владельцу</label>
      </div></details></div>
      <section data-editor-section="fields" hidden={section !== "fields"} className="editor-section"><h3>Поля <span>{card.fields.length}</span></h3>
      {card.fields.map((field, index) => <EditorEntry title={field.label} empty={!field.label} key={field.key}>
        <label>Название поля {index + 1}<input required maxLength={120} value={field.label}
          onChange={(event) => patch({ fields: card.fields.map((entry, i) => i === index ? { ...entry, label: event.target.value } : entry) })} /></label>
        <label>Тип поля {index + 1}<select value={field.value_type} onChange={(event) => {
          const value_type = event.target.value as typeof field.value_type;
          patch({ fields: card.fields.map((entry, i) => i === index ? { ...entry, value_type, value: value_type === "text" ? "" : value_type === "number" ? 0 : false } : entry) });
        }}><option value="text">Текст</option><option value="number">Число</option><option value="boolean">Да / нет</option></select></label>
        <label>Значение поля {index + 1}<input type={field.value_type === "number" ? "number" : field.value_type === "boolean" ? "checkbox" : "text"}
          step="any" maxLength={10000} value={field.value_type === "boolean" ? undefined : String(field.value ?? "")}
          checked={field.value_type === "boolean" ? Boolean(field.value) : undefined}
          onChange={(event) => patch({ fields: card.fields.map((entry, i) => i === index ? { ...entry,
            value: field.value_type === "number" ? Number(event.target.value) : field.value_type === "boolean" ? event.target.checked : event.target.value } : entry) })} /></label>
        <VisibilitySelect label={`Видимость поля ${index + 1}`} value={field.visibility}
          onChange={(visibility) => patch({ fields: card.fields.map((entry, i) => i === index ? { ...entry, visibility } : entry) })} />
        <button type="button" onClick={() => patch({ fields: card.fields.filter((_, i) => i !== index) })}>Удалить поле {index + 1}</button>
      </EditorEntry>)}
      <button type="button" onClick={() => patch({ fields: [...card.fields, { key: key(), label: "", value: "", value_type: "text", visibility: "everyone", order: card.fields.length }] })}>Добавить поле</button>
      </section>
      <section data-editor-section="resources" hidden={section !== "resources"} className="editor-section"><h3>Ресурсы <span>{card.resources.length}</span></h3>
      {card.resources.map((resource, index) => <EditorEntry title={`${resource.label} · ${resource.current} / ${resource.max ?? "∞"}`} empty={!resource.label} key={resource.key}>
        <label>Название ресурса {index + 1}<input required maxLength={120} value={resource.label}
          onChange={(event) => patch({ resources: card.resources.map((entry, i) => i === index ? { ...entry, label: event.target.value } : entry) })} /></label>
        <label>Текущее ресурса {index + 1}<input type="number" required min={0} max={resource.max ?? 1000000000} step="any" value={resource.current}
          onChange={(event) => patch({ resources: card.resources.map((entry, i) => i === index ? { ...entry, current: Number(event.target.value) } : entry) })} /></label>
        <label>Максимум ресурса {index + 1}<input type="number" min={resource.current} max={1000000000} step="any" value={resource.max ?? ""}
          onChange={(event) => patch({ resources: card.resources.map((entry, i) => i === index ? { ...entry, max: event.target.value === "" ? null : Number(event.target.value) } : entry) })} /></label>
        <VisibilitySelect label={`Видимость ресурса ${index + 1}`} value={resource.visibility}
          onChange={(visibility) => patch({ resources: card.resources.map((entry, i) => i === index ? { ...entry, visibility } : entry) })} />
        <button type="button" onClick={() => patch({ resources: card.resources.filter((_, i) => i !== index) })}>Удалить ресурс {index + 1}</button>
      </EditorEntry>)}
      <button type="button" onClick={() => patch({ resources: [...card.resources, { key: key(), label: "", current: 0, max: null, color: null, visibility: "everyone" }] })}>Добавить ресурс</button>
      </section>
      <section data-editor-section="extra" hidden={section !== "extra"} className="editor-section"><h3>Навыки, инвентарь и способности</h3><h3>Навыки <span>{card.skills.length}</span></h3>
        {card.skills.map((skill, index) => <EditorEntry title={skill.name} empty={!skill.name} key={skill.key}>
          <label>Навык {index + 1}<input required value={skill.name} onChange={(event) => patch({ skills: card.skills.map((entry, i) => i === index ? { ...entry, name: event.target.value } : entry) })} /></label>
          <label>Бонус навыка {index + 1}<input type="number" step="any" value={skill.bonus ?? 0} onChange={(event) => patch({ skills: card.skills.map((entry, i) => i === index ? { ...entry, bonus: Number(event.target.value) } : entry) })} /></label>
          <label><input type="checkbox" checked={skill.proficient}
            onChange={(event) => patch({ skills: card.skills.map((entry, i) => i === index ? { ...entry, proficient: event.target.checked } : entry) })} />Владение навыком {index + 1}</label>
          <label>Описание навыка {index + 1}<textarea aria-label={`Описание навыка ${index + 1}`} maxLength={10000} value={skill.description ?? ""}
            onChange={(event) => patch({ skills: card.skills.map((entry, i) => i === index ? { ...entry, description: event.target.value || null } : entry) })} /></label>
          <button type="button" onClick={() => patch({ skills: card.skills.filter((_, i) => i !== index) })}>Удалить навык {index + 1}</button>
        </EditorEntry>)}
        <button type="button" onClick={() => patch({ skills: [...card.skills, { key: key(), name: "", bonus: 0, proficient: false, description: null, visibility: "everyone" }] })}>Добавить навык</button>
        <h3>Инвентарь <span>{card.inventory.length}</span></h3>
        {card.inventory.map((item, index) => <EditorEntry title={item.name} empty={!item.name} key={item.id}>
          <label>Предмет {index + 1}<input required value={item.name} onChange={(event) => patch({ inventory: card.inventory.map((entry, i) => i === index ? { ...entry, name: event.target.value } : entry) })} /></label>
          <label>Количество {index + 1}<input type="number" min={0} value={item.quantity ?? 1} onChange={(event) => patch({ inventory: card.inventory.map((entry, i) => i === index ? { ...entry, quantity: Number(event.target.value) } : entry) })} /></label>
          <label>Описание предмета {index + 1}<textarea aria-label={`Описание предмета ${index + 1}`} maxLength={10000} value={item.description ?? ""}
            onChange={(event) => patch({ inventory: card.inventory.map((entry, i) => i === index ? { ...entry, description: event.target.value || null } : entry) })} /></label>
          <label>Иконка предмета {index + 1}<input maxLength={120} value={item.icon ?? ""}
            onChange={(event) => patch({ inventory: card.inventory.map((entry, i) => i === index ? { ...entry, icon: event.target.value || null } : entry) })} /></label>
          <button type="button" onClick={() => patch({ inventory: card.inventory.filter((_, i) => i !== index) })}>Удалить предмет {index + 1}</button>
        </EditorEntry>)}
        <button type="button" onClick={() => patch({ inventory: [...card.inventory, { id: crypto.randomUUID(), name: "", quantity: 1, description: null, icon: null, visibility: "everyone" }] })}>Добавить предмет</button>
        <h3>Способности <span>{card.abilities.length}</span></h3>
        {card.abilities.map((ability, index) => <EditorEntry title={ability.name} empty={!ability.name} key={ability.id}>
          <label>Способность {index + 1}<input required value={ability.name} onChange={(event) => patch({ abilities: card.abilities.map((entry, i) => i === index ? { ...entry, name: event.target.value } : entry) })} /></label>
          <label>Описание способности {index + 1}<textarea maxLength={10000} value={ability.description} onChange={(event) => patch({ abilities: card.abilities.map((entry, i) => i === index ? { ...entry, description: event.target.value } : entry) })} /></label>
          <label>Тип действия способности {index + 1}<input maxLength={120} value={ability.action_type ?? ""}
            onChange={(event) => patchAbility(index, { action_type: event.target.value || null })} /></label>
          <label><input type="checkbox" checked={ability.uses !== null}
            onChange={(event) => patchAbility(index, { uses: event.target.checked
              ? { key: key(), label: "Использования", current: 0, max: null, color: null, visibility: "everyone" }
              : null })} />Отслеживать использования способности {index + 1}</label>
          {ability.uses ? <fieldset>
            <legend>Использования способности {index + 1}</legend>
            <label>Название использований способности {index + 1}<input required maxLength={120} value={ability.uses.label}
              onChange={(event) => patchUses(index, { label: event.target.value })} /></label>
            <label>Текущее использований способности {index + 1}<input type="number" required min={0} max={ability.uses.max ?? 1000000000} step="any" value={ability.uses.current}
              onChange={(event) => patchUses(index, { current: Number(event.target.value) })} /></label>
            <label>Максимум использований способности {index + 1}<input type="number" min={ability.uses.current} max={1000000000} step="any" value={ability.uses.max ?? ""}
              onChange={(event) => patchUses(index, { max: event.target.value === "" ? null : Number(event.target.value) })} /></label>
          </fieldset> : null}
          <VisibilitySelect label={`Видимость способности ${index + 1}`} value={ability.visibility}
            onChange={(visibility) => patch({ abilities: card.abilities.map((entry, i) => i === index ? { ...entry, visibility } : entry) })} />
          <AbilityGeometryEditor value={ability.geometry} index={index+1} onChange={geometry=>
            patch({abilities:card.abilities.map((entry,i)=>i===index?{...entry,geometry}:entry)})}/>
          <button type="button" onClick={() => patch({ abilities: card.abilities.filter((_, i) => i !== index) })}>Удалить способность {index + 1}</button>
        </EditorEntry>)}
        <button type="button" onClick={() => patch({ abilities: [...card.abilities, { id: crypto.randomUUID(), schema_version: 1, name: "", description: "", action_type: null, uses: null, geometry: null, automation: null, visibility: "everyone" }] })}>Добавить способность / заклинание</button>
      </section>
      <section data-editor-section="notes" hidden={section !== "notes"} className="editor-section"><h3>Заметки</h3><div className="entry-fields">
      <label>Заметки карточки<textarea maxLength={10000} value={card.notes ?? ""} onChange={(event) => patch({ notes: event.target.value || null })} /></label>
      <VisibilitySelect label="Видимость заметок" value={card.notes_visibility} onChange={(notes_visibility) => patch({ notes_visibility })} />
      </div></section>
      <div className="editor-footer"><button type="submit">Сохранить карточку</button>
      <button type="button" onClick={onCancel}>Отменить редактирование</button></div>
    </fieldset>
  </form>;
}
