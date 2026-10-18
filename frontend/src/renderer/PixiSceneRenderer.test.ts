import { beforeEach, describe, expect, it, vi } from "vitest";

import type { SceneProjection } from "../features/scene/types";
import { createPixiRenderer } from "./PixiSceneRenderer";
import { buildFrame, Viewport } from "./viewport";

const assets = vi.hoisted(() => ({ load: vi.fn().mockResolvedValue({}), unload: vi.fn().mockResolvedValue(undefined) }));
const drawing = vi.hoisted(() => ({
  segments: [] as { from: { x: number; y: number }; to: { x: number; y: number } }[],
  screen: { width: 800, height: 600 },
  resize: new Set<() => void>(),
}));
vi.mock("pixi.js", () => {
  class Container {
    children: Container[] = [];
    position = { set: vi.fn() };
    scale = { set: vi.fn() };
    addChild(child: Container) { this.children.push(child); }
    removeChildren() { const children = this.children; this.children = []; return children; }
    destroy() {}
  }
  class Graphics extends Container {
    private pen = { x: 0, y: 0 };
    rect() { return this; }
    fill() { return this; }
    stroke() { return this; }
    moveTo(x: number, y: number) { this.pen = { x, y }; return this; }
    lineTo(x: number, y: number) {
      drawing.segments.push({ from: this.pen, to: { x, y } });
      this.pen = { x, y }; return this;
    }
  }
  class Sprite extends Container {
    anchor = { set: vi.fn() };
  }
  class Application {
    canvas = document.createElement("canvas");
    stage = new Container();
    screen = drawing.screen;
    renderer = {
      on: (_event: string, callback: () => void) => drawing.resize.add(callback),
      off: (_event: string, callback: () => void) => drawing.resize.delete(callback),
    };
    async init() {}
    destroy() {}
  }
  return { Application, Assets: assets, Container, Graphics, Sprite };
});

describe("infinite scene grid", () => {
  const scene: SceneProjection = {
    room_id: "r", actor_session_id: "p", aggregate_version: 1, event_cursor: 1,
    can_manage: true, scenes: [], items: [],
    scene: { id: "s", name: "Small scene", width: 128, height: 128, grid_size: 64,
      grid_enabled: true, snap_enabled: true, unit_size: 5, unit_label: "фут" },
  };

  beforeEach(() => {
    drawing.segments = [];
    drawing.screen.width = 800; drawing.screen.height = 600;
    drawing.resize.clear();
  });

  function expectCovered(viewport: Viewport, width: number, height: number, cellSize: number) {
    const vertical = drawing.segments.filter(line => line.from.x === line.to.x);
    const horizontal = drawing.segments.filter(line => line.from.y === line.to.y);
    const xs = vertical.map(line => line.from.x), ys = horizontal.map(line => line.from.y);
    for (const corner of [{ x: 0, y: 0 }, { x: width, y: 0 }, { x: width, y: height }, { x: 0, y: height }]) {
      const point = viewport.screenToWorld(corner);
      expect(Math.min(...xs)).toBeLessThanOrEqual(point.x);
      expect(Math.max(...xs)).toBeGreaterThanOrEqual(point.x);
      expect(Math.min(...ys)).toBeLessThanOrEqual(point.y);
      expect(Math.max(...ys)).toBeGreaterThanOrEqual(point.y);
      expect(vertical.every(line => line.from.y <= point.y && line.to.y >= point.y)).toBe(true);
      expect(horizontal.every(line => line.from.x <= point.x && line.to.x >= point.x)).toBe(true);
    }
    // Line thinning may hide cells at distant zoom, but may never move their origin.
    expect([...xs, ...ys].every(value => Number.isInteger(value / cellSize))).toBe(true);
    expect(drawing.segments.length).toBeLessThan(300);
  }

  it.each([
    { x: 0, y: 0, zoom: 1, rotation: 0, cellSize: 64 },
    { x: 2200, y: -1700, zoom: 0.1, rotation: 0, cellSize: 64 },
    { x: -830, y: 1200, zoom: 0.5, rotation: Math.PI / 4, cellSize: 64 },
    { x: 410, y: -520, zoom: 0.1, rotation: Math.PI / 3, cellSize: 8 },
    { x: -1200, y: -360, zoom: 4, rotation: Math.PI / 2, cellSize: 512 },
  ])("covers the viewport outside scene bounds at $zoom zoom and $rotation rotation", async (view) => {
    const viewport = Object.assign(new Viewport(), view);
    const renderer = await createPixiRenderer(document.createElement("div"), vi.fn());
    renderer.render(buildFrame({ ...scene, scene: { ...scene.scene!, grid_size: view.cellSize } }), viewport, new Map());
    expectCovered(viewport, 800, 600, view.cellSize);
    renderer.destroy();
  });

  it("extends to a resized canvas without waiting for a scene command or camera gesture", async () => {
    const renderer = await createPixiRenderer(document.createElement("div"), vi.fn());
    const viewport = new Viewport();
    renderer.render(buildFrame(scene), viewport, new Map());
    drawing.segments = [];
    drawing.screen.width = 1600; drawing.screen.height = 900;
    for (const repaint of drawing.resize) repaint();
    expectCovered(viewport, 1600, 900, 64);
    renderer.destroy();
    expect(drawing.resize.size).toBe(0);
  });

  it("preserves the scene grid switch", async () => {
    const renderer = await createPixiRenderer(document.createElement("div"), vi.fn());
    renderer.render(buildFrame({ ...scene, scene: { ...scene.scene!, grid_enabled: false } }), new Viewport(), new Map());
    expect(drawing.segments).toHaveLength(0);
    renderer.destroy();
  });
});

describe("private asset renderer boundary", () => {
  beforeEach(() => { assets.load.mockReset().mockResolvedValue({}); assets.unload.mockReset().mockResolvedValue(undefined); });
  it("loads an opaque private grant as a texture without relying on a filename extension", async () => {
    assets.load.mockResolvedValue({});
    const projection: SceneProjection = {
      room_id: "r", actor_session_id: "p", aggregate_version: 1, event_cursor: 1,
      can_manage: false, scenes: [], scene: null,
      items: [{ id: "map", kind: "map", name: "Private map", asset_id: "asset",
        x: 0, y: 0, width: 800, height: 600, rotation: 0, z_index: -1000,
        visibility: "everyone", is_locked: true, owner_participant_id: null, can_transform: false }],
    };
    const renderer = await createPixiRenderer(document.createElement("div"), vi.fn());
    const grant = "/api/__test_storage/opaque-grant";
    renderer.render(buildFrame(projection), new Viewport(), new Map([["asset", grant]]));
    expect(assets.load).toHaveBeenCalledWith({ src: grant, parser: "texture" });
    await Promise.resolve();
    renderer.destroy();
  });

  const projection: SceneProjection = {
    room_id: "r", actor_session_id: "p", aggregate_version: 1, event_cursor: 1,
    can_manage: false, scenes: [], scene: null,
    items: [{ id: "map", kind: "map", name: "Private map", asset_id: "asset", x: 0, y: 0,
      width: 800, height: 600, rotation: 0, z_index: -1000, visibility: "everyone",
      is_locked: true, owner_participant_id: null, can_transform: false }],
  };
  const settled = async () => { for (let i = 0; i < 10; i++) await Promise.resolve(); };

  it("releases obsolete grants across 100 refreshes and frees the last texture on destroy", async () => {
    const live = new Set<string>(); let peak = 0;
    assets.load.mockImplementation(async ({ src }: { src: string }) => { live.add(src); peak = Math.max(peak, live.size); return {}; });
    assets.unload.mockImplementation(async (url: string) => { live.delete(url); });
    const renderer = await createPixiRenderer(document.createElement("div"), vi.fn());
    for (let i = 0; i < 100; i++) {
      renderer.render(buildFrame(projection), new Viewport(), new Map([["asset", `/private/grant-${i}`]]));
      await settled();
      expect(live.size).toBe(1);
    }
    expect(assets.unload).toHaveBeenCalledTimes(99);
    expect(peak).toBeLessThanOrEqual(2);
    renderer.destroy(); await settled();
    expect(assets.unload).toHaveBeenCalledTimes(100);
    expect(live.size).toBe(0);
  });

  it("releases an image removed from the frame even if its grant remains in the supplied map", async () => {
    const renderer = await createPixiRenderer(document.createElement("div"), vi.fn());
    const urls = new Map([["asset", "/private/removed"]]);
    renderer.render(buildFrame(projection), new Viewport(), urls); await settled();
    renderer.render(buildFrame({ ...projection, items: [] }), new Viewport(), urls); await settled();
    expect(assets.unload).toHaveBeenCalledWith("/private/removed");
    renderer.destroy(); await settled();
  });

  it("releases late loads after replacement or destroy without painting or showing a stale error", async () => {
    const completions = new Map<string, (texture: object) => void>();
    assets.load.mockImplementation(({ src }: { src: string }) => new Promise(resolve => completions.set(src, resolve)));
    const error = vi.fn();
    const renderer = await createPixiRenderer(document.createElement("div"), error);
    renderer.render(buildFrame(projection), new Viewport(), new Map([["asset", "/private/late-old"]]));
    renderer.render(buildFrame(projection), new Viewport(), new Map([["asset", "/private/late-new"]]));
    completions.get("/private/late-old")!({}); await settled();
    expect(assets.unload).toHaveBeenCalledWith("/private/late-old");
    renderer.destroy(); completions.get("/private/late-new")!({}); await settled();
    expect(assets.unload).toHaveBeenCalledWith("/private/late-new");
    expect(error).not.toHaveBeenCalled();
  });

  it("keeps a shared URL alive until both renderer owners release it", async () => {
    const first = await createPixiRenderer(document.createElement("div"), vi.fn());
    const second = await createPixiRenderer(document.createElement("div"), vi.fn());
    const urls = new Map([["asset", "/private/shared"]]);
    first.render(buildFrame(projection), new Viewport(), urls);
    second.render(buildFrame(projection), new Viewport(), urls); await settled();
    first.destroy(); await settled();
    expect(assets.unload).not.toHaveBeenCalled();
    second.destroy(); await settled();
    expect(assets.unload).toHaveBeenCalledTimes(1);
    expect(assets.unload).toHaveBeenCalledWith("/private/shared");
  });
});
