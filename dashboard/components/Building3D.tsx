"use client";
// The building as an exploded axonometric, in the reference's look: every level is an open floor plate, well
// apart from the next; black shapes, thick white outlines, SITAC colours as flat fills. No dot fills, no dotted
// lines, no gradients. Built from the state (levels, room zones, plan points, hazards, people, teams, routes) until
// the IFC's building.glb exists. Still until someone drags it: rotate with the mouse, zoom with the wheel.
import { useEffect, useRef } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { LineSegments2 } from "three/examples/jsm/lines/LineSegments2.js";
import { LineSegmentsGeometry } from "three/examples/jsm/lines/LineSegmentsGeometry.js";
import { LineMaterial } from "three/examples/jsm/lines/LineMaterial.js";
import { Line2 } from "three/examples/jsm/lines/Line2.js";
import { LineGeometry } from "three/examples/jsm/lines/LineGeometry.js";
import { CSS2DObject, CSS2DRenderer } from "three/examples/jsm/renderers/CSS2DRenderer.js";
import type { Building, IncidentState, Occupant, Route } from "@/lib/types";
import { OCC_STATUS, hm, levelLabel } from "@/lib/fr";

// Colours from brand/tokens.css, by meaning: fire and danger = Seraph (blackbody), smoke = Seraph 300, people = Silex,
// structure and our crews = Halo white.
const C = { ink: "#ffffff", line: "#d0cecb", dim: "#54524f", mute: "#3a3937", fire: "#f2560f", warn: "#ff9c5a", life: "#3fd68a", lit: "#e7e6e4" };
const PX_PER_M = 50; // plan units (0–1000) per metre, when the model does not give its plan_frame
const STEP = 9; // vertical distance between two floor plates when levels have no elevation
const EXPLODE = 4; // added between levels on top of their real height (elevation_m, 1 world unit = 1 m)
const SLAB = 0.4;
const FLAT = 0.03; // the plan is drawn flat on the plate, just above its top face
const CORE = 1.6; // stair core, a small square on every plate
const ELEV = (32 * Math.PI) / 180; // starting view
const AZ = 0.62;
const FADE = 600; // ms: a level that becomes active comes up from grey

type Box = { x: number; y: number; w: number; h: number };
// Seraph serves these on routes (status/seraph.md); not in contracts/types.ts yet — requested from Amil
type PathRoute = Route & { path?: [number, number][]; path_level?: number; path_image_id?: string };
// …and these from the IFC extract (rooms[].kind, stairs[].zones); also requested in contracts/types.ts
type KindRoom = Building["rooms"][number] & { kind?: "room" | "corridor" | "elevator" | "exterior" };
type ZonedStair = Building["stairs"][number] & { zones?: { level: number; zone: number[][] }[] };
// …and Seraph computes which levels matter (levels[].focus), so the dashboard and Halo grey out the same ones
type FocusLevel = Building["levels"][number] & { outline?: unknown; focus?: boolean; focus_reasons?: string[] };
type V3 = [number, number, number];
type Note = { pos: THREE.Vector3; level: number; tone: string; title: string; index: string; lines: string[]; rank: number };
type NoteEl = Note & { box: HTMLDivElement; frame: SVGPathElement; leader: SVGPathElement; leaderDark: SVGPathElement; mark: SVGGElement; h: number };
type Fade = { t0: number; lines: [LineMaterial, THREE.Color][]; fills: [THREE.MeshBasicMaterial, number, boolean][]; els: (HTMLElement | SVGElement)[] };

// callouts, in the container's px: a column right of the building, above the radio
const FIT = { left: 80, gap: 28, top: 36 }; // px kept free around the model: level labels, callout column, edges
const NOTE = { x: 740, w: 268, top: 64, bottom: 600, gap: 12, cut: 12 };
const SVG_NS = "http://www.w3.org/2000/svg";

/** `zoom`: "all" fits the whole building; "focus" frames the level that matters (split view, Rosetta below). */
export function Building3D({ state, box, scale, zoom = "all" }: { state: IncidentState | null; box: Box; scale: number; zoom?: "all" | "focus" }) {
  const host = useRef<HTMLDivElement>(null);
  const api = useRef<{ build: (s: IncidentState) => void; ratio: (r: number) => void } | null>(null);
  const key = useRef("");

  useEffect(() => {
    const el = host.current!;
    key.current = ""; // a fresh scene must be rebuilt (dev strict mode mounts twice)
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setClearColor(0x000000, 0);
    renderer.setSize(box.w, box.h);
    renderer.domElement.style.cursor = "grab";
    el.appendChild(renderer.domElement);
    const labels = new CSS2DRenderer();
    labels.setSize(box.w, box.h);
    Object.assign(labels.domElement.style, { position: "absolute", left: "0", top: "0", pointerEvents: "none" });
    el.appendChild(labels.domElement);

    // the reference's annotations: square marker on the spot, elbow leader, framed label
    const notesSvg = document.createElementNS(SVG_NS, "svg");
    notesSvg.setAttribute("width", String(box.w + NOTE.w + 200));
    notesSvg.setAttribute("height", String(box.h));
    Object.assign(notesSvg.style, { position: "absolute", left: "0", top: "0", overflow: "visible", pointerEvents: "none" });
    el.appendChild(notesSvg);
    // Leaders are light on the dark plates; where they cross the lit room they turn dark: a dark copy of every leader,
    // clipped to that room's outline as projected on screen (updated every frame).
    const clipId = `b3-lit-${Math.random().toString(36).slice(2, 8)}`;
    let litPoly: THREE.Vector3[] = [];
    let litClip: SVGPolygonElement;
    let gLight: SVGGElement;
    let gDark: SVGGElement;
    function resetNotesSvg() {
      notesSvg.innerHTML = `<defs><clipPath id="${clipId}"><polygon points=""/></clipPath></defs><g></g><g clip-path="url(#${clipId})"></g>`;
      litClip = notesSvg.querySelector("polygon")!;
      [gLight, gDark] = Array.from(notesSvg.querySelectorAll(":scope > g")) as SVGGElement[];
    }
    resetNotesSvg();
    const notesBox = document.createElement("div");
    Object.assign(notesBox.style, { position: "absolute", left: "0", top: "0", pointerEvents: "none" });
    el.appendChild(notesBox);
    let notes: NoteEl[] = [];
    const wide = box.w > 1200;
    const col = { x: wide ? box.w - NOTE.w - 120 : NOTE.x, top: wide ? 36 : NOTE.top, bottom: wide ? box.h - 20 : NOTE.bottom, max: wide ? 4 : 5 };

    const scene = new THREE.Scene();
    const camera = new THREE.OrthographicCamera(-1, 1, 1, -1, -1000, 1000);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enablePan = false;
    controls.enableDamping = true;
    controls.dampingFactor = 0.12;
    controls.minPolarAngle = 0.15;
    controls.maxPolarAngle = Math.PI / 2 - 0.05; // never under the ground
    controls.minZoom = 0.6;
    controls.maxZoom = 3;
    let model: THREE.Group | null = null;
    let fitted = false;
    // levels shown active at the last build, when each one became active, and the fades running
    let shown: Set<number> | null = null;
    const since = new Map<number, number>();
    let fades: Fade[] = [];

    const line = (color: string, width: number) => {
      const m = new LineMaterial({ color, linewidth: width });
      m.resolution.set(box.w, box.h);
      return m;
    };
    const solid = (color: string, opacity = 1) =>
      new THREE.MeshBasicMaterial({ color, transparent: opacity < 1, opacity, polygonOffset: true, polygonOffsetFactor: 1, polygonOffsetUnits: 1 });
    const outlined = (geo: THREE.BufferGeometry, fill: THREE.Material, edge: LineMaterial) => {
      const g = new THREE.Group();
      g.add(new THREE.Mesh(geo, fill));
      const e = new LineSegmentsGeometry().setPositions(new THREE.EdgesGeometry(geo, 30).attributes.position.array as Float32Array);
      g.add(new LineSegments2(e, edge));
      return g;
    };
    const tag = (text: string, cls = "") => {
      const d = document.createElement("div");
      d.className = `b3-tag ${cls}`;
      d.textContent = text;
      return d;
    };
    // CSS2DRenderer centres its element on the point; a zero-size anchor lets each overlay place itself
    const at = (node: HTMLElement, p: V3, parent: THREE.Object3D) => {
      const anchor = document.createElement("div");
      anchor.className = "b3-anchor";
      anchor.appendChild(node);
      const o = new CSS2DObject(anchor);
      o.position.set(...p);
      parent.add(o);
      return o;
    };

    function build(s: IncidentState) {
      if (model) {
        model.traverse((o) => {
          if (o instanceof CSS2DObject) o.element.remove();
          if (o instanceof THREE.Mesh || o instanceof LineSegments2 || o instanceof Line2) o.geometry.dispose();
        });
        scene.remove(model);
      }
      const g = new THREE.Group();
      model = g;
      scene.add(g);
      resetNotesSvg();
      litPoly = [];
      notesBox.replaceChildren();

      const b = s.building;
      const levels = [...b.levels].sort((a, c) => a.level - c.level);
      const pts = new Map((b.plan?.points ?? []).map((p) => [p.name, [p.point.x, p.point.y] as [number, number]]));
      const rooms = (b.rooms as KindRoom[]).filter((r) => r.zone && r.zone.length >= 3);
      const stairs = b.stairs as ZonedStair[];
      const outlines = new Map(levels.map((l) => [l.level, readOutline((l as FocusLevel).outline)]));
      const all = [
        ...rooms.flatMap((r) => r.zone as number[][]),
        ...stairs.flatMap((st) => (st.zones ?? []).flatMap((z) => z.zone)),
        ...[...outlines.values()].flatMap((ps) => ps?.flatMap((p) => p.outer) ?? []),
        ...pts.values(),
      ];
      const M = (b as Building & { model?: { plan_frame?: { px_per_m?: number } } }).model?.plan_frame?.px_per_m ?? PX_PER_M;
      // the corridor of a level: a room « corridor:<n> » (IFC) or the « corridor » plan point (fixture)
      const sameRoom = (id: string | undefined, r: KindRoom) => id === r.id || (id === "corridor" && r.kind === "corridor");
      const x0 = (all.length ? Math.min(...all.map((p) => p[0])) : 100) - 40;
      const x1 = (all.length ? Math.max(...all.map((p) => p[0])) : 900) + 40;
      const z0 = (all.length ? Math.min(...all.map((p) => p[1])) : 100) - 40;
      const z1 = (all.length ? Math.max(...all.map((p) => p[1])) : 900) + 40;
      const W = (px: number, pz: number): [number, number] => [(px - (x0 + x1) / 2) / M, (pz - (z0 + z1) / 2) / M];
      const fw = (x1 - x0) / M;
      const fd = (z1 - z0) / M;

      const victim = s.routes.find((r) => r.purpose === "to_victim");
      const targetRoom = victim?.to.startsWith("room:") ? victim.to.slice(5) : null;
      const focus = targetRoom ? rooms.find((r) => r.id === targetRoom)?.level : s.incident.origin?.floor;
      const hz = b.hazards;

      // levels with nothing going on are grey (Amil): Seraph's levels[].focus when it sends it; else a level is active
      // with fire or smoke, someone still inside, an engaged team, or a route's target
      const active = new Set<number>();
      if (levels.some((l) => typeof (l as FocusLevel).focus === "boolean")) {
        for (const l of levels) if ((l as FocusLevel).focus) active.add(l.level);
      } else {
        for (const h of hz) if ((h.kind === "fire" || h.kind === "smoke") && h.where.level != null) active.add(h.where.level);
        for (const o of s.occupants) if (o.status !== "safe_outside" && o.level != null) active.add(o.level);
        for (const t of s.crew.teams) if (t.status === "engaged" && t.location?.level != null) active.add(t.location.level);
        for (const r of s.routes) {
          const lv = r.to.startsWith("level:") ? Number(r.to.slice(6)) : r.to.startsWith("room:") ? rooms.find((x) => x.id === r.to.slice(5))?.level : undefined;
          if (lv != null && !Number.isNaN(lv)) active.add(lv);
        }
      }
      const now = performance.now();
      for (const lv of active) if (shown && !shown.has(lv) && !since.has(lv)) since.set(lv, now);
      for (const [lv, t0] of since) if (!active.has(lv) || now - t0 >= FADE) since.delete(lv);
      shown = active;
      const groups = new Map<number, THREE.Group>();
      // real storey heights when the model has them, plus the exploded gap; else an even step
      const elev = (l: Building["levels"][number]) => l.elevation_m;
      const hasElev = levels.every((l) => elev(l) != null);
      const floorY = (lv: number) => {
        const i = levels.findIndex((l) => l.level === lv);
        return (hasElev ? elev(levels[i])! - elev(levels[0])! + i * EXPLODE : i * STEP) + SLAB;
      };

      const stairAt = (st: ZonedStair): [number, number] | null => {
        const z = st.zones?.[0]?.zone;
        if (z && z.length) return W(...centroid(z));
        const p = pts.get(`stair:${st.id}`);
        return p ? W(...p) : null;
      };

      // Someone whose room is not on the plan (none, or a mis-heard one) is never drawn outside the building: they go
      // in their level's corridor, else next to the stair core, else the middle of the slab; the i-th one is moved
      // aside by 1.2 m steps while it stays on the slab. Plan coordinates.
      const onSlab = (lv: number, px: number, pz: number) =>
        outlines.get(lv)?.some((p) => inside(px, pz, p.outer) && !p.holes.some((h) => inside(px, pz, h))) ?? true;
      const near = (lv: number, i: number): [number, number] => {
        const corr = rooms.find((r) => r.level === lv && r.kind === "corridor");
        const c = corr && centroid(corr.zone as number[][]);
        const core = stairs.flatMap((st) => st.zones?.filter((z) => z.level === lv) ?? [])[0]?.zone;
        const slab = outlines.get(lv)?.reduce((a, p) => (Math.abs(area(p.outer)) > Math.abs(area(a.outer)) ? p : a));
        const mid = slab && centroid(slab.outer);
        const base: [number, number] =
          c && inside(c[0], c[1], corr!.zone as number[][]) ? c
          : core ? centroid(core)
          : mid && onSlab(lv, mid[0], mid[1]) ? mid
          : [(x0 + x1) / 2, (z0 + z1) / 2];
        const step = Math.ceil(i / 2) * 1.2 * M * (i % 2 ? 1 : -1);
        return i && onSlab(lv, base[0] + step, base[1]) ? [base[0] + step, base[1]] : base;
      };

      // the active ladder points: where an evacuation route ends at « ladder:<room> », the balcony or terrace the fire
      // service's ladder reaches; the other ladder points of the model stay as they are
      const ladders = new Set(s.routes.filter((r) => r.purpose === "evacuation" && r.to.startsWith("ladder:")).map((r) => r.to.slice(7)));

      let focusPlate: THREE.Object3D | null = null;
      for (const l of levels) {
        const fy = floorY(l.level);
        const hi = l.level === focus;
        const on = active.has(l.level);
        const lg = new THREE.Group();
        g.add(lg);
        groups.set(l.level, lg);

        // the slab is the plan: its real outline (levels[].outline from the IFC), else the union of the level's
        // rooms, with holes where the stair and lift shafts go through; a plain plate only when the level has no rooms
        const own = rooms.filter((r) => r.level === l.level);
        const shafts = [
          ...stairs.flatMap((st) => st.zones?.filter((z) => z.level === l.level).map((z) => z.zone) ?? []),
          ...own.filter((r) => r.kind === "elevator").map((r) => r.zone as number[][]),
        ];
        // (the fictional fixture has rooms on one level only and no corridor zone: it keeps plain plates)
        const ifc = rooms.some((r) => r.kind);
        const polys =
          outlines.get(l.level) ?? (ifc && own.length ? polygons(slabLoops(own.filter((r) => r.kind !== "elevator").map((r) => r.zone as number[][]), shafts)) : null);
        const plate = new THREE.Group();
        for (const shape of polys ? shapes(polys, W) : [rect(-fw / 2, -fd / 2, fw, fd)]) {
          const geo = new THREE.ExtrudeGeometry(shape, { depth: SLAB, bevelEnabled: false });
          geo.rotateX(-Math.PI / 2);
          const part = outlined(geo, solid("#000"), on ? line(C.ink, hi ? 3.5 : 2.8) : line(C.dim, 2.2));
          part.position.y = fy - SLAB;
          plate.add(part);
        }
        lg.add(plate);
        if (hi) focusPlate = plate;
        const corner = polys ? polys.flatMap((p) => p.outer).map(([px, pz]) => W(px, pz)).reduce((a, p) => (p[0] - p[1] < a[0] - a[1] ? p : a)) : [-fw / 2, fd / 2];
        at(tag(l.label, on ? "b3-level b3-level-hi" : "b3-level b3-level-dim"), [corner[0], fy - SLAB / 2, corner[1]], lg);

        // its rooms, flat on the plate: walls as lines; fire = red floor, the room we go to = lit floor; a grey
        // level has grey walls and no fills
        for (const r of rooms.filter((x) => x.level === l.level)) {
          const poly = (r.zone as number[][]).map(([px, pz]) => W(px, pz));
          // fire and smoke only as reported (Amil): solid once a crew confirmed it, soft while only « signalé »
          const here = (kind: string) => hz.filter((h) => h.kind === kind && sameRoom(h.where.room, r) && (h.where.level ?? r.level) === r.level);
          const fire = here("fire").length > 0;
          const smoke = here("smoke").length > 0;
          const sure = (kind: string) => here(kind).some((h) => h.source.confirmed);
          const lit = r.id === targetRoom;
          const ladder = ladders.has(r.id);
          if (lit) litPoly = poly.map(([wx, wz]) => new THREE.Vector3(wx, fy + FLAT, wz));
          if (on && (fire || lit || smoke || ladder)) {
            const floor = new THREE.Mesh(
              new THREE.ShapeGeometry(new THREE.Shape(poly.map(([wx, wz]) => new THREE.Vector2(wx, -wz)))),
              fire ? solid(C.fire, sure("fire") ? 1 : 0.35) : lit ? solid(C.lit) : ladder ? solid(C.life, 0.55) : solid(C.warn, sure("smoke") ? 0.45 : 0.2),
            );
            floor.rotation.x = -Math.PI / 2;
            floor.position.y = fy + FLAT / 2;
            lg.add(floor);
          }
          // terraces and other outside areas recede
          const out = r.kind === "exterior";
          lg.add(walls(poly, fy + FLAT, on ? line(fire ? C.fire : ladder ? C.life : out ? C.dim : C.line, out && !ladder ? 1.6 : 2.4) : line(out ? C.mute : C.dim, out ? 1.4 : 1.8)));
        }

        // smoke on a named spot without a zone (e.g. the corridor): a flat amber patch
        for (const h of hz.filter((x) => on && x.kind === "smoke" && x.where.level === l.level && x.where.room)) {
          if (rooms.some((r) => sameRoom(h.where.room, r) && r.level === l.level)) continue;
          const p = pts.get(h.where.room!) ?? pts.get(`room:${h.where.room}`);
          if (!p) continue;
          const [wx, wz] = W(...p);
          const patch = new THREE.Mesh(new THREE.CircleGeometry(95 / M, 48), solid(C.warn, h.source.confirmed ? 0.35 : 0.15));
          patch.rotation.x = -Math.PI / 2;
          patch.position.set(wx, fy + 0.02, wz);
          lg.add(patch);
        }

        // stairs on this plate: the IFC outline when there is one, else a square core at the plan point;
        // amber floor when smoke-logged
        for (const st of stairs) {
          const at0 = stairAt(st);
          if (!at0) continue;
          const [wx, wz] = at0;
          const zone = st.zones?.find((z) => z.level === l.level)?.zone;
          const smoky = st.status === "smoke" || hz.some((h) => h.kind === "smoke" && h.where.stair === st.id);
          // soft while the stair's smoke is only reported
          const said = hz.filter((h) => h.kind === "smoke" && h.where.stair === st.id);
          const soft = said.length > 0 && !said.some((h) => h.source.confirmed);
          const h = CORE / 2;
          const outline: [number, number][] = zone ? zone.map(([px, pz]) => W(px, pz)) : [[wx - h, wz - h], [wx + h, wz - h], [wx + h, wz + h], [wx - h, wz + h]];
          if (on && smoky) {
            const floor = new THREE.Mesh(new THREE.ShapeGeometry(new THREE.Shape(outline.map(([x, z]) => new THREE.Vector2(x, -z)))), solid(C.warn, soft ? 0.35 : 1));
            floor.rotation.x = -Math.PI / 2;
            floor.position.y = fy + FLAT / 2;
            lg.add(floor);
          }
          lg.add(walls(outline, fy + FLAT, on ? line(smoky ? C.warn : C.ink, 2.6) : line(C.dim, 2)));
          if (l === levels.at(-1)) at(tag(st.id, smoky ? "b3-warn b3-center" : "b3-center"), [wx, fy + 0.3, wz], g);
        }
      }

      // stair shafts: four vertical edges running through every plate, from the ground floor to the top
      for (const st of stairs) {
        const p = stairAt(st);
        if (!p) continue;
        const [wx, wz] = p;
        const smoky = st.status === "smoke" || hz.some((h) => h.kind === "smoke" && h.where.stair === st.id);
        const served = levels.filter((l) => !st.zones || st.zones.some((z) => z.level === l.level));
        const y0 = floorY(served[0].level) + FLAT;
        const y1 = floorY(served.at(-1)!.level) + FLAT;
        const h = CORE / 2;
        const corners: [number, number][] = st.zones?.[0] ? st.zones[0].zone.map(([px, pz]) => W(px, pz)) : [[wx - h, wz - h], [wx + h, wz - h], [wx + h, wz + h], [wx - h, wz + h]];
        const segs: number[] = [];
        for (const [cx, cz] of corners) segs.push(cx, y0, cz, cx, y1, cz);
        g.add(new LineSegments2(new LineSegmentsGeometry().setPositions(segs), line(smoky ? C.warn : C.ink, 2)));
      }

      // people where they are: in their room when we know it, else inside their level (see near), marked « ? »
      const spot = (level: number, room?: string): [number, number] | null => {
        const r = rooms.find((x) => sameRoom(room, x) && x.level === level);
        const p = r ? centroid(r.zone as number[][]) : room ? (pts.get(`room:${room}`) ?? pts.get(room)) : undefined;
        return p ? W(...p) : null;
      };
      const indoors = s.occupants.filter((o) => o.status !== "safe_outside" && o.level != null && levels.some((l) => l.level === o.level));
      const strays = new Map<number, Occupant[]>();
      for (const o of indoors) if (!spot(o.level!, o.room)) strays.set(o.level!, [...(strays.get(o.level!) ?? []), o]);
      const where = (o: Occupant): V3 => {
        const xz = spot(o.level!, o.room) ?? W(...near(o.level!, strays.get(o.level!)!.indexOf(o)));
        return [xz[0], floorY(o.level!) + 0.1, xz[1]];
      };

      // No route line: the state gives the route as a list of nodes (stair → corridor → room), not a path. Joining
      // them straight would cross walls (docs/07-safety-rules.md rule 2). The target room is lit; the path is drawn
      // once Seraph sends one computed on the plan (through the doors).

      // callouts: only what calls for attention — the fire, people to reach, our team, a caller heading into smoke
      const list: Note[] = [];
      const v3 = (p: V3) => new THREE.Vector3(...p);
      for (const h of hz.filter((x) => x.kind === "fire" && x.where.level != null && active.has(x.where.level) && x.where.room)) {
        const r = rooms.find((x) => x.id === h.where.room && x.level === h.where.level);
        const p = r ? centroid(r.zone as number[][]) : pts.get(`room:${h.where.room}`);
        if (!p) continue;
        const name = b.plan?.points.find((x) => x.name === `room:${h.where.room}`)?.label.replace(/^\S+\s/, "");
        const [fx, fz] = W(...p);
        list.push({
          pos: v3([fx, floorY(h.where.level!) + 0.1, fz]),
          level: h.where.level!,
          tone: C.fire,
          rank: 0,
          title: "Feu",
          index: levelLabel(s, h.where.level),
          lines: [`${h.where.room}${name ? ` · ${name}` : ""}`, `→ ${h.source.confirmed ? "confirmé" : "signalé"} · ${h.source.label}`],
        });
      }
      const smoky = (stair?: string) => b.stairs.some((st) => `stair:${st.id}` === stair && st.status !== "clear");
      const noted = new Set<string>();
      for (const o of indoors) {
        if (!active.has(o.level!)) continue;
        const urgent = o.status === "needs_help" || o.status === "trapped";
        const target = o.room === targetRoom;
        const intoSmoke = o.status === "moving" && smoky(o.heading_to);
        if (!urgent && !target && !intoSmoke) continue;
        noted.add(o.id);
        const n = o.people_count && o.people_count > 1 ? `${o.people_count} pers. · ` : "";
        list.push({
          pos: v3(where(o)),
          level: o.level!,
          tone: urgent ? C.fire : intoSmoke ? C.warn : C.life,
          rank: urgent ? 1 : intoSmoke ? 2 : 4,
          title: spot(o.level!, o.room) ? o.room! : "Pièce à confirmer",
          index: levelLabel(s, o.level),
          lines: intoSmoke
            ? [`${o.name ?? o.id} → esc. ${o.heading_to!.split(":")[1]}`, "→ escalier enfumé"]
            : [`${n}${o.name ?? o.id}${o.mobility_issue ? " · PMR" : ""}`, `→ ${OCC_STATUS[o.status]}`],
        });
      }
      for (const id of ladders) {
        const r = rooms.find((x) => x.id === id);
        if (!r || !active.has(r.level)) continue;
        const [lx, lz] = W(...centroid(r.zone as number[][]));
        const who = s.occupants.filter((o) => o.heading_to === `ladder:${id}` && o.status !== "safe_outside");
        list.push({
          pos: v3([lx, floorY(r.level) + 0.1, lz]),
          level: r.level,
          tone: C.life,
          rank: 2,
          title: "Échelle",
          index: levelLabel(s, r.level),
          lines: [who.map((o) => o.name ?? o.id).join(", ") || "—", `→ ${(r.label ?? id).replace(/^(\S+)\s+/, "$1 · ")}`],
        });
      }
      for (const t of s.crew.teams.filter((x) => x.status === "engaged" && x.location?.level != null && active.has(x.location.level))) {
        const lv = t.location!.level!;
        const loc = t.location;
        const room = loc?.room ? rooms.find((x) => sameRoom(loc.room, x) && x.level === lv) : undefined;
        const st = loc?.stair ? stairs.find((x) => x.id === loc.stair) : undefined;
        const named = loc?.room ? (pts.get(loc.room) ?? pts.get(`room:${loc.room}`)) : undefined;
        const p = room ? W(...centroid(room.zone as number[][])) : named ? W(...named) : st ? stairAt(st) : null;
        const [tx, tz] = p ?? W(...near(lv, 0));
        list.push({
          pos: v3([tx, floorY(lv) + 0.1, tz]),
          level: lv,
          tone: C.ink,
          rank: 3,
          title: t.id,
          index: levelLabel(s, lv),
          lines: [
            loc?.room === "corridor" ? "Circulation" : room || named ? loc!.room! : st ? `Esc. ${st.id}` : "Pièce à confirmer",
            t.exit_by ? `→ sortie ${hm(t.exit_by)}` : `→ ${t.label}`,
          ],
        });
      }
      for (const o of indoors) if (!noted.has(o.id) && active.has(o.level!)) at(person(o, !spot(o.level!, o.room)), where(o), groups.get(o.level!)!);

      // Seraph's route, only when it is a computed path on the plan (through the gaps between zones, never a guess):
      // our way in white, an evacuation in Silex green; a dark casing keeps it readable on the lit room
      for (const r of s.routes as PathRoute[]) {
        if (!r.path || r.path.length < 2 || r.path_level == null || !levels.some((l) => l.level === r.path_level)) continue;
        const y = floorY(r.path_level) + 0.06;
        const pts3 = r.path.map(([px, pz]): V3 => {
          const [wx, wz] = W(px, pz);
          return [wx, y, wz];
        });
        route(groups.get(r.path_level)!, pts3, r.purpose === "evacuation" ? C.life : C.ink);
      }
      // most urgent first: fire, someone to rescue, someone heading into smoke, our team, the room we go to
      notes = list.sort((a, b) => a.rank - b.rank).slice(0, col.max).map(note);

      // a level that just became active comes up from grey: its lines from grey to their colour, its fills and tags
      // from transparent
      fades = [...since].map(([lv, t0]) => {
        const f: Fade = { t0, lines: [], fills: [], els: [] };
        groups.get(lv)?.traverse((o) => {
          if (o instanceof CSS2DObject) f.els.push(o.element);
          else if (o instanceof LineSegments2 || o instanceof Line2) {
            const m = o.material as LineMaterial;
            if (m.color.getHSL({ h: 0, s: 0, l: 0 }).l > 0.1) f.lines.push([m, m.color.clone()]); // not the route's dark casing
          } else if (o instanceof THREE.Mesh && o.material instanceof THREE.MeshBasicMaterial && o.material.color.getHex() !== 0) {
            f.fills.push([o.material, o.material.opacity, o.material.transparent]);
            o.material.transparent = true;
          }
        });
        for (const n of notes) if (n.level === lv) f.els.push(n.box, n.frame, n.leader, n.leaderDark, n.mark);
        return f;
      });
      fadeStep(performance.now());

      // first build: aim at the model and fit it; later builds keep the user's view
      const bb = new THREE.Box3().setFromObject(zoom === "focus" && focusPlate ? focusPlate : g);
      if (zoom === "focus") bb.expandByVector(new THREE.Vector3(0, STEP * 0.6, 0)); // a glimpse of the levels around
      const center = bb.getCenter(new THREE.Vector3());
      if (!fitted) {
        fitted = true;
        controls.target.copy(center);
        camera.position.set(center.x + 200 * Math.cos(ELEV) * Math.sin(AZ), center.y + 200 * Math.sin(ELEV), center.z + 200 * Math.cos(ELEV) * Math.cos(AZ));
        camera.lookAt(center);
        camera.updateMatrixWorld();
        let hw = 0;
        let hh = 0;
        for (let i = 0; i < 8; i++) {
          const c = new THREE.Vector3(i & 1 ? bb.max.x : bb.min.x, i & 2 ? bb.max.y : bb.min.y, i & 4 ? bb.max.z : bb.min.z);
          const v = c.applyMatrix4(camera.matrixWorldInverse);
          hw = Math.max(hw, Math.abs(v.x));
          hh = Math.max(hh, Math.abs(v.y));
        }
        // the model fits in the space left of the callout column (main: room for the level labels on the left;
        // split: centred on the screen), its target at the centre of that space
        const rx = wide ? box.w / 2 : (FIT.left + col.x - FIT.gap) / 2;
        const rw = wide ? 2 * (col.x - FIT.gap - box.w / 2) : col.x - FIT.gap - FIT.left;
        const ppu = Math.min(rw / (2 * hw), (box.h - 2 * FIT.top) / (2 * hh)) / (zoom === "focus" ? 1.12 : 1);
        const half = box.h / (2 * ppu);
        camera.left = -rx / ppu;
        camera.right = (box.w - rx) / ppu;
        camera.top = half;
        camera.bottom = -half;
        camera.zoom = 1;
        camera.updateProjectionMatrix();
        controls.update();
      }
    }

    function route(g: THREE.Group, path: V3[], color: string) {
      const flat = path.flat();
      const casing = new Line2(new LineGeometry().setPositions(flat), line("#0b0a0a", 10));
      casing.renderOrder = 1;
      g.add(casing);
      const core = new Line2(new LineGeometry().setPositions(flat), line(color, 5));
      core.renderOrder = 2;
      g.add(core);
      const a = new THREE.Vector3(...path[path.length - 2]);
      const z = new THREE.Vector3(...path[path.length - 1]);
      const head = new THREE.Mesh(new THREE.ConeGeometry(0.5, 1.2, 24), solid(color));
      head.position.copy(z);
      head.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), z.clone().sub(a).normalize());
      g.add(head);
    }

    // a closed outline lying on a plate
    function walls(poly: [number, number][], y: number, mat: LineMaterial) {
      const segs: number[] = [];
      poly.forEach(([ax, az], i) => {
        const [bx, bz] = poly[(i + 1) % poly.length];
        segs.push(ax, y, az, bx, y, bz);
      });
      return new LineSegments2(new LineSegmentsGeometry().setPositions(segs), mat);
    }

    // a flat pastille, « ? » when their room is not on the plan
    function person(o: Occupant, unsure: boolean) {
      const urgent = o.status === "needs_help" || o.status === "trapped";
      const unknown = o.status === "no_answer" || o.status === "unknown" || o.status === "calling";
      const d = document.createElement("div");
      d.className = "b3-mark";
      const dot = document.createElement("i");
      dot.className = `b3-dot ${urgent ? "b3-dot-fire" : unknown ? "b3-dot-dim" : o.status === "moving" ? "b3-dot-warn" : "b3-dot-life"}`;
      d.appendChild(dot);
      if (unsure) d.append(tag("?", "b3-q"));
      return d;
    }

    function note(n: Note): NoteEl {
      const boxEl = document.createElement("div");
      boxEl.className = "b3-note";
      const head = document.createElement("div");
      head.className = "b3-note-head";
      head.innerHTML = `<span class="b3-note-title"><i style="background:${n.tone}"></i></span><span class="b3-note-idx"></span>`;
      head.querySelector(".b3-note-title")!.append(n.title);
      head.querySelector(".b3-note-idx")!.textContent = n.index;
      boxEl.appendChild(head);
      for (const l of n.lines) {
        const d = document.createElement("div");
        d.className = "b3-note-line";
        d.textContent = l;
        boxEl.appendChild(d);
      }
      notesBox.appendChild(boxEl);
      const path = (cls: string, parent: SVGElement) => {
        const p = document.createElementNS(SVG_NS, "path");
        p.setAttribute("class", cls);
        parent.appendChild(p);
        return p;
      };
      const leader = path("b3-note-leader", gLight);
      const leaderDark = path("b3-note-leader b3-note-leader-dark", gDark);
      const frame = path("b3-note-frame", notesSvg);
      const mark = document.createElementNS(SVG_NS, "g");
      mark.innerHTML = `<rect x="-7" y="-7" width="14" height="14" class="b3-note-mark"/><rect x="-3.5" y="-3.5" width="7" height="7" fill="${n.tone}"/>`;
      notesSvg.appendChild(mark);
      return { ...n, box: boxEl, frame, leader, leaderDark, mark, h: boxEl.offsetHeight };
    }

    // every frame: anchors follow the model, labels stack in the column in the anchors' order, never overlapping
    function layoutNotes() {
      litClip.setAttribute(
        "points",
        litPoly
          .map((p) => {
            const v = p.clone().project(camera);
            return `${((v.x + 1) / 2) * box.w},${((1 - v.y) / 2) * box.h}`;
          })
          .join(" "),
      );
      for (const n of notes) n.h = n.box.offsetHeight; // read first (fonts may load late), then write
      const at = notes
        .map((n) => {
          const v = n.pos.clone().project(camera);
          return { n, x: ((v.x + 1) / 2) * box.w, y: ((1 - v.y) / 2) * box.h };
        })
        .sort((a, b) => a.y - b.y);
      let y = col.top;
      const tops = at.map((a) => {
        const t = Math.max(a.y - a.n.h / 2, y);
        y = t + a.n.h + NOTE.gap;
        return t;
      });
      const over = y - NOTE.gap - col.bottom;
      if (over > 0) for (let i = 0; i < tops.length; i++) tops[i] = Math.max(col.top, tops[i] - over);
      at.forEach(({ n, x, y: ay }, i) => {
        const t = tops[i];
        const { w, cut } = NOTE;
        const bx = col.x;
        const h = n.h;
        n.box.style.transform = `translate(${bx}px, ${t}px)`;
        n.frame.setAttribute("d", `M${bx},${t}H${bx + w - cut}L${bx + w},${t + cut}V${t + h - cut}L${bx + w - cut},${t + h}H${bx}Z`);
        const d = `M${x},${ay}H${bx - 40}L${bx},${t + h}`;
        n.leader.setAttribute("d", d);
        n.leaderDark.setAttribute("d", d);
        n.mark.setAttribute("transform", `translate(${x},${ay})`);
      });
    }

    const grey = new THREE.Color(C.dim);
    function fadeStep(now: number) {
      fades = fades.filter((f) => {
        const k = Math.min(1, Math.max(0, (now - f.t0) / FADE));
        const e = 1 - (1 - k) ** 3;
        for (const [m, to] of f.lines) m.color.copy(grey).lerp(to, e);
        for (const [m, to, transparent] of f.fills) {
          m.opacity = to * e;
          if (k === 1) m.transparent = transparent;
        }
        for (const el of f.els) el.style.opacity = k === 1 ? "" : String(e);
        return k < 1;
      });
    }

    let raf = 0;
    const frame = () => {
      raf = requestAnimationFrame(frame);
      if (fades.length) fadeStep(performance.now());
      controls.update();
      renderer.render(scene, camera);
      labels.render(scene, camera);
      layoutNotes();
    };
    frame();
    const grab = () => (renderer.domElement.style.cursor = "grabbing");
    const release = () => (renderer.domElement.style.cursor = "grab");
    renderer.domElement.addEventListener("pointerdown", grab);
    window.addEventListener("pointerup", release);

    api.current = {
      build,
      ratio: (r) => {
        renderer.setPixelRatio(r);
        renderer.setSize(box.w, box.h);
      },
    };
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("pointerup", release);
      controls.dispose();
      renderer.dispose();
      el.innerHTML = "";
      api.current = null;
    };
  }, [box.w, box.h, zoom]);

  useEffect(() => {
    api.current?.ratio(Math.min(3, window.devicePixelRatio * scale));
  }, [scale]);

  useEffect(() => {
    if (!state) return;
    const k = JSON.stringify([state.building, state.occupants, state.crew.teams, state.routes, state.incident.origin]);
    if (k === key.current) return;
    key.current = k;
    api.current?.build(state);
  }, [state]);

  return <div ref={host} className="absolute" style={{ left: box.x, top: box.y, width: box.w, height: box.h }} />;
}

// ───────── slab outlines ─────────

type Loop = [number, number][];

type Poly = { outer: Loop; holes: Loop[] };

/** levels[].outline in any of the shapes the IFC session may send: one loop, a list of loops (outer and holes by
 *  winding), {outer, holes}, or a list of {outer, holes} (a level in several parts). */
function readOutline(o: unknown): Poly[] | null {
  const isPt = (p: unknown) => Array.isArray(p) && p.length === 2 && typeof p[0] === "number";
  const isPoly = (p: unknown): p is Poly => !!p && typeof p === "object" && Array.isArray((p as Poly).outer) && (p as Poly).outer.length >= 3;
  if (!o) return null;
  if (Array.isArray(o) && o.length && isPt(o[0])) return [{ outer: o as Loop, holes: [] }];
  if (Array.isArray(o) && o.length && Array.isArray(o[0]) && isPt((o[0] as unknown[])[0])) return polygons(o as Loop[]);
  if (Array.isArray(o)) {
    const ps = o.filter(isPoly).map((p) => ({ outer: p.outer, holes: p.holes ?? [] }));
    return ps.length ? ps : null;
  }
  return isPoly(o) ? [{ outer: o.outer, holes: o.holes ?? [] }] : null;
}

/** Loops to polygons: the winding of the biggest loop marks the outers, the others are holes of the outer they sit in. */
function polygons(loops: Loop[]): Poly[] {
  if (!loops.length) return [];
  const big = loops.reduce((a, l) => (Math.abs(area(l)) > Math.abs(area(a)) ? l : a), loops[0]);
  const sign = Math.sign(area(big));
  const outers = loops.filter((l) => Math.sign(area(l)) === sign);
  const holes = loops.filter((l) => Math.sign(area(l)) !== sign);
  return outers.map((outer) => ({ outer, holes: holes.filter((h) => inside(h[0][0], h[0][1], outer)) }));
}

/** The union of a level's room zones as outline loops (plan units), with the shafts cut out. Rasterised on a 4-unit
 *  grid, closed by 2 cells so the gaps of the walls between rooms disappear, then traced and simplified. */
function slabLoops(zones: number[][][], holes: number[][][]): Loop[] {
  const N = 250;
  const S = 1000 / N;
  let grid = new Uint8Array(N * N);
  const paint = (poly: number[][], v: number) => {
    const xs = poly.map((p) => p[0]);
    const ys = poly.map((p) => p[1]);
    const i0 = Math.max(0, Math.floor(Math.min(...xs) / S));
    const i1 = Math.min(N - 1, Math.ceil(Math.max(...xs) / S));
    const j0 = Math.max(0, Math.floor(Math.min(...ys) / S));
    const j1 = Math.min(N - 1, Math.ceil(Math.max(...ys) / S));
    for (let j = j0; j <= j1; j++) for (let i = i0; i <= i1; i++) if (inside((i + 0.5) * S, (j + 0.5) * S, poly)) grid[j * N + i] = v;
  };
  const morph = (on: number, r: number) => {
    const out = new Uint8Array(N * N).fill(1 - on);
    for (let j = 0; j < N; j++)
      for (let i = 0; i < N; i++) {
        let hit = false;
        for (let dj = -r; dj <= r && !hit; dj++)
          for (let di = -r; di <= r && !hit; di++) {
            const x = i + di;
            const y = j + dj;
            if (x >= 0 && y >= 0 && x < N && y < N && grid[y * N + x] === on) hit = true;
          }
        out[j * N + i] = hit ? on : 1 - on;
      }
    grid = out;
  };
  zones.forEach((z) => paint(z, 1));
  morph(1, 2); // dilate: bridge the walls
  morph(0, 2); // erode: back to the outer face
  holes.forEach((z) => paint(z, 0));
  const filled = (i: number, j: number) => i >= 0 && j >= 0 && i < N && j < N && grid[j * N + i] === 1;

  // boundary edges, each cell walked clockwise (y down), kept only where the neighbour is empty
  const next = new Map<number, number[]>();
  const key = (x: number, y: number) => y * (N + 1) + x;
  const add = (a: number, b: number) => next.set(a, [...(next.get(a) ?? []), b]);
  for (let j = 0; j < N; j++)
    for (let i = 0; i < N; i++) {
      if (!filled(i, j)) continue;
      if (!filled(i, j - 1)) add(key(i, j), key(i + 1, j));
      if (!filled(i + 1, j)) add(key(i + 1, j), key(i + 1, j + 1));
      if (!filled(i, j + 1)) add(key(i + 1, j + 1), key(i, j + 1));
      if (!filled(i - 1, j)) add(key(i, j + 1), key(i, j));
    }
  const loops: Loop[] = [];
  for (const start of next.keys()) {
    while (next.get(start)?.length) {
      const loop: Loop = [];
      let k = start;
      do {
        loop.push([(k % (N + 1)) * S, Math.floor(k / (N + 1)) * S]);
        const outs = next.get(k)!;
        const n = outs.pop()!;
        k = n;
      } while (k !== start && next.get(k)?.length);
      if (loop.length >= 4) loops.push(simplify(loop, S * 1.2));
    }
  }
  return loops.filter((l) => l.length >= 3 && Math.abs(area(l)) > S * S * 6);
}

function inside(x: number, y: number, poly: number[][]) {
  let c = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const [xi, yi] = poly[i];
    const [xj, yj] = poly[j];
    if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) c = !c;
  }
  return c;
}

function area(l: Loop) {
  let a = 0;
  for (let i = 0; i < l.length; i++) {
    const [x1, y1] = l[i];
    const [x2, y2] = l[(i + 1) % l.length];
    a += x1 * y2 - x2 * y1;
  }
  return a / 2;
}

/** Douglas–Peucker on a closed loop: the staircase of the raster becomes straight walls and diagonals. */
function simplify(loop: Loop, tol: number): Loop {
  const dp = (pts: Loop): Loop => {
    if (pts.length < 3) return pts;
    const [ax, ay] = pts[0];
    const [bx, by] = pts[pts.length - 1];
    const len = Math.hypot(bx - ax, by - ay) || 1;
    let far = 0;
    let at = 0;
    for (let i = 1; i < pts.length - 1; i++) {
      const d = Math.abs((by - ay) * pts[i][0] - (bx - ax) * pts[i][1] + bx * ay - by * ax) / len;
      if (d > far) [far, at] = [d, i];
    }
    return far > tol ? [...dp(pts.slice(0, at + 1)).slice(0, -1), ...dp(pts.slice(at))] : [pts[0], pts[pts.length - 1]];
  };
  let far = 0;
  let at = 0;
  loop.forEach(([x, y], i) => {
    const d = Math.hypot(x - loop[0][0], y - loop[0][1]);
    if (d > far) [far, at] = [d, i];
  });
  const a = dp(loop.slice(0, at + 1));
  const b = dp([...loop.slice(at), loop[0]]);
  return [...a.slice(0, -1), ...b.slice(0, -1)];
}

/** Polygons (plan units) → THREE shapes in world x/z, each with its holes. */
function shapes(polys: Poly[], W: (px: number, pz: number) => [number, number]): THREE.Shape[] {
  const v = (l: Loop) => l.map(([px, pz]) => {
    const [x, z] = W(px, pz);
    return new THREE.Vector2(x, -z);
  });
  return polys.map((p) => {
    const shape = new THREE.Shape(v(p.outer));
    for (const h of p.holes) shape.holes.push(new THREE.Path(v(h)));
    return shape;
  });
}

function rect(x: number, z: number, w: number, d: number): THREE.Shape {
  return new THREE.Shape([new THREE.Vector2(x, -z), new THREE.Vector2(x + w, -z), new THREE.Vector2(x + w, -(z + d)), new THREE.Vector2(x, -(z + d))]);
}

function centroid(poly: number[][]): [number, number] {
  return [poly.reduce((a, p) => a + p[0], 0) / poly.length, poly.reduce((a, p) => a + p[1], 0) / poly.length];
}
