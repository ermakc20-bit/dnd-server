import { useState } from "react";
import { tableTools } from "./TableToolbar";
import type { SceneProjection } from "../scene/types";
import type { Execute, TableTool } from "./types";

export function ToolsPanel({projection,disabled,execute,tool,label,onLabel,visibility,onVisibility}: {
  projection:SceneProjection;disabled:boolean;execute:Execute;tool:TableTool;
  label:string;onLabel(label:string):void;visibility:"everyone"|"gm_only";onVisibility(visibility:"everyone"|"gm_only"):void;
}) {
  const [selected,setSelected]=useState("");
  const annotation=projection.annotations?.find(mark=>mark.id===selected);
  return <section className="scene-form" aria-label="Инструменты стола">

    <h3 className="current-tool-name">{tableTools.find(entry => entry.id === tool)?.label}</h3>
    <p>{tool === "select" ? "Выберите объект на поле. Потяните пустое поле, чтобы переместить вид." : tool === "label" ? "Укажите текст, затем выберите место на поле." : tool === "fog.polygon" ? "Отметьте вершины на поле и завершите область." : "Выберите две точки на поле. Escape очищает черновик."}</p>
    {tool === "label" ? <label>Текст метки<input value={label} maxLength={160} onChange={event=>onLabel(event.target.value)}/></label> : null}
    {projection.can_manage && ["line", "arrow", "label"].includes(tool) ? <label>Видимость новых меток<select value={visibility} onChange={event=>onVisibility(event.target.value as "everyone"|"gm_only")}>
      <option value="everyone">Всем</option><option value="gm_only">Только мастеру</option></select></label>:null}
    <details className="help-disclosure"><summary>Как работать с инструментом</summary><p>Линия, стрелка, линейка и прямоугольник: выберите две точки. Метка: одну. Многоугольник: точки и «Завершить область». Клавиатура: стрелки двигают прицел, Enter ставит точку, Escape отменяет.</p></details>
    {projection.can_manage ? <section className="panel-section"><h3>Туман войны</h3><div className="card-actions"><button disabled={disabled || !projection.scene} onClick={()=>void execute("fog.fill",{})}>Закрыть сцену туманом</button>
      <button disabled={disabled || !projection.scene} onClick={()=>void execute("fog.reset",{})}>Снять туман</button></div></section>:null}
    <details className="panel-section"><summary>Метки на сцене · {projection.annotations?.length ?? 0}</summary><label>Выбранная метка<select value={selected} onChange={event=>setSelected(event.target.value)}>
      <option value="">Выберите метку</option>{projection.annotations?.map(mark=><option key={mark.id} value={mark.id}>{mark.label||({line:"Линия",arrow:"Стрелка",label:"Метка"}[mark.kind])}</option>)}
    </select></label>
    {annotation ? <form key={`${annotation.id}-${projection.aggregate_version}`} onSubmit={event=>{
      event.preventDefault(); const data=new FormData(event.currentTarget);
      const points=annotation.points.map((_,index)=>({x:Number(data.get(`x${index}`)),y:Number(data.get(`y${index}`))}));
      void execute("annotation.update",{annotation_id:annotation.id,annotation:{kind:annotation.kind,points,
        label:String(data.get("label")??""),visibility:annotation.visibility}});
    }}>
      <label>Текст выбранной метки<input name="label" defaultValue={annotation.label} maxLength={160}/></label>
      {annotation.points.map((point,index)=><div key={index}><label>X точки {index+1}<input name={`x${index}`} type="number" step="any" min={-1000000} max={1000000} defaultValue={point.x} required/></label>
        <label>Y точки {index+1}<input name={`y${index}`} type="number" step="any" min={-1000000} max={1000000} defaultValue={point.y} required/></label></div>)}
      <button disabled={disabled||!annotation.can_edit} type="submit">Сохранить метку</button>
      <button disabled={disabled||!annotation.can_edit} type="button" onClick={()=>void execute("annotation.delete",{annotation_id:annotation.id},()=>setSelected(""))}>Удалить метку в корзину</button>
    </form>:null}</details>
  </section>;
}
