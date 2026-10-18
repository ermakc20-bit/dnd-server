import { useEffect, useState } from "react";
import type { ParticipantSummary } from "../campaigns/api";
import { CardEditor } from "../cards/CardEditor";
import { importApi, ImportError, type Diagnostic, type Draft, type ImportJob, type SourceFragment } from "./api";
import "./import.css";

export function ImportPanel({ roomId, accessToken, canManage, disabled, hasScene, execute, players, onLoadPlayers }: {
  roomId: string; accessToken?: string; canManage: boolean; disabled: boolean; hasScene: boolean;
  execute(type: string, payload: Record<string, unknown>, onAcknowledged?: () => void): Promise<boolean>;
  players: ParticipantSummary[]; onLoadPlayers(): void;
}) {
  const [jobs, setJobs] = useState<ImportJob[]>([]);
  const [job, setJob] = useState<ImportJob | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [text, setText] = useState("");
  const [inputMode, setInputMode] = useState<"file" | "text">("file");
  const [sourceKind, setSourceKind] = useState<"file" | "text">("file");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [diagnostics, setDiagnostics] = useState<Diagnostic[]>([]);
  const [duplicate, setDuplicate] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [editing, setEditing] = useState<string | null>(null);
  const [reload, setReload] = useState(0);
  useEffect(() => {
    let active = true;
    if (canManage) void importApi.list(roomId, accessToken).then((result) => { if (active) setJobs(result); })
      .catch((reason: unknown) => { if (active) setError(reason instanceof Error ? reason.message : "Импорты недоступны"); });
    return () => { active = false; };
  }, [roomId, accessToken, canManage, reload]);
  if (!canManage) return null;
  const blocked = disabled || busy;
  const open = job?.status === "draft";
  const total = job?.draftset.drafts.filter((draft) => draft.included).reduce((sum, draft) => sum + draft.count, 0) ?? 0;
  function failure(reason: unknown) {
    setError(reason instanceof Error ? reason.message : "Импорт временно недоступен");
    if (reason instanceof ImportError) { setDiagnostics(reason.diagnostics); setDuplicate(reason.code === "duplicate_file"); }
  }
  async function operation(action: () => Promise<void>) {
    if (blocked) return;
    setBusy(true); setError(null);
    try { await action(); } catch (reason) { failure(reason); } finally { setBusy(false); }
  }
  function patch(key: string, change: Partial<Draft>) {
    setJob((current) => current ? { ...current, draftset: { ...current.draftset,
      drafts: current.draftset.drafts.map((draft) => draft.external_key === key ? { ...draft, ...change } : draft) } } : null);
    setDirty(true);
  }
  async function save(): Promise<ImportJob | null> {
    if (!job) return null;
    const saved = dirty ? await importApi.save(roomId, job, accessToken) : job;
    setJob(saved); setDirty(false); return saved;
  }
  async function upload(kind: "file" | "text", mode?: string) {
    if (kind === "file" && !file) return;
    setSourceKind(kind);
    const result = kind === "text" ? await importApi.paste(roomId, text, accessToken, mode)
      : await importApi.upload(roomId, file!, accessToken, mode);
    setJob(result); setDirty(false); setEditing(null); setDiagnostics([]); setDuplicate(false); setReload((n) => n + 1);
  }
  async function confirm() {
    const saved = await save();
    if (!saved) return;
    await execute("import.confirm", { job_id: saved.id, expected_job_version: saved.version }, () => {
      setJob((current) => current?.id === saved.id ? { ...current, status: "confirmed",
        draftset: { ...current.draftset, fragments: [] } } : current);
      setFile(null); setText(""); setDirty(false); setReload((n) => n + 1);
      void importApi.get(roomId, saved.id, accessToken).then((result) => setJob((current) => current?.id === saved.id ? result : current)).catch(failure);
    });
  }
  const edited = job?.draftset.drafts.find((draft) => draft.external_key === editing);
  return <section className="import-panel" aria-label="Импорт карточек">
    <header className="import-heading">{!job ? <img className="library-art" src="/art/adventure-journal.png" width={160} height={160} alt="" /> : null}<div><h2>{job ? "Проверьте карточки перед добавлением" : "Добавить готовые карточки"}</h2><p>{job ? "Выберите экземпляры, проверьте поля и подтвердите импорт." : "Сначала разбор источника, затем проверка. Карточки появятся в комнате после подтверждения."}</p></div></header>
    <details className="import-reference"><summary>Форматы, ограничения и шаблоны</summary>
    <p className="import-limits">До 5 МБ · 100 карточек · 200 экземпляров · обработка до 8 с.<br />Исходник удаляется после подтверждения, отмены или через 24 часа (очистка раз в минуту).</p>
    <div className="import-actions">{["xlsx", "docx"].map((format) => <button key={format} type="button" disabled={blocked}
      onClick={() => void operation(() => importApi.template(roomId, format, accessToken))}>Скачать {format.toUpperCase()} v1</button>)}</div>
    <details><summary>Какие документы поддерживаются</summary><p>JSON — каноническая карточка или набор schema_version + cards. XLSX и DOCX — формы выше. TXT, PDF и другой DOCX — только явная разметка: schema_version: 1, Карточка: ключ, Название: значение. PDF без распознаваемого текста не поддерживается. HTML — известные блоки Vampires / Old Russia. Сценарии не выполняются.</p></details>
    </details>
    <div className="import-source" hidden={Boolean(job)}>
    <div className="segmented-control" role="group" aria-label="Источник карточек"><button type="button" aria-pressed={inputMode === "file"} onClick={() => setInputMode("file")}>Из файла</button><button type="button" aria-pressed={inputMode === "text"} onClick={() => setInputMode("text")}>Вставить текст</button></div>
    <div hidden={inputMode !== "file"}><label>Файл карточек<input disabled={blocked || dirty} type="file" accept=".json,.xlsx,.docx,.txt,.pdf,.html,.htm"
      onChange={(event) => { setFile(event.target.files?.[0] ?? null); setDuplicate(false); setError(null); setDiagnostics([]); }} /></label>
    {file ? <p>{file.name} · {(file.size / 1024).toFixed(1)} КБ</p> : null}
    <button type="button" disabled={blocked || !file || dirty} onClick={() => void operation(() => upload("file"))}>{busy ? "Обрабатываем…" : "Разобрать файл"}</button>
    </div><div hidden={inputMode !== "text"}><label>Текст карточек<textarea aria-label="Текст карточек" disabled={blocked || dirty} value={text} rows={8}
      placeholder={"schema_version: 1\nКарточка: guard\nНазвание: Страж\nКоличество: 2"}
      onChange={(event) => { setText(event.target.value); setDuplicate(false); setError(null); setDiagnostics([]); }} /></label>
    <p className="import-limits">Вставьте явную разметку TXT. Неразмеченный текст показывается для проверки и не создаёт карточки.</p>
    <button type="button" disabled={blocked || dirty} onClick={() => void operation(() => upload("text"))}>Разобрать текст</button></div></div>
    {error ? <p role="alert">{error}</p> : null}
    {duplicate ? <div className="import-actions"><button disabled={blocked} onClick={() => void operation(() => upload(sourceKind, "update_drafts"))}>Обновить совпадающие черновики</button>
      <button disabled={blocked} onClick={() => void operation(() => upload(sourceKind, "new_instances"))}>Новые экземпляры</button></div> : null}
    <Diagnostics diagnostics={diagnostics} />
    <button type="button" disabled={blocked || dirty} onClick={() => { setReload((n) => n + 1);
      if (job) void operation(async () => { setJob(await importApi.get(roomId, job.id, accessToken)); setEditing(null); }); }}>Обновить импорты</button>
    {!job ? jobs.map((entry) => <button type="button" key={entry.id} disabled={blocked} onClick={() => { setJob(entry); setDirty(false); }}>
      Продолжить импорт · {entry.draftset.drafts.length} карточек · до {new Date(entry.expires_at).toLocaleString("ru-RU")}</button>) : null}
    {job ? <>
      <p role="status">{job.status === "confirmed" ? `Импорт подтверждён · карточек: ${job.card_ids.length || total}` : job.status === "cancelled" ? "Импорт отменён · исходник удалён" : job.status === "expired" ? "Срок черновика истёк · исходник удалён" : `Черновик v${job.version} · ${total} экземпляров${dirty ? " · есть несохранённые правки" : " · сохранён"}`}</p>
      <Diagnostics diagnostics={job.draftset.diagnostics} />
      <Fragments fragments={job.draftset.fragments?.filter((f) => f.external_key === null) ?? []} label="Непривязанный исходный текст" />
      {edited && open ? <>
        <CardEditor key={edited.external_key} initial={edited.card} disabled={blocked} players={players} onLoadPlayers={onLoadPlayers}
          onSave={async (card) => { patch(edited.external_key, { card }); setEditing(null); }} onCancel={() => setEditing(null)} />
        <Fragments fragments={job.draftset.fragments?.filter((f) => f.external_key === edited.external_key) ?? []} label={`Нераспознанный текст: ${edited.card.name}`} />
      </> : <ul className="import-drafts">
        {job.draftset.drafts.map((draft) => <li key={draft.external_key}>
          <h3>{draft.card.name}</h3><small>{draft.external_key}</small>
          <p>{draft.card.resources.map((r) => `${r.label}: ${r.current}/${r.max ?? "∞"}`).join(" · ") || "Ресурсы не указаны"}</p>
          <label><input type="checkbox" aria-label={`Включить: ${draft.card.name}`} disabled={blocked || !open} checked={draft.included}
            onChange={(event) => patch(draft.external_key, { included: event.target.checked })} />Включить в импорт</label>
          <label>Экземпляров<input aria-label={`Экземпляров: ${draft.card.name}`} type="number" min={1} max={200} disabled={blocked || !open} value={draft.count}
            onChange={(event) => patch(draft.external_key, { count: Math.max(1, Math.min(200, Number(event.target.value) || 1)) })} /></label>
          <label><input type="checkbox" aria-label={`Токен для: ${draft.card.name}`} disabled={blocked || !open || !hasScene} checked={draft.create_token}
            onChange={(event) => patch(draft.external_key, { create_token: event.target.checked })} />Создать отдельный токен каждому</label>
          {!hasScene ? <small>Сначала создайте сцену для токенов.</small> : null}
          <button type="button" disabled={blocked || !open} onClick={() => setEditing(draft.external_key)}>Редактировать: {draft.card.name}</button>
          <details><summary>Исходные поля</summary><ul>{Object.entries(draft.source).map(([field, source]) => <li key={field}>{field} · {source.section} · строка {source.row} · {source.field}</li>)}</ul></details>
          <Fragments fragments={job.draftset.fragments?.filter((f) => f.external_key === draft.external_key) ?? []} label={`Нераспознанный текст: ${draft.card.name}`} />
        </li>)}
      </ul>}
      {open ? <div className="import-actions import-confirm"><button disabled={blocked || !dirty || editing !== null} onClick={() => void operation(async () => { await save(); })}>Сохранить черновики</button>
        <button disabled={blocked || total < 1 || total > 200 || editing !== null || (!hasScene && job.draftset.drafts.some((d) => d.included && d.create_token))} onClick={() => void operation(confirm)}>Подтвердить импорт ({total})</button>
        <button disabled={blocked} onClick={() => void operation(async () => { setJob(await importApi.cancel(roomId, job, accessToken)); setDirty(false); setEditing(null); setFile(null); setText(""); setReload((n) => n + 1); })}>Отменить импорт и удалить исходник</button></div> : null}
      <button disabled={blocked || dirty} onClick={() => { setJob(null); setEditing(null); setReload((n) => n + 1); }}>Закрыть просмотр</button>
    </> : null}
  </section>;
}
function Fragments({ fragments, label }: { fragments: SourceFragment[]; label: string }) {
  return fragments.length ? <section className="import-fragments" aria-label={label}>
    <h3>{label}</h3><p>Текст не распознан как поля карточки. Проверьте его и перенесите нужные сведения в редакторе.</p>
    {fragments.map((fragment, index) => <div key={index}>
      <small>{fragment.section} · строка {fragment.row}</small><pre>{fragment.text}</pre>
    </div>)}
  </section> : null;
}
function Diagnostics({ diagnostics }: { diagnostics: Diagnostic[] }) {
  return diagnostics.length ? <ul className="import-diagnostics" aria-label="Диагностика импорта">{diagnostics.map((item, index) => <li key={index}>
    <strong>{{ error: "Ошибка", warning: "Предупреждение", info: "Информация" }[item.severity]}</strong> · {item.entity ?? "документ"} · {item.section} · строка {item.row} · {item.field}: {item.message}
  </li>)}</ul> : null;
}
