import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { RendererFactory } from "../../renderer/PixiSceneRenderer";
import type { SceneProjection } from "./types";
import { SceneCanvas } from "./SceneCanvas";

const projection: SceneProjection = {
  room_id: "r", actor_session_id: "p", aggregate_version: 1, event_cursor: 1,
  can_manage: true, scenes: [],
  scene: { id: "s", name: "Test", width: 4096, height: 4096, grid_size: 64,
    grid_enabled: true, snap_enabled: true, unit_size: 5, unit_label: "фут" },
  items: [{ id: "token", kind: "token", name: "Токен", x: 0, y: 0, width: 64, height: 64,
    rotation: 0, z_index: 0, visibility: "everyone", is_locked: false, owner_participant_id: null,
    asset_id: null, can_transform: true }],
};

describe("SceneCanvas", () => {
  it("restores the confirmed frame when a drag becomes read-only after a transport failure", async () => {
    const draw = vi.fn();
    const onMove = vi.fn();
    const factory: RendererFactory = async () => ({ render: draw, destroy: vi.fn() });
    const props = { projection, assetUrls: new Map<string, string>(), onMove,
      onSelect: vi.fn(), factory };
    const view = render(<SceneCanvas {...props} disabled={false} />);
    await waitFor(() => expect(draw).toHaveBeenCalled());
    const surface = screen.getByRole("region", { name: "Карта и токены" });
    fireEvent(surface, new MouseEvent("pointerdown", { clientX: 20, clientY: 20, bubbles: true }));
    fireEvent(surface, new MouseEvent("pointermove", { clientX: 100, clientY: 148, bubbles: true }));
    fireEvent(surface, new MouseEvent("pointerup", { clientX: 100, clientY: 148, bubbles: true }));
    expect(onMove).toHaveBeenCalledTimes(1);
    expect(draw.mock.calls.at(-1)?.[0].items[0]).toMatchObject({ x: 80, y: 128 });
    view.rerender(<SceneCanvas {...props} disabled />);
    await waitFor(() => expect(draw.mock.calls.at(-1)?.[0].items[0]).toMatchObject({ x: 0, y: 0 }));
    expect(projection.items[0]).toMatchObject({ x: 0, y: 0 });
  });
  it("does not accidentally drag a locked token even for the GM", async () => {
    const draw = vi.fn();
    const onMove = vi.fn();
    render(<SceneCanvas projection={{ ...projection, items: [{ ...projection.items[0], is_locked: true }] }}
      assetUrls={new Map()} onMove={onMove} onSelect={vi.fn()} disabled={false}
      factory={async () => ({ render: draw, destroy: vi.fn() })} />);
    await waitFor(() => expect(draw).toHaveBeenCalled());
    const surface = screen.getByRole("region", { name: "Карта и токены" });
    fireEvent(surface, new MouseEvent("pointerdown", { clientX: 20, clientY: 20, bubbles: true }));
    fireEvent(surface, new MouseEvent("pointermove", { clientX: 100, clientY: 148, bubbles: true }));
    fireEvent(surface, new MouseEvent("pointerup", { clientX: 100, clientY: 148, bubbles: true }));
    expect(onMove).not.toHaveBeenCalled();
  });
  it("consumes wheel input without scrolling the surrounding document", async () => {
    const draw = vi.fn();
    render(<SceneCanvas projection={projection} assetUrls={new Map()} onMove={vi.fn()}
      onSelect={vi.fn()} disabled={false}
      factory={async () => ({ render: draw, destroy: vi.fn() })} />);
    await waitFor(() => expect(draw).toHaveBeenCalled());
    const surface = screen.getByRole("region", { name: "Карта и токены" });
    const wheel = new WheelEvent("wheel", { deltaY: 500, clientX: 100, clientY: 100,
      bubbles: true, cancelable: true });
    fireEvent(surface, wheel);
    expect(wheel.defaultPrevented).toBe(true);
    expect(draw.mock.calls.at(-1)?.[1].zoom).toBeLessThan(1);
  });
  it("previews a drag locally and submits exactly one durable transform on release", async () => {
    const draw = vi.fn();
    const onMove = vi.fn();
    const factory: RendererFactory = async () => ({ render: draw, destroy: vi.fn() });
    render(<SceneCanvas projection={projection} assetUrls={new Map()} onMove={onMove}
      onSelect={vi.fn()} disabled={false} factory={factory} />);
    const surface = screen.getByRole("region", { name: "Карта и токены" });
    await waitFor(() => expect(draw).toHaveBeenCalled());
    fireEvent(surface, new MouseEvent("pointerdown", { clientX: 20, clientY: 20, bubbles: true }));
    fireEvent(surface, new MouseEvent("pointermove", { clientX: 100, clientY: 148, bubbles: true }));
    expect(onMove).not.toHaveBeenCalled();
    expect(draw.mock.calls.at(-1)?.[0].items[0]).toMatchObject({ x: 80, y: 128 });
    fireEvent(surface, new MouseEvent("pointerup", { clientX: 100, clientY: 148, bubbles: true }));
    expect(onMove).toHaveBeenCalledTimes(1);
    expect(onMove).toHaveBeenCalledWith("token", { x: 80, y: 128 });
  });

  it("keeps 500 objects in the renderer frame and denies local drag of an uncontrolled token", async () => {
    const draw = vi.fn();
    const onMove = vi.fn();
    const items = Array.from({ length: 500 }, (_, index) => ({
      ...projection.items[0], id: `t${index}`, x: index * 80, can_transform: false,
    }));
    render(<SceneCanvas projection={{ ...projection, items }} assetUrls={new Map()}
      onMove={onMove} onSelect={vi.fn()} disabled={false}
      factory={async () => ({ render: draw, destroy: vi.fn() })} />);
    await waitFor(() => expect(draw).toHaveBeenCalled());
    expect(draw.mock.calls.at(-1)?.[0].items).toHaveLength(500);
    const surface = screen.getByRole("region", { name: "Карта и токены" });
    fireEvent(surface, new MouseEvent("pointerdown", { clientX: 20, clientY: 20, bubbles: true }));
    fireEvent(surface, new MouseEvent("pointermove", { clientX: 100, clientY: 148, bubbles: true }));
    fireEvent(surface, new MouseEvent("pointerup", { clientX: 100, clientY: 148, bubbles: true }));
    expect(onMove).not.toHaveBeenCalled();
  });
});
