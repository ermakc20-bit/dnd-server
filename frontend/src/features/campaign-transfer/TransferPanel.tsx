import { useEffect, useRef, useState } from "react";
import { TransferError, transferApi, type TransferApi, type TransferJob } from "./api";
import "./transfer.css";

const terminal = new Set(["completed", "failed", "cancelled", "expired", "cleanup_pending"]);
const phases: Record<string, string> = { receiving: "Загружаем ZIP", validating: "Проверяем весь архив",
  building: "Собираем снимок и изображения", storing: "Сохраняем новые изображения",
  committing: "Восстанавливаем кампанию", completed: "Готово", failed: "Перенос не выполнен",
  cancelled: "Перенос отменён", expired: "Срок задания истёк", cleanup_pending: "Удаляем временные изображения" };
const messages: Record<string, string> = {
  asset_unavailable: "Изображения временно недоступны. Исходная кампания сохранена.",
  unsafe_config: "Настройки содержат непереносимые поля. Исходная кампания сохранена.",
  interrupted: "Сервер прервал перенос. Новая кампания не создана.",
  upload_interrupted: "Загрузка прервана. Файл сохранён в форме.",
  archive_limit: "Архив превышает допустимый размер. Лимит ZIP — 256 МБ, изображения — 50 МБ.",
  archive_version: "Версия архива не поддерживается.",
  checksum: "Контрольные суммы не совпадают. Архив повреждён.",
};

export function TransferPanel({ accessToken, campaignId, onImported, api = transferApi }: {
  accessToken: string; campaignId?: string; onImported?(id: string): void; api?: TransferApi;
}) {
  const key = `vtt.transfer.${campaignId ?? "import"}`;
  const [opened, setOpened] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [history, setHistory] = useState(false);
  const [snapshot, setSnapshot] = useState(false);
  const [job, setJob] = useState<TransferJob | null>(null);
  const [id, setId] = useState<string | null>(() => sessionStorage.getItem(key));
  const [error, setError] = useState<string | null>(null);
  const [working, setWorking] = useState(false);
  const [checking, setChecking] = useState(false);
  const notified = useRef<string | null>(null);
  const latest = useRef<TransferJob | null>(null);
  const upload = useRef<AbortController | null>(null);
  const callback = useRef(onImported); callback.current = onImported;

  function accept(state: TransferJob) {
    const previous = latest.current;
    if (previous?.id === state.id && terminal.has(previous.phase) &&
      (!terminal.has(state.phase) || previous.phase === "completed" && state.phase !== "completed")) return false;
    latest.current = state;
    setJob(state); setError(null);
    if (state.phase === "completed" && state.kind === "import" && state.result_campaign_id && notified.current !== state.id) {
      notified.current = state.id; callback.current?.(state.result_campaign_id);
    }
    return true;
  }

  useEffect(() => {
    if (!id || working) return;
    let active = true; let timer: ReturnType<typeof setTimeout> | undefined;
    const refresh = async () => {
      try {
        const state = await api.get(id, accessToken);
        if (!active) return;
        if (!accept(state)) return;
        if (!terminal.has(state.phase) || state.phase === "cleanup_pending") timer = setTimeout(() => void refresh(), 750);
      } catch (reason) {
        if (!active) return;
        setError(reason instanceof Error ? reason.message : "Не удалось проверить статус.");
        if (reason instanceof TransferError && reason.code === "forbidden") {
          sessionStorage.removeItem(key); setId(null); setJob(null);
        } else timer = setTimeout(() => void refresh(), 1500);
      }
    };
    void refresh();
    return () => { active = false; if (timer) clearTimeout(timer); };
  }, [accessToken, api, id, working, key]);

  async function start() {
    if (working || id && (!job || !terminal.has(job.phase))) return;
    if (!campaignId && !file) return;
    if (!campaignId && file && (!file.name.toLowerCase().endsWith(".zip") || !file.size || file.size > 268435456)) {
      setError("Выберите ZIP кампании до 256 МБ"); return;
    }
    const next = crypto.randomUUID(); setId(next); sessionStorage.setItem(key, next);
    setWorking(true); setOpened(true); setError(null);
    const controller = new AbortController(); upload.current = controller;
    setJob({ id: next, kind: campaignId ? "export" : "import", phase: "receiving", progress: 0,
      cancel_requested: false, result_campaign_id: null, error_code: null, expires_at: "", archive_available: false });
    try { accept(campaignId ? await api.export(next, campaignId, history, snapshot, accessToken)
      : await api.import(next, file!, accessToken, controller.signal)); }
    catch (reason) { if (latest.current?.phase !== "cancelled") setError(reason instanceof Error ? reason.message : "Перенос временно недоступен."); }
    finally { upload.current = null; setWorking(false); }
  }

  async function check() {
    if (!id) return;
    setChecking(true);
    try { accept(await api.get(id, accessToken)); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Статус недоступен."); }
    finally { setChecking(false); }
  }

  async function cancel() {
    if (!id) return;
    try { const state = await api.cancel(id, accessToken); accept(state);
      if (state.phase === "cancelled") upload.current?.abort(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Проверяем отмену…"); }
  }

  async function download() {
    if (!id) return;
    try { await api.download(id, accessToken); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Не удалось скачать ZIP."); }
  }

  const busy = working || !!id && (!job || !terminal.has(job.phase) || job.phase === "cleanup_pending");
  const label = campaignId ? "Экспорт кампании" : "Импортировать кампанию";
  return <section className="transfer-panel" aria-label={label}>
    <button type="button" className="button-secondary" onClick={() => setOpened(!opened)}>{label}</button>
    {opened || id ? <div className="transfer-body">
      <p>{campaignId ? "Переносимый снимок включает все карточки, сцены и изображения. ZIP до 256 МБ; изображение до 50 МБ."
        : "ZIP восстановится как независимая кампания. Аккаунты и приглашения не переносятся. ZIP до 256 МБ; изображение до 50 МБ."}</p>
      {campaignId ? <>
        <label><input type="checkbox" checked={history} disabled={busy} onChange={e => setHistory(e.target.checked)} />Добавить последние 1000 событий</label>
        <label><input type="checkbox" checked={snapshot} disabled={busy} onChange={e => setSnapshot(e.target.checked)} />Добавить подтверждённый снимок</label>
      </> : <label>ZIP кампании<input type="file" accept=".zip,application/zip" disabled={busy}
        onChange={e => setFile(e.target.files?.[0] ?? null)} /></label>}
      <div className="transfer-actions">
        <button type="button" disabled={busy || !campaignId && !file}
          onClick={() => void start()}>{campaignId ? "Подготовить ZIP" : "Восстановить независимую кампанию"}</button>
        {busy ? <button type="button" className="button-secondary" onClick={() => void cancel()}>Отменить перенос</button> : null}
        {id ? <button type="button" className="button-secondary" disabled={checking} onClick={() => void check()}>Проверить статус</button> : null}
        {job?.archive_available ? <button type="button" onClick={() => void download()}>Скачать ZIP</button> : null}
      </div>
      {job ? <p role="status">{phases[job.phase] ?? "Проверяем статус"} · {job.progress}%
        {job.cancel_requested && !terminal.has(job.phase) ? " · Отмена запрошена" : ""}
        {job.phase === "completed" && job.kind === "import" ? job.result_campaign_id
          ? " · Создана независимая кампания" : " · Созданная кампания теперь недоступна" : ""}
        {job.phase === "completed" && job.kind === "export" && !job.archive_available ? " · ZIP больше недоступен; подготовьте заново" : ""}
        {job.phase === "cleanup_pending" ? " · Кампания не создана. Сервер повторит очистку, когда хранилище станет доступно." : ""}
      </p> : null}
      {job?.error_code && job.phase !== "cancelled" ? <p className="campaign-error" role="alert">
        {messages[job.error_code] ?? "Архив не прошёл проверку. Новая кампания не создана. Файл сохранён в форме."}</p> : null}
      {error ? <p className="campaign-error" role="alert">{error}</p> : null}
      {error && id ? <p>Сначала проверьте статус: потеря ответа не означает отмену импорта.</p> : null}
    </div> : null}
  </section>;
}
