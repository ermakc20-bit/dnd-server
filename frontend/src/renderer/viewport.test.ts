import { describe, expect, it } from "vitest";

describe("scene renderer public geometry", () => {
  it("preserves world point under cursor on zoom and reverses pan transforms", async () => {
    const module = await import("./viewport");
    expect(module.Viewport).toBeTypeOf("function");
    const viewport = new module.Viewport();
    viewport.pan(40, -20);
    expect(viewport.screenToWorld({ x: 100, y: 80 })).toEqual({ x: 60, y: 100 });
    viewport.zoomAt({ x: 100, y: 80 }, 2);
    expect(viewport.screenToWorld({ x: 100, y: 80 })).toEqual({ x: 60, y: 100 });
    expect(viewport.worldToScreen({ x: 60, y: 100 })).toEqual({ x: 100, y: 80 });
    viewport.zoomAt({ x: 0, y: 0 }, 100);
    expect(viewport.zoom).toBe(4);
  });

  it("hits rotated top-layer objects and builds a frame of 500 visible objects", async () => {
    const { hitTest, buildFrame } = await import("./viewport");
    const items = Array.from({ length: 500 }, (_, index) => ({
      id: `item-${index}`, kind: "token" as const, name: `Token ${index}`, asset_id: null,
      x: index * 80, y: 0, width: 64, height: 64, rotation: 0, z_index: index,
      visibility: "everyone" as const, is_locked: false, owner_participant_id: null,
      can_transform: true,
    }));
    const projection = {
      room_id: "r", actor_session_id: "p", aggregate_version: 1, event_cursor: 1,
      can_manage: true, scenes: [], scene: null, items,
    };
    const frame = buildFrame(projection);
    expect(frame.items).toHaveLength(500);
    expect(hitTest(frame.items, { x: 499 * 80 + 32, y: 32 })?.id).toBe("item-499");
    expect(hitTest(frame.items, { x: -1, y: -1 })).toBeNull();
    const rotated = { ...items[0], id: "rotated", width: 128, rotation: 90, z_index: 501 };
    expect(hitTest([...frame.items, rotated], { x: 64, y: -15 })?.id).toBe("rotated");
    const preview = buildFrame(projection, { id: "item-499", x: 100, y: 100 });
    expect(preview.items[499].x).toBe(100);
    expect(projection.items[499].x).toBe(39920);
  });
});

it("viewport rotation keeps anchor fixed and distance in world units", async () => {
  const { Viewport } = await import("./viewport");
  const viewport = new Viewport();
  viewport.pan(10, 20);
  viewport.zoomAt({ x: 10, y: 20 }, 2);
  viewport.rotateAt({ x: 10, y: 20 }, Math.PI / 2);
  expect(viewport.worldToScreen({ x: 64, y: 0 }).x).toBeCloseTo(10);
  expect(viewport.worldToScreen({ x: 64, y: 0 }).y).toBeCloseTo(148);
  expect(viewport.screenToWorld({ x: 10, y: 148 }).x).toBeCloseTo(64);
  expect(viewport.screenToWorld({ x: 10, y: 148 }).y).toBeCloseTo(0);
});
