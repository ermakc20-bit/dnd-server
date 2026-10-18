import type { Viewport } from "./viewport";

export function visibleGrid(viewport: Viewport, width: number, height: number, cellSize: number) {
  const corners = [
    { x: 0, y: 0 }, { x: width, y: 0 },
    { x: width, y: height }, { x: 0, y: height },
  ].map(point => viewport.screenToWorld(point));
  // At distant zoom levels show a subset of the same world-aligned lines.
  // This bounds drawing work and avoids subpixel moiré; snapping keeps its real cell size.
  const stride = 2 ** Math.max(0, Math.ceil(Math.log2(12 / (cellSize * viewport.zoom))));
  const step = cellSize * stride;
  return {
    left: Math.floor(Math.min(...corners.map(point => point.x)) / step) * step - step,
    top: Math.floor(Math.min(...corners.map(point => point.y)) / step) * step - step,
    right: Math.ceil(Math.max(...corners.map(point => point.x)) / step) * step + step,
    bottom: Math.ceil(Math.max(...corners.map(point => point.y)) / step) * step + step,
    step,
  };
}
