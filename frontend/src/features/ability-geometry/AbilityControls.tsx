import type { AbilitySelection } from "./types";
import type { Point } from "../../renderer/viewport";
import type { SceneProjection } from "../scene/types";
import { directed } from "./geometry";
import "./ability-geometry.css";

export function AbilityControls({selection,origin,direction,projection,onConfirm,onCancel,onClear,onPoint,onToken,disabled}: {
  selection:AbilitySelection|null;origin:Point|null;direction:Point|null;projection:SceneProjection;
  onConfirm():void;onCancel():void;onClear(id:string):void;onPoint(point:Point):void;
  onToken(id:string):void;disabled:boolean;
}) {
  const geometry=selection?.ability.geometry;
  const requiredDirection=geometry?directed(geometry):false;
  return <section className="ability-controls" aria-label="Области способностей">
    {selection&&geometry?<>
      <p role="status">{selection.ability.name} · {!origin?geometry.origin==="token"?"Выберите токен карточки":"Выберите точку источника":requiredDirection&&!direction?"Укажите направление":"Область готова к показу"}</p>
      <p>Размеры из карточки · {geometry.units}{geometry.range!=null?` · дальность (справочно) ${geometry.range}`:""}. Ресурсы и урон меняются вручную.</p>
      {geometry.origin==="point"?<p>{requiredDirection?"Протяните от источника к направлению. Повторный жест перемещает и поворачивает черновик.":"Укажите точку на карте. Повторное указание перемещает черновик."} Затем подтвердите показ.</p>:null}
      {geometry.units!==projection.scene?.unit_label?<p role="alert">Единицы способности должны совпадать с калибровкой сцены.</p>:null}
      {geometry.origin==="token"&&!origin?<div>{projection.items.filter(item=>item.kind==="token"&&item.card_id===selection.cardId).map(item=>
        <button key={item.id} type="button" onClick={()=>onToken(item.id)}>Источник: {item.name}</button>)}</div>:null}
      {(geometry.origin==="point"&&!origin)||(requiredDirection&&origin)?<form className="ability-coordinates" onSubmit={event=>{event.preventDefault();const form=new FormData(event.currentTarget);
        onPoint({x:Number(form.get("x")),y:Number(form.get("y"))});}}>
        <label>Координата X<input name="x" type="number" min={-1000000} max={1000000} step="any" required defaultValue={128}/></label>
        <label>Координата Y<input name="y" type="number" min={-1000000} max={1000000} step="any" required defaultValue={128}/></label>
        <button type="submit">Задать точку</button>
      </form>:null}
      <button type="button" disabled={!origin||(requiredDirection&&!direction)||geometry.units!==projection.scene?.unit_label} onClick={onConfirm}>Показать способность</button>
      <button type="button" onClick={onCancel}>Отменить область</button>
    </>:null}
    {(projection.ability_presentations??[]).map(area=><div key={area.id}>
      <p>Область способности · затронутые видимые токены: {area.affected_item_ids.length}</p>
      <ul>{area.affected_item_ids.map(id=><li key={id}>{projection.items.find(item=>item.id===id)?.name??"Токен"}</li>)}</ul>
      {area.can_clear?<button type="button" disabled={disabled} onClick={()=>onClear(area.id)}>Убрать область</button>:null}
    </div>)}
  </section>;
}
