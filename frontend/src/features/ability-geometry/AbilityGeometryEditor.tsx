import type { Geometry } from "./types";
import "./ability-geometry.css";

const shapes = { circle: "Круг", cone: "Конус", line: "Линия", cube: "Куб", radius: "Радиус" };
const defaults: Geometry = { shape: "circle", origin: "token", radius: 5, length: 5,
  width: 5, angle: 90, range: null, units: "фут", color: "#c5a65c" };

export function AbilityGeometryEditor({ value, index, onChange }: {
  value: Geometry | null; index: number; onChange(value: Geometry | null): void;
}) {
  function patch(change: Partial<Geometry>) { if (value) onChange({ ...value, ...change }); }
  function dimension(key: "radius" | "length" | "width" | "angle" | "range", label: string,
    required = true) {
    return <label>{label} {index}<input type="number" step="any" min={key === "range" ? 0 : 0.000001}
      max={key === "angle" ? 360 : 1000000} required={required} value={value?.[key] ?? ""}
      onChange={event => patch({ [key]: event.target.value === "" ? null : Number(event.target.value) })} /></label>;
  }
  return <fieldset className="ability-geometry-editor">
    <legend>Область способности {index}</legend>
    <label><input type="checkbox" checked={value !== null}
      onChange={event => onChange(event.target.checked ? { ...defaults } : null)} />Геометрия способности {index}</label>
    {value ? <>
      <label>Форма области {index}<select value={value.shape}
        onChange={event => patch({ shape: event.target.value as Geometry["shape"] })}>
        {Object.entries(shapes).map(([shape, label]) => <option key={shape} value={shape}>{label}</option>)}
      </select></label>
      <label>Источник области {index}<select value={value.origin}
        onChange={event => patch({ origin: event.target.value as Geometry["origin"] })}>
        <option value="token">Токен этой карточки</option><option value="point">Точка на карте</option>
      </select></label>
      {["circle", "radius"].includes(value.shape) ? dimension("radius", "Радиус области")
        : dimension("length", "Длина области")}
      {value.shape === "line" ? dimension("width", "Ширина области") : null}
      {value.shape === "cone" ? dimension("angle", "Угол области") : null}
      {dimension("range", "Дальность (справочно)", false)}
      <label>Единицы области {index}<input required minLength={1} maxLength={24} value={value.units}
        onChange={event => patch({ units: event.target.value })} /></label>
      <label>Цвет области {index}<input type="color" value={value.color ?? "#c5a65c"}
        onChange={event => patch({ color: event.target.value })} /></label>
      <p>Круг и радиус — диск; куб — квадрат с источником в центре. Размеры заданы в единицах сцены,
        угол — в градусах. Дальность — подсказка; применение и расход ресурсов решаются вручную.</p>
    </> : null}
  </fieldset>;
}
