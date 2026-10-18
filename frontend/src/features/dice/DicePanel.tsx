import { useEffect, useState } from "react";
import type { Execute } from "../scene-tools/types";
export interface JournalEntry { cursor:number; aggregate_version:number;actor_name:string;occurred_at:string;action:string;
  type:string;result:string;visibility:"everyone"|"gm_only"|"owner_only";can_undo:boolean;revoked?:boolean;
  roll:null|{expression:string;results:number[];modifier:number;total:number} }
interface JournalPage {entries:JournalEntry[];next_cursor:number|null}

export function DicePanel({roomId,accessToken,canManage,disabled,version,execute}: {
  roomId:string;accessToken?:string;canManage:boolean;disabled:boolean;version:number;execute:Execute;
}) {
  const [expression,setExpression]=useState("1d20");
  const [visibility,setVisibility]=useState("everyone");
  const [page,setPage]=useState<JournalPage>({entries:[],next_cursor:null});
  const [error,setError]=useState<string|null>(null);
  const [loading,setLoading]=useState(false);
  async function read(before=0) {
    setLoading(true);
    try {
      const response=await fetch(`/api/v1/rooms/${roomId}/journal?before_cursor=${before}&limit=30`,{
        credentials:"same-origin",headers:accessToken?{Authorization:`Bearer ${accessToken}`}:{}});
      if(!response.ok) throw new Error("Журнал временно недоступен");
      const incoming=await response.json() as JournalPage;
      if(!Array.isArray(incoming.entries)) throw new Error("Журнал временно недоступен");
      setPage(previous=>before?{...incoming,entries:[...previous.entries,...incoming.entries]}:incoming);setError(null);
    } catch(reason) {setError(reason instanceof Error?reason.message:"Журнал временно недоступен");}
    finally {setLoading(false);}
  }
  useEffect(()=>{let active=true;setPage({entries:[],next_cursor:null});
    // Read only while mounted; a late response from another room cannot replace this journal.
    const controller=new AbortController();
    void fetch(`/api/v1/rooms/${roomId}/journal?limit=30`,{signal:controller.signal,credentials:"same-origin",
      headers:accessToken?{Authorization:`Bearer ${accessToken}`}:{}}).then(async response=>{
        if(!response.ok)throw new Error("Журнал временно недоступен");const incoming=await response.json() as JournalPage;
        if(!Array.isArray(incoming.entries))throw new Error("Журнал временно недоступен");
        if(active){setPage(incoming);setError(null);}
      }).catch(()=>{if(active)setError("Журнал временно недоступен");});
    return ()=>{active=false;controller.abort();};
  },[roomId,accessToken,version]);
  return <section className="scene-form" aria-label="Кубы и журнал">
    <form className="dice-composer" onSubmit={event=>{event.preventDefault();void execute("dice.roll",{expression,visibility});}}>
      <label>Выражение кубов<input value={expression} maxLength={40} onChange={event=>setExpression(event.target.value)} required/></label>
      <div className="dice-presets" role="group" aria-label="Быстрый выбор куба">{["d4", "d6", "d8", "d10", "d12", "d20", "d100"].map(die => <button key={die} type="button" aria-pressed={expression === `1${die}`} onClick={() => setExpression(`1${die}`)}>{die}</button>)}</div>
      <details className="help-disclosure"><summary>Формула броска</summary><p>NdS±K · до 100 кубов, 1000 граней, модификатор ±10000. Например: 2d6+3.</p></details>
      {canManage?<label>Видимость броска<select value={visibility} onChange={event=>setVisibility(event.target.value)}>
        <option value="everyone">Всем</option><option value="gm_only">Только мастеру</option></select></label>:null}
      <button type="submit" disabled={disabled||!expression.trim()}>Бросить кубы</button></form>
    <h3>Журнал</h3><details className="help-disclosure"><summary>Какие действия можно отменить</summary><p>Отмена доступна мастеру для последнего действия: карточки, ресурсы, области способностей, связанные токены, удаление и копирование объектов, туман, метки, название и сетка сцены. Также можно отменить создание и смену сцен, обычные токены, карты и подтверждение импорта. Отмена броска сохраняет результат и помечает его отменённым мастером.</p></details>
    {error?<p role="status">{error}</p>:null}
    {page.entries.length===0?<p>Здесь появятся действия участников и серверные броски.</p>:null}
    <ol className="table-journal">{page.entries.map(entry=><li key={entry.cursor}>
      <strong>{entry.actor_name}</strong> · <time dateTime={entry.occurred_at}>{new Date(entry.occurred_at).toLocaleTimeString("ru-RU")}</time>
      <p>{entry.action} · {entry.visibility==="everyone"?"Всем":entry.visibility==="gm_only"?"Только мастеру":"Владельцу"} · версия {entry.aggregate_version}</p>
      {entry.revoked?<p>Бросок отменён мастером</p>:null}
      {entry.roll?<output className="dice-result">{entry.roll.expression}: [{entry.roll.results.join(", ")}] {entry.roll.modifier?`${entry.roll.modifier>0?"+":""}${entry.roll.modifier}`:""} = {entry.roll.total}</output>:null}
      {canManage?<button disabled={disabled||!entry.can_undo} onClick={()=>void execute("action.undo",{event_cursor:entry.cursor})}>
        {entry.can_undo?"Отменить последнее действие":"Необратимо / есть более новое действие"}</button>:null}
    </li>)}</ol>
    <button disabled={loading} onClick={()=>void read()}>Обновить журнал</button>
    {page.next_cursor?<button disabled={loading} onClick={()=>void read(page.next_cursor!)}>Более ранние действия</button>:null}
  </section>;
}
