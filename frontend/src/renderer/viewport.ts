import type { SceneItem, SceneProjection } from "../features/scene/types";
import type { PresentedGeometry } from "../features/ability-geometry/types";

export interface Point { x: number; y: number }
export interface ItemPreview extends Point { id: string }
export interface SceneFrame { projection: SceneProjection; items: SceneItem[]; abilityPreview:PresentedGeometry|null }

export class Viewport {
  x = 0;
  y = 0;
  zoom = 1;
  rotation = 0;

  pan(dx: number, dy: number) { this.x += dx; this.y += dy; }
  screenToWorld(point: Point): Point {
    const dx = (point.x - this.x) / this.zoom;
    const dy = (point.y - this.y) / this.zoom;
    const c = Math.cos(this.rotation), s = Math.sin(this.rotation);
    return { x: dx * c + dy * s, y: -dx * s + dy * c };
  }
  worldToScreen(point: Point): Point {
    const c = Math.cos(this.rotation), s = Math.sin(this.rotation);
    return { x: (point.x * c - point.y * s) * this.zoom + this.x,
      y: (point.x * s + point.y * c) * this.zoom + this.y };
  }
  zoomAt(point: Point, factor: number) {
    const world = this.screenToWorld(point);
    this.zoom = Math.max(0.1, Math.min(4, this.zoom * factor));
    this.anchor(point, world);
  }
  rotateAt(point: Point, radians: number) {
    const world = this.screenToWorld(point);
    this.rotation += radians;
    this.anchor(point, world);
  }
  private anchor(point: Point, world: Point) {
    const screen = this.worldToScreen(world);
    this.x += point.x - screen.x;
    this.y += point.y - screen.y;
  }
}

export function buildFrame(projection: SceneProjection, preview?: ItemPreview | null, abilityPreview:PresentedGeometry|null=null): SceneFrame {
  return {
    projection,
    abilityPreview,
    items: projection.items.map((item) => preview?.id === item.id
      ? { ...item, x: preview.x, y: preview.y } : item)
      .sort((a, b) => a.z_index - b.z_index),
  };
}

export function hitTest(items: readonly SceneItem[], point: Point): SceneItem | null {
  for (let index = items.length - 1; index >= 0; index -= 1) {
    const item = items[index];
    const angle = -item.rotation * Math.PI / 180;
    const dx = point.x - item.x - item.width / 2;
    const dy = point.y - item.y - item.height / 2;
    const x = dx * Math.cos(angle) - dy * Math.sin(angle);
    const y = dx * Math.sin(angle) + dy * Math.cos(angle);
    if (Math.abs(x) <= item.width / 2 && Math.abs(y) <= item.height / 2) return item;
  }
  return null;
}
