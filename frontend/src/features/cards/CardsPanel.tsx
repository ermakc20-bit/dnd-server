import { useEffect, useRef, useState } from "react";
import type { ParticipantSummary } from "../campaigns/api";
import { cardApi } from "./api";
import { Icon } from "../../components/Icon";
import { CardEditor } from "./CardEditor";
import { blankCard, editable, kinds, type Card, type CardData, type CardPage } from "./types";
import "./cards.css";
import type { AbilitySelection } from "../ability-geometry/types";
import type { SceneItem } from "../scene/types";

export function CardsPanel({ roomId, accessToken, canManage, disabled, version, execute, players, onLoadPlayers, hasScene, onPresentAbility, abilitySources = [], auxiliary = false, compact = false, requestedCard, onEditingChange }: {
  roomId: string; accessToken?: string; canManage: boolean; disabled: boolean; version: number;
  execute(type: string, payload: Record<string, unknown>, onAcknowledged?: () => void): Promise<boolean>;
  players: ParticipantSummary[]; onLoadPlayers(): void; hasScene: boolean;
  onPresentAbility?(selection:AbilitySelection):void;
  abilitySources?:readonly SceneItem[];
  auxiliary?: boolean; compact?: boolean; requestedCard?: { id: string; request: number } | null; onEditingChange?(editing: boolean): void;
}) {
  const [page, setPage] = useState<CardPage | null>(null);
  const [search, setSearch] = useState("");
  const [offset, setOffset] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [draft, setDraft] = useState<{ id?: string; data: CardData; baseVersion: number } | null>(null);
  const handledRequest = useRef<typeof requestedCard>(undefined);
  const [targetCard, setTargetCard] = useState<typeof requestedCard>(null);
  const [focusedCard, setFocusedCard] = useState<{ card: Card; scope: string } | null>(null);
  const focusScope = `${roomId}:${accessToken ?? ""}:${version}`;
  useEffect(() => { onEditingChange?.(Boolean(draft)); }, [Boolean(draft), onEditingChange]);
  useEffect(() => {
    if (!draft && requestedCard && requestedCard !== handledRequest.current) {
      handledRequest.current = requestedCard; setTargetCard(requestedCard); setSelected(requestedCard.id);
    }
  }, [requestedCard, draft]);
  useEffect(() => {
    if (!targetCard || selected !== targetCard.id) return;
    let active = true; setFocusedCard(null);
    void cardApi.get(roomId, targetCard.id, accessToken).then(card => {
      if (active) { setFocusedCard({ card, scope: focusScope }); setError(null); }
    }).catch(reason => { if (active) setError(reason instanceof Error ? reason.message : "Карточка недоступна"); });
    return () => { active = false; };
  }, [targetCard, selected, focusScope, roomId, accessToken]);
  const [draftError, setDraftError] = useState<string | null>(null);
  const [reload, setReload] = useState(0);
  const [loading, setLoading] = useState(true);
  const searchInput = useRef<HTMLInputElement | null>(null);
  const restoreSearch = useRef(false);
  const reader = useRef<HTMLDivElement | null>(null);
  const detailHeading = useRef<HTMLHeadingElement | null>(null);
  useEffect(() => {
    let active = true; setLoading(true);
    void cardApi.list(roomId, search, offset, accessToken).then((value) => {
      if (active) { setPage(value); setError(null); }
    }).catch((reason: unknown) => { if (active) setError(reason instanceof Error ? reason.message : "Карточки недоступны"); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [roomId, search, offset, accessToken, version, reload]);
  const card = targetCard?.id === selected ? focusedCard?.scope === focusScope ? focusedCard.card : undefined : page?.cards.find((entry) => entry.id === selected);
  const focusedSelection = useRef<string | null>(null);
  useEffect(() => {
    const key = selected ? `${selected}:${targetCard?.request ?? "library"}` : null;
    // A refreshed room snapshot may temporarily hide the authorized card. Only
    // an intentional selection should move focus back from the game canvas.
    if (!selected || draft) focusedSelection.current = null;
    if (selected && card && !draft && focusedSelection.current !== key) {
      focusedSelection.current = key;
      reader.current?.scrollTo?.(0, 0);
      detailHeading.current?.focus({ preventScroll: true });
    }
    if (!selected && restoreSearch.current) { restoreSearch.current = false; searchInput.current?.focus({ preventScroll: true }); }
  }, [selected, draft, card?.id, targetCard?.request]);
  const blocked = disabled || loading || error !== null;
  const linkedSources=abilitySources.filter(item=>item.kind==="token"&&item.card_id===card?.id);
  async function save(data: CardData) {
    if (draft?.id && draft.baseVersion !== version) {
      setDraftError("Состояние комнаты изменилось. Черновик сохранён в форме. Отмените редактирование и откройте актуальную карточку.");
      return;
    }
    const submittedDraft = draft;
    await execute(draft?.id ? "card.update" : "card.create", draft?.id ? { card_id: draft.id, card: data } : { card: data }, () => {
      setDraft((current) => current === submittedDraft ? null : current);
      setReload((value) => value + 1);
    });
  }
  async function exportCard(format: "json" | "html") {
    if (!card) return;
    try { await cardApi.export(roomId, card.id, format, accessToken); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Экспорт недоступен"); }
  }
  return <section className={`cards-panel${compact ? " cards-panel--play" : ""}`} aria-label="Карточки комнаты">
    {error ? <p role="alert">{error}</p> : null}
    {draftError ? <p role="alert">{draftError}</p> : null}
    <div className={`card-library${selected || (draft && !auxiliary) ? " card-library--selected" : ""}`}>
      <div className="card-browser">
        <div className="library-toolbar">
          <label className="library-search"><span>Поиск карточек</span><Icon name="search" size={17} /><input ref={searchInput} value={search} placeholder="Найти карточку…" maxLength={160} disabled={Boolean(draft) && !auxiliary} onChange={(event) => { setSearch(event.target.value); setOffset(0); setSelected(null); }} /></label>
          <button className="icon-button" type="button" aria-label="Обновить карточки" title="Обновить карточки" disabled={Boolean(draft) && !auxiliary} onClick={() => setReload((value) => value + 1)}><Icon name="refresh" size={17} /></button>
        </div>
        {canManage && !auxiliary ? <button className="library-create" type="button" disabled={disabled || error !== null || Boolean(draft)} onClick={() => { setDraftError(null); setDraft({ data: blankCard(), baseVersion: version }); }}><Icon name="plus" size={17} />Новая карточка</button> : null}
        {loading ? <p role="status">Загружаем карточки…</p> : null}
        {!loading && page?.cards.length === 0 ? <div className="library-empty"><h3>{search ? "Ничего не найдено" : "Карточек пока нет"}</h3><p>{search ? "Попробуйте другое имя или очистите поиск." : canManage ? "Создайте персонажа или импортируйте готовые карточки." : "Мастер ещё не открыл карточки."}</p></div> : null}
        <ul className="card-list">{page?.cards.map((entry) => <li key={entry.id}><button type="button" aria-pressed={entry.id === selected} disabled={Boolean(draft) && !auxiliary}
          onClick={() => setSelected(entry.id)}><span className="card-list-name">{entry.name}</span><small>{kinds[entry.kind]}</small><Icon name="chevron" size={15} /></button></li>)}</ul>
        {page && page.cards.length > 0 ? <div className="card-pages"><button type="button" aria-label="Предыдущие карточки" disabled={offset === 0 || Boolean(draft)} onClick={() => setOffset(Math.max(0, offset - 20))}>Назад</button>
          <span>{offset + 1}–{offset + page.cards.length}</span><button type="button" disabled={!page.has_more || Boolean(draft)} onClick={() => setOffset(offset + 20)}>Далее</button></div> : null}
      </div>
      <div ref={reader} className="card-reader">
        {draft ? <div hidden={auxiliary}><div className="editor-context"><h3>{draft.id ? "Редактирование карточки" : "Новая карточка"}</h3><span>Правки сохранятся при переключении панелей</span></div><CardEditor initial={draft.data} isNew={!draft.id} disabled={disabled || error !== null} players={players} onLoadPlayers={onLoadPlayers}
          onSave={save} onCancel={() => { setDraft(null); setDraftError(null); }} /></div> : null}
        {!draft || auxiliary ? <>
        {draft && auxiliary ? <p>Черновик подготовки сохранён в этой вкладке. Продолжите на большом экране.</p> : null}
        {!card ? <div className="reader-empty"><img className="library-art" src="/art/adventure-journal.png" width={160} height={160} alt="" /><h3>Выберите карточку</h3><p>Характеристики, ресурсы и способности откроются здесь.</p></div> : null}
      {card ? <article className="card-detail" aria-label={`Карточка ${card.name}`}>
        <button type="button" className="card-back" onClick={() => { restoreSearch.current = true; setSelected(null); }}><Icon name="arrow" size={16} />К списку карточек</button>
        <header className="card-detail-heading"><span className="card-kind">{kinds[card.kind]}</span><h3 ref={detailHeading} tabIndex={-1}>{card.name}</h3>{card.subtitle ? <p>{card.subtitle}</p> : null}</header>
        {card.can_edit_structure && !auxiliary ? <div className="card-actions">
          <button type="button" aria-label="Редактировать карточку" disabled={blocked} onClick={() => setDraft({ id: card.id, data: editable(card), baseVersion: version })}>Изменить</button>
          <button type="button" aria-label="Добавить токен карточки" title="Добавить токен карточки" disabled={blocked || !hasScene} onClick={() => void execute("item.create", { name: card.name, card_id: card.id, owner_participant_id: card.owner_participant_id, visibility: card.visibility })}>На сцену</button>
          <details className="card-more"><summary>Ещё</summary><div>
          <button type="button" disabled={blocked} onClick={() => void execute("card.clone", { card_id: card.id })}>Клонировать карточку</button>
          <button type="button" disabled={blocked} onClick={() => void execute("card.delete", { card_id: card.id }, () => { setSelected(null); setReload((value) => value + 1); })}>Удалить карточку в корзину</button>
          <p>Представление существующего персонажа использует ту же карточку. Для независимого экземпляра дублируйте токен.</p></div></details>
        </div> : <p>{card.can_edit_current ? "Можно менять только текущие ресурсы." : "Карточка доступна для просмотра."}</p>}
        <div className="card-resources">{card.resources.map((resource) => <form key={`${card.id}-${resource.key}-${card.version}`} className="card-resource" onSubmit={(event) => {
          event.preventDefault(); const value = new FormData(event.currentTarget).get("current");
          void execute("card.resource", { card_id: card.id, resource_key: resource.key, current: Number(value) });
        }}><label>{resource.label}<input aria-label={`Текущее: ${resource.label}`} name="current" type="number" step="any" min={0} max={resource.max ?? 1000000000}
          required defaultValue={resource.current} disabled={blocked || !card.can_edit_current} /></label>
          <span>из {resource.max ?? "∞"}</span><button type="submit" aria-label={`Сохранить ${resource.label}`} title={`Сохранить ${resource.label}`} disabled={blocked || !card.can_edit_current}><Icon name="check" size={17} /></button>
          {resource.max !== null && resource.max > 0 ? <progress aria-label={`${resource.label}: ${resource.current} из ${resource.max}`} value={resource.current} max={resource.max} /> : null}</form>)}</div>
        <details className="card-fields-disclosure" open={card.fields.length <= 12}><summary>Характеристики и сведения <span>{card.fields.length}</span></summary><dl className="card-stat-list">{[...card.fields].sort((a, b) => a.order - b.order).map((field) => <div key={field.key}><dt>{field.label}</dt><dd>{typeof field.value === "boolean" ? field.value ? "Да" : "Нет" : field.value ?? "—"}</dd></div>)}</dl></details>
        {card.skills.length ? <section className="card-read-section"><h4>Навыки</h4><ul>{card.skills.map((skill) => <li key={skill.key}>
          {skill.name}: {skill.bonus ?? "—"}{skill.proficient ? <> · <span>Владение</span></> : null}
          {skill.description ? <p>{skill.description}</p> : null}
        </li>)}</ul></section> : null}
        {card.abilities.length ? <section className="card-read-section"><h4>Способности и заклинания</h4>{card.abilities.map((ability) => <div key={ability.id}><details><summary>{ability.name}</summary>
          {ability.description ? <p>{ability.description}</p> : null}
          {ability.action_type ? <p>{ability.action_type}</p> : null}
          {ability.uses ? <p>{ability.uses.label}: {ability.uses.current} / {ability.uses.max ?? "∞"}</p> : null}
        </details>
          {!auxiliary&&ability.geometry&&onPresentAbility&&(card.can_edit_structure||card.can_edit_current)?
            ability.geometry.origin==="token"?linkedSources.map((item,index)=><button key={item.id} type="button" disabled={blocked||!hasScene}
              onClick={()=>onPresentAbility({cardId:card.id,ability,sourceTokenId:item.id})}>
              Показать область: {ability.name} · источник: {item.name||"Токен"}
              {linkedSources.filter(source=>source.name===item.name).length>1?` · представление ${index+1} (${item.x}, ${item.y})`:""}
            </button>):<button type="button" disabled={blocked||!hasScene}
              onClick={()=>onPresentAbility({cardId:card.id,ability})}>Показать область: {ability.name}</button>:null}</div>)}</section> : null}
        {card.inventory.length ? <details className="card-read-section" open={!compact}><summary>Инвентарь · {card.inventory.length}</summary><ul>{card.inventory.map((item) => <li key={item.id}>
          {item.icon ? <><span>{item.icon}</span> </> : null}{item.name} × {item.quantity ?? 1}
          {item.description ? <p>{item.description}</p> : null}
        </li>)}</ul></details> : null}
        {card.notes ? <section><h4>Заметки</h4><p>{card.notes}</p></section> : null}
        {card.can_export && !auxiliary ? <div className="card-actions"><button type="button" disabled={disabled} onClick={() => void exportCard("json")}>Скачать JSON</button>
          <button type="button" disabled={disabled} onClick={() => void exportCard("html")}>Скачать HTML</button><p>Экспорт — автономный снимок, без синхронизации.</p></div> : null}
      </article> : null}
      </> : null}
      </div>
    </div>
  </section>;
}
