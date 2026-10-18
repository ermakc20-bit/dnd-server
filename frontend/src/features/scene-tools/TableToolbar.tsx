import type { Ref } from "react";
import { Icon, type IconName } from "../../components/Icon";
import type { TableTool } from "./types";

export const tableTools: readonly { id: TableTool; label: string; icon: IconName; key: string; gm?: boolean }[] = [
  { id: "select", label: "Выбор и перемещение", icon: "pointer", key: "V" },
  { id: "ruler", label: "Линейка", icon: "ruler", key: "R" },
  { id: "line", label: "Линия", icon: "line", key: "L" },
  { id: "arrow", label: "Стрелка", icon: "direction", key: "A" },
  { id: "label", label: "Метка", icon: "label", key: "T" },
  { id: "fog.rectangle", label: "Открыть прямоугольник", icon: "fog", key: "F", gm: true },
  { id: "fog.polygon", label: "Открыть многоугольник", icon: "polygon", key: "P", gm: true },
];
export function toolAvailable(id: TableTool, hasScene: boolean, disabled: boolean, canManage: boolean) {
  return id === "select" || hasScene && (id === "ruler" || !disabled && (!id.startsWith("fog.") || canManage));
}

export function TableToolbar({ tool, onTool, hasScene, disabled, canManage, onSettings, settingsOpen, settingsRef }: {
  tool: TableTool; onTool(tool: TableTool): void; hasScene: boolean; disabled: boolean; canManage: boolean;
  onSettings(): void; settingsOpen: boolean; settingsRef?: Ref<HTMLButtonElement>;
}) {
  const keyboardTool = toolAvailable(tool, hasScene, disabled, canManage) ? tool : "select";
  return <div className="table-toolbox">
    <div className="map-tool-rail" role="toolbar" aria-label="Работа на карте" aria-orientation="vertical"
      onKeyDown={event => {
        if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
        const buttons = [...event.currentTarget.querySelectorAll<HTMLButtonElement>("button:not(:disabled)")];
        const index = buttons.indexOf(event.target as HTMLButtonElement);
        const next = event.key === "Home" ? 0 : event.key === "End" ? buttons.length - 1
          : (index + (event.key === "ArrowDown" ? 1 : -1) + buttons.length) % buttons.length;
        event.preventDefault(); buttons[next]?.focus();
      }}>
      {tableTools.filter(entry => !entry.gm || canManage).map(entry => <button key={entry.id} type="button"
        aria-label={entry.label} tabIndex={entry.id === keyboardTool ? 0 : -1} aria-keyshortcuts={entry.key} aria-pressed={tool === entry.id}
        disabled={!toolAvailable(entry.id, hasScene, disabled, canManage)}
        onClick={() => onTool(entry.id)}>
        <Icon name={entry.icon} size={19} /><span className="tool-tip" aria-hidden="true">{entry.label}<kbd>{entry.key}</kbd></span>
      </button>)}
      <span className="tool-divider" />
      <button ref={settingsRef} type="button" aria-label="Инструменты" aria-expanded={settingsOpen}
        onClick={onSettings}><Icon name="settings" size={19} /><span className="tool-tip" aria-hidden="true">Параметры инструмента</span></button>
    </div>
  </div>;
}
