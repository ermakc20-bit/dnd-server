import type { Texture } from "pixi.js";

import type { SceneFrame } from "./viewport";
import { Viewport } from "./viewport";
import { visibleGrid } from "./grid";
import { outline } from "../features/ability-geometry/geometry";

export interface SceneRenderer {
  render(frame: SceneFrame, viewport: Viewport, assetUrls: ReadonlyMap<string, string>): void;
  destroy(): void;
}

export type RendererFactory = (host: HTMLElement, onAssetError: (message: string) => void)
  => Promise<SceneRenderer>;

interface SharedTexture {
  owners: Set<symbol>;
  loading: Promise<Texture>;
  cleanup?: Promise<void>;
}
// Assets is a Pixi singleton. Unload only after every renderer using that URL
// has released it; re-acquisition waits for a pending retirement to finish.
const textureOwners = new Map<string, SharedTexture>();

export const createPixiRenderer: RendererFactory = async (host, onAssetError) => {
  const { Application, Assets, Container, Graphics, Sprite } = await import("pixi.js");
  const app = new Application();
  await app.init({ resizeTo: host, background: "#12171f", antialias: true, preference: "webgl" });
  host.appendChild(app.canvas);
  const world = new Container();
  app.stage.addChild(world);
  const textures = new Map<string, Texture>();
  const owned = new Map<string, SharedTexture>();
  const owner = Symbol("scene-renderer");
  let current: { frame: SceneFrame; viewport: Viewport; urls: ReadonlyMap<string, string> } | null = null;
  let destroyed = false;

  function release(url: string, entry: SharedTexture) {
    entry.owners.delete(owner);
    if (entry.owners.size || entry.cleanup) return;
    entry.cleanup = entry.loading.then(() => Assets.unload(url)).catch(() => undefined).then(() => {
      if (textureOwners.get(url) === entry) textureOwners.delete(url);
    });
  }

  function acquire(url: string) {
    let entry = textureOwners.get(url);
    if (!entry || !entry.owners.size) {
      const previous = entry;
      entry = { owners: new Set(), loading: previous?.cleanup
        ? previous.cleanup.then(() => Assets.load<Texture>({ src: url, parser: "texture" }))
        : Assets.load<Texture>({ src: url, parser: "texture" }) };
      textureOwners.set(url, entry);
    }
    entry.owners.add(owner);
    owned.set(url, entry);
    const acquired = entry;
    void entry.loading.then((loaded) => {
      if (!destroyed && owned.get(url) === acquired) { textures.set(url, loaded); paint(); }
    }).catch(() => {
      if (!destroyed && owned.get(url) === acquired) onAssetError("Изображение временно недоступно. Метаданные сохранены.");
    });
  }

  function paint() {
    if (destroyed || !current) return;
    for (const child of world.removeChildren()) child.destroy();
    const { frame, viewport, urls } = current;
    const wanted = new Set(frame.items.flatMap(item => {
      const url = item.asset_id ? urls.get(item.asset_id) : undefined;
      return url ? [url] : [];
    }));
    for (const [url, entry] of owned) if (!wanted.has(url)) {
      owned.delete(url); textures.delete(url); release(url, entry);
    }
    for (const url of wanted) if (!owned.has(url)) acquire(url);
    world.position.set(viewport.x, viewport.y);
    world.scale.set(viewport.zoom);
    world.rotation=viewport.rotation;
    const scene = frame.projection.scene;
    const grid = new Graphics();
    if (scene) {
      const { left, top, right, bottom, step } = visibleGrid(
        viewport, app.screen.width, app.screen.height, scene.grid_size,
      );
      world.addChild(new Graphics().rect(left, top, right - left, bottom - top).fill("#1c232b"));
      if (scene.grid_enabled) {
        for (let x = left; x <= right; x += step) grid.moveTo(x, top).lineTo(x, bottom);
        for (let y = top; y <= bottom; y += step) grid.moveTo(left, y).lineTo(right, y);
        grid.stroke({ color: "#8995a6", alpha: 0.28, width: 1 / viewport.zoom });
      }
    }
    for (const item of frame.items) {
      const url = item.asset_id ? urls.get(item.asset_id) : undefined;
      const texture = url ? textures.get(url) : undefined;
      const graphic = texture ? new Sprite(texture) : new Graphics()
        .rect(-item.width / 2, -item.height / 2, item.width, item.height)
        .fill(item.kind === "map" ? "#343e4b" : item.can_transform ? "#9aaabd" : "#778493")
        .stroke({ color: item.is_locked ? "#bdc7d3" : "#1b2027", width: 2 });
      if (graphic instanceof Sprite) {
        graphic.anchor.set(0.5);
        graphic.width = item.width;
        graphic.height = item.height;
      }
      graphic.position.set(item.x + item.width / 2, item.y + item.height / 2);
      graphic.rotation = item.rotation * Math.PI / 180;
      graphic.alpha = item.visibility === "gm_only" ? 0.6 : 1;
      world.addChild(graphic);
    }
    // The calibration grid remains visible above opaque map textures.
    world.addChild(grid);
    const areas=frame.projection.ability_presentations??[];
    for(const geometry of [...areas.map(area=>area.geometry),...(frame.abilityPreview?[frame.abilityPreview]:[])]) {
      const points=outline(geometry),graphic=new Graphics();
      if(points.length){graphic.moveTo(points[0].x,points[0].y);for(const point of points.slice(1))graphic.lineTo(point.x,point.y);
        graphic.lineTo(points[0].x,points[0].y).fill({color:geometry.color,alpha:0.18}).stroke({color:geometry.color,width:2/viewport.zoom,alpha:0.9});}
      world.addChild(graphic);
    }
    for(const area of areas)for(const id of area.affected_item_ids) {
      const item=frame.items.find(item=>item.id===id&&item.kind==="token");if(!item)continue;
      const highlight=new Graphics().rect(-item.width/2,-item.height/2,item.width,item.height)
        .stroke({color:area.geometry.color,width:4/viewport.zoom});
      highlight.position.set(item.x+item.width/2,item.y+item.height/2);highlight.rotation=item.rotation*Math.PI/180;
      world.addChild(highlight);
    }
  }

  app.renderer.on("resize", paint);

  return {
    render(frame, viewport, urls) { current = { frame, viewport, urls }; paint(); },
    destroy() {
      destroyed = true;
      current = null;
      app.renderer.off("resize", paint);
      app.destroy(true, { children: true, texture: false, textureSource: false });
      for (const [url, entry] of owned) release(url, entry);
      owned.clear(); textures.clear();
    },
  };
};
