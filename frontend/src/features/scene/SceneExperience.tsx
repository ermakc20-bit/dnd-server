import { TableToolbar, tableTools, toolAvailable } from "../scene-tools/TableToolbar";
import { ToolsPanel } from "../scene-tools/ToolsPanel";
import { DicePanel } from "../dice/DicePanel";
import type { TableTool } from "../scene-tools/types";
import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";

import type { RendererFactory } from "../../renderer/PixiSceneRenderer";
import { campaignApi, type CampaignApi, type ParticipantSummary, type RoomSummary } from "../campaigns/api";
import { CardsPanel } from "../cards/CardsPanel";
import { ImportPanel } from "../card-import/ImportPanel";
import { connectRoom, type ConnectionDiagnostics, type RealtimeFactory, type RoomConnection } from "../realtime/transport";
import { emergencySnapshot, downloadEmergencySnapshot } from "../realtime/emergencySnapshot";
import type { ItemPreview } from "../../renderer/viewport";
import { sceneApi } from "./api";
import { SceneCanvas } from "./SceneCanvas";
import type { AssetMetadata, SceneApi, SceneCommand, SceneProjection } from "./types";
import "./scene.css";
import type { AbilitySelection } from "../ability-geometry/types";
import { RoomAdmin } from "../campaigns/CampaignExperience";
import { useDevice } from "../../app/useDevice";
import { Icon } from "../../components/Icon";
import "../../styles/product.css";

export function SceneExperience({ room, accessToken, api = sceneApi, rendererFactory, onBack,
  participantApi = campaignApi,
  realtimeFactory = connectRoom,
}: {
  room: RoomSummary; accessToken?: string; api?: SceneApi; rendererFactory?: RendererFactory;
  onBack?(): void;
  participantApi?: Pick<CampaignApi, "listParticipants">;
  realtimeFactory?: RealtimeFactory;
}) {
  const device = useDevice();
  const phone = device === "phone";
  const stageHost = useRef<HTMLElement | null>(null);
  const [projection, setProjection] = useState<SceneProjection | null>(null);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const inFlight = useRef(false);
  const [name, setName] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [assetUrls, setAssetUrls] = useState<ReadonlyMap<string, string>>(new Map());
  const [file, setFile] = useState<File | null>(null);
  const [prepared, setPrepared] = useState<AssetMetadata | null>(null);
  const [uploadKind, setUploadKind] = useState<"map" | "token">("map");
  const [uploading, setUploading] = useState(false);
  const [pendingCommand, setPendingCommand] = useState<SceneCommand | null>(null);
  const pendingRef = useRef<SceneCommand | null>(null);
  const pendingCompletion = useRef<{ commandId: string; onAcknowledged(): void } | null>(null);
  const [players, setPlayers] = useState<ParticipantSummary[]>([]);
  const [tab, setTab] = useState<"scene" | "cards" | "import" | "tools" | "people" | "dice">("scene");
  const [visited, setVisited] = useState<Set<string>>(new Set(["scene"]));
  const [panelOpen, setPanelOpen] = useState(false);
  const [cardEditing, setCardEditing] = useState(false);
  const [requestedCard, setRequestedCard] = useState<{ id: string; request: number } | null>(null);
  const [roomAccess, setRoomAccess] = useState(room);
  const panelButton = useRef<HTMLButtonElement | null>(null);
  const panelHost = useRef<HTMLElement | null>(null);
  const panelHeading = useRef<HTMLHeadingElement | null>(null);
  const activeTab = phone ? tab === "dice" ? "dice" : "cards" : tab;
  function openPanel(next: typeof tab) { setTab(next); setVisited(current => new Set([...current, next])); setPanelOpen(true); }
  useEffect(() => { if (panelOpen && !phone) panelHeading.current?.focus({ preventScroll: true }); }, [panelOpen, activeTab, phone]);
  useEffect(() => {
    const close = (event: KeyboardEvent) => { if (event.key === "Escape" && !event.defaultPrevented && panelOpen && !phone) { setPanelOpen(false); panelButton.current?.focus(); } };
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [phone, panelOpen]);
  useEffect(() => {
    if (!panelOpen || activeTab !== "tools") return;
    const outside = (event: PointerEvent) => {
      const target = event.target as HTMLElement;
      if (!panelHost.current?.contains(target) && !target.closest?.(".table-toolbox")) setPanelOpen(false);
    };
    document.addEventListener("pointerdown", outside);
    return () => document.removeEventListener("pointerdown", outside);
  }, [panelOpen, activeTab]);
  const [tool,setTool]=useState<TableTool>("select");
  const [annotationLabel,setAnnotationLabel]=useState("Метка");
  const [annotationVisibility,setAnnotationVisibility]=useState<"everyone"|"gm_only">("everyone");
  const connection = useRef<RoomConnection | null>(null);
  const [lastSync, setLastSync] = useState<string | null>(null);
  const [diagnostics, setDiagnostics] = useState<ConnectionDiagnostics>({ attempt: 0, lastConfirmedSyncAt: null, failureStartedAt: null });
  const [prolongedFailure, setProlongedFailure] = useState(false);
  const confirmed = useRef<ReturnType<typeof emergencySnapshot> | null>(null);
  const [remotePreview, setRemotePreview] = useState<ItemPreview | null>(null);
  const [presence, setPresence] = useState(0);
  const [abilitySelection,setAbilitySelection]=useState<AbilitySelection|null>(null);

  const load = useCallback(() => connection.current?.refresh() ?? Promise.resolve(false), []);

  useEffect(() => {
    setProjection(null); setConnected(false); setLastSync(null);
    confirmed.current = null; setPlayers([]); setAssetUrls(new Map()); setSelectedId(null);
    setDiagnostics({ attempt: 0, lastConfirmedSyncAt: null, failureStartedAt: null }); setProlongedFailure(false);
    setPendingCommand(null); pendingRef.current = null; pendingCompletion.current = null;
    const transport = realtimeFactory({ roomId: room.id, accessToken,
      onSnapshot: (snapshot) => { const at = new Date().toISOString();
        confirmed.current = snapshot.can_manage ? emergencySnapshot(snapshot, at) : null;
        setAbilitySelection(null);setProjection(snapshot); setLastSync(new Date(at).toLocaleTimeString("ru-RU"));
        if (!pendingRef.current) setError(null); },
      onState: (state, reason) => {
        setConnected(state === "connected");
        setDiagnostics(current => state === "connected"
          ? { attempt: 0, lastConfirmedSyncAt: new Date().toISOString(), failureStartedAt: null }
          : state === "revoked" ? { attempt: 0, lastConfirmedSyncAt: null, failureStartedAt: null }
          : { ...current, failureStartedAt: current.failureStartedAt ?? Date.now() });
        if(state!=="connected")setAbilitySelection(null);
        if (reason) setError(reason);
        if (state === "revoked") {
          setProjection(null); setAssetUrls(new Map()); setPlayers([]); setSelectedId(null);
          setPendingCommand(null); pendingCompletion.current = null; setFile(null); setPrepared(null);
          pendingRef.current = null;
          setPresence(0); setLastSync(null);
          confirmed.current = null; setProlongedFailure(false);
        }
      }, onPreview: setRemotePreview, onPresence: setPresence, onDiagnostics: setDiagnostics,
    });
    connection.current = transport;
    return () => { transport.close(); connection.current = null; };
  }, [room.id, accessToken, realtimeFactory]);

  useEffect(() => {
    setProlongedFailure(false);
    if (diagnostics.failureStartedAt === null) return;
    const remaining = Math.max(0, 30000 - (Date.now() - diagnostics.failureStartedAt));
    const timer = setTimeout(() => setProlongedFailure(true), remaining);
    return () => clearTimeout(timer);
  }, [diagnostics.failureStartedAt]);

  useEffect(() => {
    let active = true;
    const ids = [...new Set(projection?.items.map((item) => item.asset_id).filter((id) => id !== null) ?? [])];
    void Promise.all(ids.map(async (id) => {
      try { const grant = await api.download(room.id, id, accessToken); return [id, grant.url] as const; }
      catch (reason) { if (active) setError(message(reason)); return null; }
    })).then((entries) => {
      if (active) setAssetUrls(new Map(entries.filter((entry) => entry !== null)));
    });
    return () => { active = false; };
  }, [projection, api, room.id, accessToken]);

  async function send(command: SceneCommand): Promise<boolean> {
    if (inFlight.current) return false;
    inFlight.current = true; setSaving(true); setError(null);
    setPendingCommand(command);
    pendingRef.current = command;
    try {
      const result = await api.command(command, accessToken);
      if (result.error_code || result.status === "rejected") {
        setPendingCommand(null);
        pendingRef.current = null;
        if (pendingCompletion.current?.commandId === command.command_id) pendingCompletion.current = null;
        const reason = result.message ?? "Команда отклонена сервером";
        if (result.error_code === "stale_version") await load();
        setError(reason); return false;
      }
      setPendingCommand(null);
      pendingRef.current = null;
      const completion = pendingCompletion.current;
      if (completion?.commandId === command.command_id) {
        pendingCompletion.current = null;
        completion.onAcknowledged();
      }
      return await load();
    } catch (reason) {
      setConnected(false); connection.current?.reconnect(); setError(message(reason)); return false;
    } finally { inFlight.current = false; setSaving(false); }
  }

  async function execute(type: string, payload: Record<string, unknown>, onAcknowledged?: () => void) {
    if (!projection || !connected || pendingCommand || inFlight.current) return false;
    const command = { command_id: crypto.randomUUID(), room_id: room.id,
      actor_session_id: projection.actor_session_id,
      expected_aggregate_version: projection.aggregate_version, type, payload,
      client_sent_at: new Date().toISOString() };
    pendingCompletion.current = onAcknowledged ? { commandId: command.command_id, onAcknowledged } : null;
    return send(command);
  }

  async function create(event: FormEvent) {
    event.preventDefault();
    if (name.trim() && await execute("scene.create", { name: name.trim() })) setName("");
  }
  async function loadPlayers() {
    if (!accessToken || !projection?.can_manage) return;
    try {
      setPlayers((await participantApi.listParticipants(accessToken, room.id))
        .filter((participant) => participant.role === "player" && participant.removed_at === null));
    } catch (reason) { setError(message(reason)); }
  }
  async function upload() {
    if (!file || uploading || pendingCommand) return;
    if (!["image/jpeg", "image/png", "image/webp", "image/avif"].includes(file.type) || file.size <= 0 || file.size > 52428800) {
      setError("Выберите JPEG, PNG, WebP или AVIF до 50 МБ"); return;
    }
    setUploading(true); setError(null);
    try {
      const metadata = prepared ?? await api.prepareUpload(room.id, file, accessToken);
      setPrepared(metadata);
      const ready = metadata.status === "ready" ? metadata : await api.upload(metadata, file, accessToken);
      setPrepared(ready);
      if (!projection?.scene) {
        setError("Изображение сохранено. Сначала создайте сцену, затем добавьте его."); return;
      }
      const accepted = await execute("item.create", { kind: uploadKind, asset_id: ready.id,
        name: file.name.slice(0, 160), width: uploadKind === "map" ? ready.width : projection.scene.grid_size,
        height: uploadKind === "map" ? ready.height : projection.scene.grid_size,
        z_index: uploadKind === "map" ? -1000 : 0, is_locked: uploadKind === "map" });
      if (accepted) { setFile(null); setPrepared(null); }
    } catch (reason) { setError(message(reason)); }
    finally { setUploading(false); }
  }

  const selected = projection?.items.find((item) => item.id === selectedId);
  // Unrelated room events must not replace an in-progress form. Canonical edits
  // to this item still refresh every field from the authoritative snapshot.
  const selectedFormKey = selected ? JSON.stringify([selected.id, selected.x, selected.y,
    selected.width, selected.height, selected.rotation, selected.name, selected.z_index,
    selected.is_locked, selected.visibility, selected.owner_participant_id]) : undefined;
  const disabled = saving || uploading || !connected || pendingCommand !== null;
  const scene = projection?.scene;
  const workbench = panelOpen && (activeTab === "import" || activeTab === "cards" && cardEditing);
  function chooseTool(next: TableTool) {
    if (!toolAvailable(next, Boolean(scene), disabled, Boolean(projection?.can_manage))) return;
    setAbilitySelection(null); setTool(next);
    stageHost.current?.querySelector<HTMLElement>(".scene-canvas")?.focus({ preventScroll: true });
  }
  useEffect(() => {
    if (phone) return;
    const shortcut = (event: KeyboardEvent) => {
      if (event.defaultPrevented || event.metaKey || event.ctrlKey || event.altKey || workbench) return;
      const target = event.target as HTMLElement;
      if (target.closest?.("input, textarea, select, [contenteditable='true']")) return;
      const next = tableTools.find(entry => entry.key.toLowerCase() === event.key.toLowerCase());
      if (next && toolAvailable(next.id, Boolean(scene), disabled, Boolean(projection?.can_manage))) {
        event.preventDefault(); chooseTool(next.id);
      }
    };
    window.addEventListener("keydown", shortcut);
    return () => window.removeEventListener("keydown", shortcut);
  }, [phone, workbench, disabled, scene?.id, projection?.can_manage]);
  useEffect(() => {
    const host = stageHost.current?.querySelector<HTMLElement>(".scene-canvas");
    if (!host || typeof ResizeObserver === "undefined") return;
    // Pixi's existing resizeTo(host) follows window resize. Panels and onboarding
    // also resize the host without changing the browser viewport.
    const observer = new ResizeObserver(() => window.dispatchEvent(new Event("resize")));
    observer.observe(host);
    return () => observer.disconnect();
  }, [scene?.id, phone]);

  return (
    <main className={`scene-page product-table product-table--${device}`}>
      <header className="scene-header">
        <div className="table-location">
          {onBack ? <button type="button" className="table-back" onClick={onBack} aria-label="К кампаниям" title="К кампаниям"><Icon name="arrow" /></button> : null}
          <div><h1>{room.name}</h1></div>
        </div>
        {projection ? <div className="table-controls">
            <nav className="scene-tabs" aria-label="Панели стола">
              {!phone ? <button ref={activeTab === "scene" ? panelButton : undefined} type="button" title="Сцена" aria-pressed={(panelOpen || phone) && activeTab === "scene"} onClick={() => { if (!phone && panelOpen && activeTab === "scene") { setPanelOpen(false); panelButton.current?.focus(); } else openPanel("scene"); } }><Icon name="map" /><span>Сцена</span></button> : null}
              <button ref={activeTab === "cards" ? panelButton : undefined} type="button" title="Карточки" aria-pressed={(panelOpen || phone) && activeTab === "cards"} onClick={() => { if (!phone && panelOpen && activeTab === "cards") { setPanelOpen(false); panelButton.current?.focus(); } else openPanel("cards"); } }><Icon name="cards" /><span>Карточки</span></button>
              {phone ? <button type="button" aria-pressed={activeTab === "dice"} onClick={() => { if (!phone && panelOpen && activeTab === "dice") { setPanelOpen(false); panelButton.current?.focus(); } else openPanel("dice"); } }><Icon name="dice" /><span>Кубы и журнал</span></button> : null}
              {!phone ? <button ref={activeTab === "dice" ? panelButton : undefined} type="button" title="Кубы и журнал" aria-pressed={panelOpen && activeTab === "dice"} onClick={() => { if (!phone && panelOpen && activeTab === "dice") { setPanelOpen(false); panelButton.current?.focus(); } else openPanel("dice"); } }><Icon name="dice" /><span>Кубы</span></button> : null}
              {!phone && projection.can_manage ? <><button ref={activeTab === "import" ? panelButton : undefined} type="button" title="Импорт" aria-pressed={(panelOpen || phone) && activeTab === "import"} onClick={() => { if (!phone && panelOpen && activeTab === "import") { setPanelOpen(false); panelButton.current?.focus(); } else openPanel("import"); } }><Icon name="upload" /><span>Импорт</span></button>
                <button ref={activeTab === "people" ? panelButton : undefined} type="button" title="Участники" aria-pressed={(panelOpen || phone) && activeTab === "people"} onClick={() => { if (!phone && panelOpen && activeTab === "people") { setPanelOpen(false); panelButton.current?.focus(); } else openPanel("people"); } }><Icon name="people" /><span>Участники</span></button></> : null}
            </nav>
          </div> : null}
        <div className="scene-actions">
          {lastSync ? <p className={`table-connection${connected ? " table-connection--online" : ""}`} aria-label={connected ? "Связь установлена" : "Нет связи"} title={`Последняя синхронизация: ${lastSync}`}>
            <span className="connection-dot" aria-hidden="true" />{connected ? "Связь установлена" : "Нет связи"}
            {presence ? <span className="table-presence"><Icon name="people" size={16} />{presence}</span> : null}
          </p> : null}
          <button type="button" className="table-refresh" disabled={saving} onClick={() => void load()} aria-label="Обновить сцену" title="Обновить сцену"><Icon name="refresh" size={18} /></button>
        </div>
      </header>
      {error ? <p className="scene-error" role="alert">{error}</p> : null}
      {!connected && projection ? <p role="status">Только чтение · последнее подтверждённое состояние</p> : null}
      {!connected && diagnostics.failureStartedAt !== null ? <p role="status">Переподключение · попытка {diagnostics.attempt}</p> : null}
      {!connected && prolongedFailure && (projection?.can_manage || room.can_manage) ? <section aria-label="Диагностика связи">
        <p>Синхронизация не подтверждена более 30 секунд. Проверьте подключение и повторите соединение.</p>
        <p>Снимок содержит только последнее подтверждённое представление сцены. Файлы карты и полная кампания в него не входят.</p>
        {confirmed.current ? <button type="button" onClick={() => {
          if (confirmed.current) downloadEmergencySnapshot(confirmed.current);
        }}>Скачать аварийный снимок</button> : <p>Нет подтверждённого локального снимка для скачивания.</p>}
      </section> : null}
      {pendingCommand ? <button type="button" disabled={saving || !connected} onClick={() => void send(pendingCommand)}>
        Повторить неподтверждённую команду
      </button> : null}
      {phone ? <p className="phone-notice">Режим участия · карточки, ресурсы, кубы и журнал. Карта и подготовка доступны на планшете или компьютере.</p> : null}
      {!projection ? <p>{error ? "Сцена недоступна. Повторите загрузку." : "Загружаем сцену…"}</p> : (
        <div className={`scene-workspace${panelOpen && activeTab !== "tools" ? " scene-workspace--inspecting" : ""}${workbench ? " scene-workspace--preparing" : ""}`}>
          {!phone ? <section ref={stageHost} className="scene-stage" aria-label="Игровая сцена">
            <div className="scene-stage-heading">
              <h2>{scene?.name ?? (projection.can_manage ? "Пустой стол" : "Мастер готовит сцену")}</h2>
              <output>{projection.items.length} объектов</output>
            </div>
            <TableToolbar tool={tool} onTool={chooseTool} hasScene={Boolean(scene)} disabled={disabled} canManage={projection.can_manage}
              settingsOpen={panelOpen && activeTab === "tools"} settingsRef={activeTab === "tools" ? panelButton : undefined}
              onSettings={() => { if (panelOpen && activeTab === "tools") { setPanelOpen(false); panelButton.current?.focus(); } else openPanel("tools"); }} />
            {selected ? <div className="selection-bar" role="toolbar" aria-label="Выбранный объект на карте"><span>{selected.name || "Без названия"}</span>{selected.card_id ? <button type="button" onClick={() => { setRequestedCard({ id: selected.card_id!, request: Date.now() }); openPanel("cards"); }}><Icon name="cards" size={16} />Карточка</button> : null}<button type="button" onClick={() => openPanel("scene")}><Icon name="settings" size={16} />Свойства</button><button className="icon-button" type="button" aria-label="Снять выделение" onClick={() => setSelectedId(null)}><Icon name="close" size={16} /></button></div> : null}
            {scene ? <SceneCanvas projection={projection} assetUrls={assetUrls} disabled={disabled}
              selectedId={selectedId} onExitTool={() => setTool("select")} tool={tool} onToolCommand={(type,payload)=>void execute(type,payload)}
              annotationLabel={annotationLabel} annotationVisibility={annotationVisibility}
              abilitySelection={abilitySelection} onAbilityCancel={()=>setAbilitySelection(null)}
              onAbilityCommand={(type,payload)=>void execute(type,payload,()=>setAbilitySelection(null))}
              remotePreview={remotePreview} onPreview={(preview) => connection.current?.preview(preview)}
              onSelect={(item) => setSelectedId(item?.id ?? null)}
              onMove={(id, position) => void execute("item.update", { item_id: id, ...position })}
              factory={rendererFactory} onAssetError={setError} /> : (
              <div className="scene-empty"><div className="scene-empty-content">
                <Icon name="map" size={44} />
                <h2>{projection.can_manage ? "Добавьте первую сцену" : "Скоро начнём"}</h2>
                <p>{projection.can_manage ? "Назовите сцену, затем добавьте карту. Карточки и приглашения можно подготовить в любой момент." : "Участие подтверждено. Ждём мастера."}</p>
                {projection.can_manage ? <button type="button" onClick={() => openPanel("scene")}><Icon name="plus" size={18} />Добавить сцену</button> : null}
              </div></div>
            )}
          </section> : null}
          <aside ref={panelHost} className={`scene-sidebar scene-sidebar--${activeTab}${panelOpen || phone ? "" : " scene-sidebar--closed"}`} aria-label="Инструменты сцены" aria-hidden={!panelOpen && !phone} inert={!panelOpen && !phone}>
            {!phone ? <header className="work-panel-header">
              <h2 ref={panelHeading} tabIndex={-1}>{({ scene: "Сцена и объекты", cards: "Карточки", import: "Импорт карточек", tools: "Параметры инструмента", people: "Участники и доступ", dice: "Кубы и журнал" })[activeTab]}</h2>
              <button type="button" className="icon-button" aria-label="Свернуть панель" title="Закрыть · Esc" onClick={() => { setPanelOpen(false); panelButton.current?.focus(); }}><Icon name="close" size={18} /></button>
            </header> : null}
            <div className="scene-panel-body">
            <div hidden={phone || activeTab !== "scene"}>
            {scene || projection.items.length > 0 ? <><h3 className="section-heading">Объекты <span>{projection.items.length}</span></h3>
            <label>Выбранный объект<select value={selectedId ?? ""} onChange={(event) => setSelectedId(event.target.value || null)}>
              <option value="">Выберите на карте или в списке</option>
              {projection.items.map((item) => <option key={item.id} value={item.id}>{item.name || "Без названия"}{item.is_locked ? " · заблокирован" : ""}</option>)}
            </select></label>
            {selected ? <form key={selectedFormKey} className="scene-form"
              onSubmit={(event) => { event.preventDefault(); const values = new FormData(event.currentTarget);
                const payload: Record<string, unknown> = { item_id: selected.id };
                for (const key of ["x", "y", "width", "height", "rotation"]) payload[key] = Number(values.get(key));
                if (projection.can_manage) Object.assign(payload, { name: String(values.get("name")),
                  z_index: Number(values.get("layer")), is_locked: values.has("locked"),
                  visibility: values.get("visibility"), owner_participant_id: values.get("owner") || null });
                void execute("item.update", payload); }}>
              <h3>{selected.name}</h3>
              {!selected.can_transform ? <p>Просмотр · управление не назначено или объект заблокирован.</p> : null}
              {projection.can_manage ? <label>Название объекта<input name="name" defaultValue={selected.name} maxLength={160} /></label> : null}
              {(["x", "y", "width", "height", "rotation"] as const).map((key) => (
                <label key={key}>{({ x: "X", y: "Y", width: "Ширина", height: "Высота", rotation: "Поворот, °" })[key]}
                  <input name={key} type="number" step="any" min={key === "width" || key === "height" ? 0.01 : -1000000}
                    max={1000000} defaultValue={selected[key]} required /></label>
              ))}
              {projection.can_manage ? <>
                <label>Слой<input name="layer" type="number" defaultValue={selected.z_index} required /></label>
                <label>Видимость<select name="visibility" defaultValue={selected.visibility}>
                  <option value="everyone">Всем</option><option value="gm_only">Только мастеру</option><option value="owner_only">Назначенному игроку</option>
                </select></label>
                <button type="button" disabled={disabled || !accessToken} onClick={() => void loadPlayers()}>Загрузить игроков</button>
                <label>Управление токеном<select name="owner" defaultValue={selected.owner_participant_id ?? ""}>
                  <option value="">Только мастер · управление отозвано</option>
                  {selected.owner_participant_id && !players.some((player) => player.id === selected.owner_participant_id)
                    ? <option value={selected.owner_participant_id}>Назначенный участник · загрузите список</option> : null}
                  {players.map((player) => <option key={player.id} value={player.id}>{player.display_name}</option>)}
                </select></label>
                <label className="scene-checkbox"><input name="locked" type="checkbox" defaultChecked={selected.is_locked} />Заблокирован</label>
                <button type="button" disabled={disabled} onClick={() => void execute("item.duplicate", { item_id: selected.id })}>Дублировать токен</button>
                <button type="button" disabled={disabled} onClick={() => void execute("item.delete", { item_id: selected.id }, () => setSelectedId(null))}>Удалить токен в корзину</button>
              </> : null}
              <button type="submit" disabled={disabled || !selected.can_transform}>Сохранить трансформацию</button>
            </form> : null}
            </> : null}
            {projection.can_manage ? <>
              <details className="panel-section" open={!scene}><summary>Новая сцена</summary><form onSubmit={create} className="scene-form">
                <label>Название сцены<input value={name} maxLength={120}
                  onChange={(event) => setName(event.target.value)} required /></label>
                <button disabled={disabled || !name.trim()} type="submit">Создать сцену</button>
              </form></details>
              {projection.scenes.length ? <label>Активная сцена<select disabled={disabled} value={scene?.id ?? ""}
                onChange={(event) => void execute("scene.activate", { scene_id: event.target.value })}>
                {projection.scenes.map((entry) => <option key={entry.id} value={entry.id}>{entry.name}</option>)}
              </select></label> : null}
              {scene ? <details className="panel-section"><summary>Название сцены</summary><form key={`scene-${scene.id}-${projection.aggregate_version}`} className="scene-form"
                onSubmit={(event) => { event.preventDefault(); const values = new FormData(event.currentTarget);
                  void execute("scene.rename", { scene_id: scene.id, name: String(values.get("name")).trim() }); }}>
                <label>Новое название<input name="name" defaultValue={scene.name} required maxLength={120} /></label>
                <button disabled={disabled} type="submit">Переименовать сцену</button>
              </form></details> : null}
              {scene ? <details className="panel-section"><summary>Сетка и масштаб</summary><form key={`grid-${scene.id}-${projection.aggregate_version}`} className="scene-form"
                onSubmit={(event) => { event.preventDefault(); const values = new FormData(event.currentTarget);
                  void execute("scene.grid", { grid_size: Number(values.get("size")),
                    unit_size: Number(values.get("unit")), unit_label: String(values.get("label")),
                    grid_enabled: values.has("grid"), snap_enabled: values.has("snap") }); }}>
                <label>Размер клетки, px<input name="size" type="number" min={8} max={512} defaultValue={scene.grid_size} required /></label>
                <label>Единиц на клетку<input name="unit" type="number" min={0.01} max={10000} step="any" defaultValue={scene.unit_size} required /></label>
                <label>Единица измерения<input name="label" defaultValue={scene.unit_label} maxLength={24} required /></label>
                <label className="scene-checkbox"><input name="grid" type="checkbox" defaultChecked={scene.grid_enabled} />Показать сетку</label>
                <label className="scene-checkbox"><input name="snap" type="checkbox" defaultChecked={scene.snap_enabled} />Привязка к сетке</label>
                <button disabled={disabled} type="submit">Сохранить сетку</button>
              </form></details> : null}
              {scene ? <section className="scene-form" aria-label="Приватное изображение">
                <h3>Добавить изображение</h3>
                <p>JPEG · PNG · WebP · AVIF, до 50 МБ. Файл приватный.</p>
                <label>Тип изображения<select disabled={disabled} value={uploadKind} onChange={(event) => setUploadKind(event.target.value as "map" | "token")}>
                  <option value="map">Карта</option><option value="token">Токен</option>
                </select></label>
                <label>Файл изображения<input disabled={disabled} type="file" accept="image/jpeg,image/png,image/webp,image/avif"
                  onChange={(event) => { setFile(event.target.files?.[0] ?? null); setPrepared(null); }} /></label>
                {file ? <p>{file.name}{prepared ? " · метаданные сохранены" : ""}</p> : null}
                <button type="button" disabled={disabled || uploading || !file} onClick={() => void upload()}>
                  {uploading ? "Загружаем…" : prepared ? "Повторить / добавить изображение" : "Загрузить изображение"}
                </button>
              </section> : null}
              {scene ? <button type="button" disabled={disabled}
                onClick={() => void execute("item.create", { name: "Токен", width: scene.grid_size, height: scene.grid_size })}>
                Создать простой токен</button> : null}
            </> : null}

            </div>
            {visited.has("tools") ? <div hidden={phone || activeTab !== "tools"}><ToolsPanel projection={projection} disabled={disabled} execute={execute}
              tool={tool} label={annotationLabel} onLabel={setAnnotationLabel}
              visibility={annotationVisibility} onVisibility={setAnnotationVisibility}/></div> : null}
            {visited.has("dice") || phone ? <div hidden={activeTab !== "dice"}><DicePanel roomId={room.id} accessToken={accessToken} canManage={!phone && projection.can_manage}
                disabled={disabled} version={projection.aggregate_version} execute={execute}/></div> : null}
            {visited.has("cards") || phone ? <div hidden={activeTab !== "cards"}><CardsPanel roomId={room.id} accessToken={accessToken} canManage={projection.can_manage} auxiliary={phone} compact={!workbench} requestedCard={requestedCard} onEditingChange={setCardEditing}
              disabled={disabled} version={projection.aggregate_version} execute={execute} players={players}
              onLoadPlayers={() => void loadPlayers()} hasScene={Boolean(scene)} abilitySources={projection.items}
              onPresentAbility={phone ? undefined : selection=>{setTool("select");setAbilitySelection(selection);setPanelOpen(false);}} /></div> : null}
            {visited.has("import") && projection.can_manage ? <div hidden={phone || activeTab !== "import"}><ImportPanel roomId={room.id} accessToken={accessToken} canManage={projection.can_manage}
              disabled={disabled} execute={execute} players={players} hasScene={Boolean(scene)}
              onLoadPlayers={() => void loadPlayers()} /></div> : null}
            {visited.has("people") && projection.can_manage && accessToken ? <div hidden={phone || activeTab !== "people"} className="table-room-admin"><RoomAdmin room={roomAccess} accessToken={accessToken} api={campaignApi} onRoom={setRoomAccess} disabled={disabled} /></div> : null}
            </div>
          </aside>
        </div>
      )}
    </main>
  );
}

function message(reason: unknown): string { return reason instanceof Error ? reason.message : "Сцена временно недоступна"; }
