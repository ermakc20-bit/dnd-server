import { useEffect, useRef, useState, type FormEvent } from "react";

import type {
  CampaignApi,
  CampaignSummary,
  GuestApi,
  GuestSession,
  InviteSummary,
  ParticipantSummary,
  ParticipantStatus,
  RoomSecurityPage,
  RoomSummary,
} from "./api";
import { CampaignApiError, campaignApi } from "./api";
import { supabase } from "../../lib/supabase";
import "./campaigns.css";
import { TransferPanel } from "../campaign-transfer/TransferPanel";
import type { TransferApi } from "../campaign-transfer/api";
import { useDevice } from "../../app/useDevice";
import { Icon } from "../../components/Icon";

export function CampaignHome({
  accessToken,
  api = campaignApi,
  onOpenRoom,
  transferApi,
}: {
  accessToken: string;
  api?: CampaignApi;
  onOpenRoom?(room: RoomSummary): void;
  transferApi?: TransferApi;
}) {
  const phone = useDevice() === "phone";
  const [campaigns, setCampaigns] = useState<CampaignSummary[] | null>(null);
  const [creating, setCreating] = useState(false);
  const [saving, setSaving] = useState(false);
  const [name, setName] = useState("");
  const [systemId, setSystemId] = useState("neutral");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    void api.listCampaigns(accessToken).then(
      (items) => active && setCampaigns(items),
      (reason: unknown) => active && setError(errorMessage(reason)),
    );
    return () => {
      active = false;
    };
  }, [accessToken, api]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (phone || saving || !name.trim()) return;
    setSaving(true);
    setError(null);
    try {
      const campaign = await api.createCampaign(accessToken, name.trim(), systemId);
      setCampaigns((current) => [...(current ?? []), campaign]);
      setCreating(false);
      setName("");
      if (campaign.rooms[0]) onOpenRoom?.(campaign.rooms[0]);
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setSaving(false);
    }
  }

  if (campaigns === null && error === null) {
    return <main className="campaign-page campaign-page--center">Загружаем кампании…</main>;
  }

  return (
    <main className="campaign-page campaign-home">
      <nav className="workspace-nav" aria-label="Раздел сервиса">
        <a href="/" aria-current="page"><Icon name="map" />Кампании</a>
        <span>Ваши приключения</span>
      </nav>
      <header className="campaign-header">
        <div>
          <h1>Кампании</h1>
          <p>Выберите стол, чтобы продолжить игру или подготовку.</p>
        </div>
        {!phone ? <div className="campaign-header-actions">
          <TransferPanel accessToken={accessToken} api={transferApi} onImported={() => {
            void api.listCampaigns(accessToken).then(setCampaigns, (reason: unknown) => setError(errorMessage(reason)));
          }} />
          {campaigns && campaigns.length > 0 ? <button type="button" onClick={() => setCreating(true)}><Icon name="plus" size={18} />Создать кампанию</button> : null}
        </div> : null}
      </header>

      {error ? <p className="campaign-error" role="alert">{error}</p> : null}
      {phone ? <p className="phone-notice">Телефон — для участия: карточки, ресурсы, кубы и журнал. Подготовьте кампанию на компьютере.</p> : null}

      {campaigns?.length === 0 && !creating ? (
        <section className="campaign-empty">
          <h2>Создайте первый стол</h2>
          <p>Кампания сохранится как черновик. Карту, сетку и карточки можно добавить позже.</p>
          {!phone ? <button type="button" onClick={() => setCreating(true)}>Создать кампанию</button> : <p>Откройте приглашение мастера или существующий стол.</p>}
        </section>
      ) : null}

      {creating && phone ? <p role="status">Черновик кампании сохранён в этой вкладке. Продолжите подготовку на большом экране.</p> : null}
      {creating && !phone ? (
        <form className="campaign-form" onSubmit={submit}>
          <h2>Новая кампания</h2>
          <label>
            Название кампании
            <input autoFocus required value={name} onChange={(event) => setName(event.target.value)} maxLength={120} />
          </label>
          <label>
            Игровой пакет
            <select value={systemId} onChange={(event) => setSystemId(event.target.value)}>
              <option value="neutral">Нейтральный</option>
              <option value="dnd_ru">D&amp;D-подобный (русский)</option>
            </select>
          </label>
          <div className="campaign-actions">
            <button type="submit" disabled={saving}>
              {saving ? "Сохраняем…" : "Сохранить кампанию"}
            </button>
            <button type="button" disabled={saving} className="button-secondary" onClick={() => setCreating(false)}>
              Отмена
            </button>
          </div>
        </form>
      ) : null}

      {campaigns && campaigns.length > 0 ? (
        <section className="campaign-grid" aria-label="Список кампаний">
          {campaigns.map((campaign) => (
            <article className="campaign-card" key={campaign.id}>
              <div className="campaign-card-visual">
              <img className="campaign-cover" src="/art/adventure-cover.jpg" alt="" width={2048} height={1024} />
              <div className="campaign-card-content">
              <div className="campaign-facts"><span className={`campaign-status campaign-status--${campaign.status}`}>{campaign.status === "draft" ? "Черновик" : campaign.status === "archived" ? "В архиве" : "Активна"}</span><p className="campaign-meta">{campaign.system_id === "dnd_ru" ? "D&D · русский" : "Без привязки к системе"}</p></div>
              <h2>{campaign.name}</h2>
              <p className="campaign-room-count">{campaign.rooms.length > 0 ? `Комнат: ${campaign.rooms.length}` : "Комнат пока нет"}</p>
              {onOpenRoom ? <div className="campaign-room-links">{campaign.rooms.map((room) => (
                <button key={room.id} type="button" onClick={() => onOpenRoom(room)}
                  aria-label={`Открыть стол ${room.name}`}><span>Продолжить игру<span className="campaign-room-name">{room.name}</span></span><Icon name="chevron" size={18} /></button>
              ))}</div> : null}
              </div>
              </div>
              {!phone && campaign.rooms.some(room => room.can_manage) ? <details className="campaign-settings">
                <summary><Icon name="settings" size={17} />Настройки и перенос<Icon name="chevron" size={16} /></summary>
                <div className="campaign-settings-body">
                <TransferPanel accessToken={accessToken} campaignId={campaign.id} api={transferApi} />
                <details className="campaign-next-steps"><summary>Подготовка кампании</summary>
                  <ol aria-label="Следующие шаги">
                    <li>Добавьте карту и настройте сетку</li>
                    <li>Импортируйте или создайте карточки</li>
                    <li>Отправьте защищённое приглашение</li>
                  </ol>
                </details>
                {campaign.rooms.filter((room) => room.can_manage).map((room) => (
                <RoomAdmin
                  key={room.id}
                  accessToken={accessToken}
                  api={api}
                  room={room}
                  onRoom={(room) => setCampaigns((current) =>
                    current?.map((item) => item.id === campaign.id
                      ? { ...item, rooms: item.rooms.map((old) => old.id === room.id ? room : old) }
                      : item) ?? [],
                  )}
                />
              ))}
                </div>
              </details> : null}
            </article>
          ))}
        </section>
      ) : null}
    </main>
  );
}

export function GuestJoin({
  inviteToken,
  accessToken,
  api = campaignApi,
  onSession,
}: {
  inviteToken: string;
  accessToken?: string;
  api?: GuestApi;
  onSession?(session: GuestSession): void;
}) {
  const [session, setSession] = useState<GuestSession | null>(null);
  const [checking, setChecking] = useState(true);
  const [displayName, setDisplayName] = useState("");
  const [pin, setPin] = useState("");
  const [accountEmail, setAccountEmail] = useState("");
  const [accountMessage, setAccountMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    void api.restoreGuest(inviteToken, accessToken).then(
      (restored) => {
        if (active) { setSession(restored); onSession?.(restored); }
      },
      (reason: unknown) => {
        if (active && (!(reason instanceof CampaignApiError) || ![401, 403, 404].includes(reason.status))) {
          setError(errorMessage(reason));
        }
      },
    ).finally(() => {
      if (active) setChecking(false);
    });
    return () => {
      active = false;
    };
  }, [accessToken, api, inviteToken, onSession]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      const confirmed = accessToken
        ? await api.joinRegistered(accessToken, inviteToken, displayName.trim(), pin || undefined)
        : await api.joinGuest(inviteToken, displayName.trim(), pin || undefined);
      setSession(confirmed);
      onSession?.(confirmed);
    } catch (reason) {
      setError(errorMessage(reason));
    }
  }

  async function sendAccountLink(event: FormEvent) {
    event.preventDefault();
    if (!supabase) {
      setAccountMessage("Вход с аккаунтом временно недоступен");
      return;
    }
    const { error: authError } = await supabase.auth.signInWithOtp({
      email: accountEmail,
      options: { emailRedirectTo: window.location.href },
    });
    setAccountMessage(authError
      ? "Не удалось отправить ссылку для входа"
      : "Ссылка отправлена. После входа вы вернётесь к этому приглашению.");
  }

  if (checking) {
    return <main className="campaign-page campaign-page--center">Восстанавливаем вход…</main>;
  }
  if (session) {
    return (
      <main className="campaign-page campaign-page--center journey-entry">
        <section className="guest-card">

          <h1>{session.room.name}</h1>
          <p>{session.participant.display_name}, мастер готовит игровую сцену.</p>
        </section>
      </main>
    );
  }
  return (
    <main className="campaign-page campaign-page--center journey-entry">
      <div className="guest-options">
        <form className="guest-card" onSubmit={submit}>

        <h1>Вход за игровой стол</h1>
        <p>{accessToken
          ? "Вход сохранится в вашем профиле. Укажите имя, под которым вас увидит группа."
          : "Аккаунт не нужен. Укажите имя, под которым вас увидит группа."}</p>
        <label>
          Ваше имя
          <input
            value={displayName}
            onChange={(event) => setDisplayName(event.target.value)}
            maxLength={80}
            required
          />
        </label>
        <label>
          PIN, если мастер его включил
          <input
            value={pin}
            onChange={(event) => setPin(event.target.value)}
            inputMode="numeric"
            maxLength={12}
          />
        </label>
        {error ? <p className="campaign-error" role="alert">{error}</p> : null}
        <button type="submit">Войти в комнату</button>
        </form>
        {!accessToken ? (
          <form className="guest-card guest-card--account" onSubmit={sendAccountLink}>
            <h2>Войти с аккаунтом — необязательно</h2>
            <p>Тогда участие сохранится в постоянном профиле.</p>
            <label>
              Почта
              <input
                type="email"
                value={accountEmail}
                onChange={(event) => setAccountEmail(event.target.value)}
                required
              />
            </label>
            <button type="submit" className="button-secondary">Продолжить с аккаунтом</button>
            {accountMessage ? <p role="status">{accountMessage}</p> : null}
          </form>
        ) : null}
      </div>
    </main>
  );
}

function errorMessage(reason: unknown): string {
  return reason instanceof Error ? reason.message : "Сервер временно недоступен";
}

export function RoomAdmin({
  accessToken,
  api,
  room,
  onRoom,
  disabled = false,
}: {
  accessToken: string;
  api: CampaignApi;
  room: RoomSummary;
  onRoom(room: RoomSummary): void;
  disabled?: boolean;
}) {
  const [invite, setInvite] = useState<InviteSummary | null>(null);
  const [pin, setPin] = useState("");
  const [participants, setParticipants] = useState<ParticipantSummary[]>([]);
  const [statuses, setStatuses] = useState<ParticipantStatus[]>([]);
  const [journal, setJournal] = useState<RoomSecurityPage | null>(null);
  const [busy, setBusy] = useState(false);
  const [denied, setDenied] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scope = `${room.id}:${accessToken}:${room.can_manage}`;
  const currentScope = useRef(scope); currentScope.current = scope;
  const generation = useRef(0);
  const participantRequest = useRef(0);
  useEffect(() => {
    generation.current++; setParticipants([]); setStatuses([]); setJournal(null);
    setInvite(null); setPin(""); setError(null); setDenied(false); setBusy(false);
    return () => { generation.current++; };
  }, [scope]);

  async function run(action: () => Promise<void>, write = true) {
    if (denied || !room.can_manage || (write && disabled)) return;
    const requestGeneration = generation.current;
    setError(null);
    try { await action(); } catch (reason) {
      if (currentScope.current !== scope || generation.current !== requestGeneration) return;
      if (reason instanceof CampaignApiError && [401,403].includes(reason.status)) {
        generation.current++; setDenied(true); setParticipants([]); setStatuses([]); setJournal(null);
        setInvite(null); setPin("");
      }
      setError(errorMessage(reason));
    }
  }

  async function loadParticipants() {
    const version = generation.current;
    const requestId = ++participantRequest.current;
    const current = () => currentScope.current === scope && version === generation.current
      && requestId === participantRequest.current;
    if (typeof api.listParticipants === "function") {
      const rows = await api.listParticipants(accessToken, room.id);
      if (!current()) return;
      setParticipants(rows);
    }
    if (api.listParticipantStatus) {
      const rows = await api.listParticipantStatus(accessToken, room.id);
      if (current()) setStatuses(rows);
    }
  }
  async function loadJournal(beforeId?: number) {
    if (!api.securityEvents || busy) return;
    const version = generation.current; setBusy(true);
    try {
      const page = await api.securityEvents(accessToken, room.id, beforeId);
      if (currentScope.current === scope && version === generation.current) setJournal(current => ({ ...page,
        events: beforeId ? [...(current?.events ?? []), ...page.events] : page.events }));
    } finally { if (currentScope.current === scope && version === generation.current) setBusy(false); }
  }
  async function loadInvite(rotate: boolean) {
    const version = generation.current;
    const value = await (rotate ? api.rotateInvite(accessToken, room.id) : api.issueInvite(accessToken, room.id));
    if (currentScope.current === scope && version === generation.current) setInvite(value);
  }
  async function changeRoom(change: { is_locked?: boolean; pin?: string; remove_pin?: boolean }) {
    const version = generation.current;
    const value = await api.updateRoomAccess(accessToken, room.id, change);
    if (currentScope.current === scope && version === generation.current) onRoom(value);
  }

  if (!room.can_manage) return null;

  return (
    <section className="room-admin" aria-label={`Управление комнатой ${room.name}`}>
      <h3>{room.name}</h3>
      <p role="status">
        {room.is_locked ? "Комната закрыта" : "Комната открыта"}
        {" · "}
        {room.pin_enabled ? "PIN включён" : "PIN выключен"}
      </p>
      <section className="access-section"><h4>Приглашение</h4><div className="campaign-actions">
        <button type="button" disabled={disabled || denied} onClick={() => void run(() => loadInvite(false))}>Выпустить приглашение</button>
        <button type="button" disabled={disabled || denied} className="button-secondary" onClick={() => void run(() => loadInvite(true))}>Перевыпустить</button>
        <button type="button" disabled={disabled || denied} className="button-secondary" onClick={() => void run(async () => {
          const version = generation.current;
          await api.revokeInvites(accessToken, room.id);
          if (currentScope.current === scope && version === generation.current) setInvite(null);
        })}>Отозвать</button>
      </div>
      {invite ? <output className="invite-link">{`${window.location.origin}/join/${invite.token}`}</output> : null}
      </section><section className="access-section"><h4>Доступ к комнате</h4><label>
        PIN комнаты
        <input disabled={disabled || denied} inputMode="numeric" value={pin} onChange={(event) => setPin(event.target.value)} />
      </label>
      <div className="campaign-actions">
        <button type="button" disabled={disabled || denied} onClick={() => void run(() => changeRoom({ pin }))}>Сохранить PIN</button>
        <button type="button" disabled={disabled || denied} className="button-secondary" onClick={() => void run(() => changeRoom({ remove_pin: true }))}>Убрать PIN</button>
        <button type="button" disabled={disabled || denied} className="button-secondary" onClick={() => void run(() => changeRoom({ is_locked: !room.is_locked }))}>{room.is_locked ? "Открыть комнату" : "Закрыть комнату"}</button>
      </div>
      </section><section className="access-section"><h4>Участники</h4><button type="button" disabled={denied} className="button-secondary" onClick={() => void run(loadParticipants, false)}>
        Показать участников
      </button>
      <ul>
        {statuses.map(participant => <li key={participant.id}>
          {participant.display_name} · {participant.role === "gm" ? "мастер" : "игрок"} · {participant.connection_status === "connected" ? "Подключён" : participant.connection_status === "disconnected" ? "Нет активного соединения" : "Статус неизвестен"}
          <ul>{participant.assigned_tokens.map(token => <li key={token.id}>{token.name} · {token.scene_name}</li>)}</ul>
          {participant.role !== "gm" ? <button type="button" disabled={disabled || denied} onClick={() => void run(async () => {
            await api.removeParticipant(accessToken, room.id, participant.id); await loadParticipants();
          })}>Удалить</button> : null}
        </li>)}
        {participants.filter(participant => !statuses.some(status => status.id === participant.id)).map((participant) => (
          <li key={participant.id}>
            {participant.display_name} · {participant.role === "gm" ? "мастер" : "игрок"}
            {participant.role !== "gm" ? (
              <button type="button" disabled={disabled || denied} onClick={() => void run(async () => {
                await api.removeParticipant(accessToken, room.id, participant.id);
                await loadParticipants();
              })}>Удалить</button>
            ) : null}
          </li>
        ))}
      </ul>
      <details className="help-disclosure"><summary>Как определяется статус</summary><p>Статус отражает живые соединения сервера. Время исчезновения lease не определяет точное время сетевого обрыва.</p></details></section>
      {api.securityEvents ? <button type="button" disabled={busy || disabled || denied} onClick={() => void run(() => loadJournal(), false)}>Журнал безопасности</button> : null}
      {journal ? <section aria-label="Журнал безопасности комнаты">
        {journal.events.length === 0 ? <p>Записей безопасности пока нет.</p> : <ol>{journal.events.map(event => <li key={event.id}>
          {event.type === "participant.joined" ? "Вход в комнату" : event.type === "connection.opened" ? "Подключение соединения" : "Отключение соединения"} · {event.display_name} · {new Date(event.occurred_at).toLocaleString("ru-RU")}
          {event.reason === "socket_closed_actor_connected" ? <span> · Другие соединения участника активны</span> : event.reason === "socket_closed_actor_unknown" ? <span> · Статус остальных соединений неизвестен</span> : null}
        </li>)}</ol>}
        {journal.next_before_id !== null ? <button type="button" disabled={busy || disabled || denied} onClick={() => void run(() => loadJournal(journal.next_before_id!), false)}>Более ранние записи</button> : null}
      </section> : null}
      {error ? <p role="alert" className="campaign-error">{error}</p> : null}
    </section>
  );
}
