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
import type { IncidentState, Occupant, Route } from "@/lib/types";
import { OCC_STATUS, hm, levelLabel } from "@/lib/fr";

// Colours from brand/tokens.css, by meaning: fire and danger = Seraph (blackbody), smoke = Seraph 300, people = Silex,
// structure and our crews = Halo white.
const C = { ink: "#ffffff", line: "#d0cecb", fire: "#f2560f", warn: "#ff9c5a", life: "#3fd68a", lit: "#e7e6e4" };
const M = 50; // plan units (0–1000) per metre
const STEP = 9; // vertical distance between two floor plates
const SLAB = 0.4;
const FLAT = 0.03; // the plan is drawn flat on the plate, just above its top face
const CORE = 1.6; // stair core, a small square on every plate
const ELEV = (24 * Math.PI) / 180; // starting view
const AZ = 0.62;

type Box = { x: number; y: number; w: number; h: number };
// Seraph serves these on routes (status/seraph.md); not in contracts/types.ts yet — requested from Amil
type PathRoute = Route & { path?: [number, number][]; path_level?: number; path_image_id?: string };
type V3 = [number, number, number];
type Note = { pos: THREE.Vector3; tone: string; title: string; index: string; lines: string[]; rank: number };
type NoteEl = Note & { box: HTMLDivElement; frame: SVGPathElement; leader: SVGPathElement; leaderDark: SVGPathElement; mark: SVGGElement; h: number };

// callouts, in the container's px: a column right of the building, above the radio
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
      const rooms = b.rooms.filter((r) => r.zone && r.zone.length >= 3);
      const all = [...rooms.flatMap((r) => r.zone as number[][]), ...pts.values()];
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
      const floorY = (lv: number) => levels.findIndex((l) => l.level === lv) * STEP + SLAB;

      let focusPlate: THREE.Object3D | null = null;
      for (const l of levels) {
        const fy = floorY(l.level);
        const hi = l.level === focus;

        // the floor plate
        const plate = outlined(new THREE.BoxGeometry(fw, SLAB, fd), solid("#000"), line(hi ? C.ink : C.line, hi ? 3.5 : 2.4));
        plate.position.set(0, fy - SLAB / 2, 0);
        g.add(plate);
        if (hi) focusPlate = plate;
        at(tag(l.label, hi ? "b3-level b3-level-hi" : "b3-level"), [-fw / 2, fy - SLAB / 2, fd / 2], g);

        // its rooms, flat on the plate: walls as lines; fire = red floor, the room we go to = lit floor
        for (const r of rooms.filter((x) => x.level === l.level)) {
          const poly = (r.zone as number[][]).map(([px, pz]) => W(px, pz));
          const fire = hz.some((h) => h.kind === "fire" && h.where.room === r.id);
          const smoke = hz.some((h) => h.kind === "smoke" && h.where.room === r.id);
          const lit = r.id === targetRoom;
          if (lit) litPoly = poly.map(([wx, wz]) => new THREE.Vector3(wx, fy + FLAT, wz));
          if (fire || lit || smoke) {
            const floor = new THREE.Mesh(
              new THREE.ShapeGeometry(new THREE.Shape(poly.map(([wx, wz]) => new THREE.Vector2(wx, -wz)))),
              fire ? solid(C.fire) : lit ? solid(C.lit) : solid(C.warn, 0.45),
            );
            floor.rotation.x = -Math.PI / 2;
            floor.position.y = fy + FLAT / 2;
            g.add(floor);
          }
          g.add(walls(poly, fy + FLAT, line(fire ? C.fire : C.line, 2.4)));
        }

        // smoke on a named spot without a zone (e.g. the corridor): a flat amber patch
        for (const h of hz.filter((x) => x.kind === "smoke" && x.where.level === l.level && x.where.room)) {
          if (rooms.some((r) => r.id === h.where.room && r.level === l.level)) continue;
          const p = pts.get(h.where.room!) ?? pts.get(`room:${h.where.room}`);
          if (!p) continue;
          const [wx, wz] = W(...p);
          const patch = new THREE.Mesh(new THREE.CircleGeometry(95 / M, 48), solid(C.warn, 0.35));
          patch.rotation.x = -Math.PI / 2;
          patch.position.set(wx, fy + 0.02, wz);
          g.add(patch);
        }

        // stair cores: a flat square on every plate, amber floor when smoke-logged
        for (const st of b.stairs) {
          const p = pts.get(`stair:${st.id}`);
          if (!p) continue;
          const [wx, wz] = W(...p);
          const smoky = st.status === "smoke" || hz.some((h) => h.kind === "smoke" && h.where.stair === st.id);
          const h = CORE / 2;
          const sq: [number, number][] = [[wx - h, wz - h], [wx + h, wz - h], [wx + h, wz + h], [wx - h, wz + h]];
          if (smoky) {
            const floor = new THREE.Mesh(new THREE.PlaneGeometry(CORE, CORE), solid(C.warn));
            floor.rotation.x = -Math.PI / 2;
            floor.position.set(wx, fy + FLAT / 2, wz);
            g.add(floor);
          }
          g.add(walls(sq, fy + FLAT, line(smoky ? C.warn : C.ink, 2.6)));
          if (l === levels.at(-1)) at(tag(st.id, smoky ? "b3-warn b3-center" : "b3-center"), [wx, fy + 0.3, wz], g);
        }
      }

      // stair shafts: four vertical edges running through every plate, from the ground floor to the top
      for (const st of b.stairs) {
        const p = pts.get(`stair:${st.id}`);
        if (!p) continue;
        const [wx, wz] = W(...p);
        const smoky = st.status === "smoke" || hz.some((h) => h.kind === "smoke" && h.where.stair === st.id);
        const y0 = floorY(levels[0].level) + FLAT;
        const y1 = floorY(levels.at(-1)!.level) + FLAT;
        const h = CORE / 2;
        const segs: number[] = [];
        for (const [dx, dz] of [[-h, -h], [h, -h], [h, h], [-h, h]]) segs.push(wx + dx, y0, wz + dz, wx + dx, y1, wz + dz);
        g.add(new LineSegments2(new LineSegmentsGeometry().setPositions(segs), line(smoky ? C.warn : C.ink, 2)));
      }

      // people where they are: in their room when we know it, else along the front edge of their plate
      const spot = (level: number, room?: string): [number, number] | null => {
        const r = rooms.find((x) => x.id === room && x.level === level);
        const p = r ? centroid(r.zone as number[][]) : room ? (pts.get(`room:${room}`) ?? pts.get(room)) : undefined;
        return p ? W(...p) : null;
      };
      const inside = s.occupants.filter((o) => o.status !== "safe_outside" && o.level != null && levels.some((l) => l.level === o.level));
      const lanes = new Map<number, Occupant[]>();
      for (const o of inside) if (!spot(o.level!, o.room)) lanes.set(o.level!, [...(lanes.get(o.level!) ?? []), o]);
      const where = (o: Occupant): V3 => {
        const xz = spot(o.level!, o.room);
        if (xz) return [xz[0], floorY(o.level!) + 0.1, xz[1]];
        const lane = lanes.get(o.level!)!;
        return [-fw / 2 + (fw * (lane.indexOf(o) + 1)) / (lane.length + 1), floorY(o.level!) + 0.1, fd / 2 - 1.5];
      };

      // No route line: the state gives the route as a list of nodes (stair → corridor → room), not a path. Joining
      // them straight would cross walls (docs/07-safety-rules.md rule 2). The target room is lit; the path is drawn
      // once Seraph sends one computed on the plan (through the doors).

      // callouts: only what calls for attention — the fire, people to reach, our team, a caller heading into smoke
      const list: Note[] = [];
      const v3 = (p: V3) => new THREE.Vector3(...p);
      for (const h of hz.filter((x) => x.kind === "fire" && x.where.level != null && x.where.room)) {
        const r = rooms.find((x) => x.id === h.where.room && x.level === h.where.level);
        const p = r ? centroid(r.zone as number[][]) : pts.get(`room:${h.where.room}`);
        if (!p) continue;
        const name = b.plan?.points.find((x) => x.name === `room:${h.where.room}`)?.label.replace(/^\S+\s/, "");
        const [fx, fz] = W(...p);
        list.push({
          pos: v3([fx, floorY(h.where.level!) + 0.1, fz]),
          tone: C.fire,
          rank: 0,
          title: "Feu",
          index: levelLabel(s, h.where.level),
          lines: [`${h.where.room}${name ? ` · ${name}` : ""}`, `→ ${h.source.label}`],
        });
      }
      const smoky = (stair?: string) => b.stairs.some((st) => `stair:${st.id}` === stair && st.status !== "clear");
      const noted = new Set<string>();
      for (const o of inside) {
        const urgent = o.status === "needs_help" || o.status === "trapped";
        const target = o.room === targetRoom;
        const intoSmoke = o.status === "moving" && smoky(o.heading_to);
        if (!urgent && !target && !intoSmoke) continue;
        noted.add(o.id);
        const n = o.people_count && o.people_count > 1 ? `${o.people_count} pers. · ` : "";
        list.push({
          pos: v3(where(o)),
          tone: urgent ? C.fire : intoSmoke ? C.warn : C.life,
          rank: urgent ? 1 : intoSmoke ? 2 : 4,
          title: o.room ?? "?",
          index: levelLabel(s, o.level),
          lines: intoSmoke
            ? [`${o.name ?? o.id} → esc. ${o.heading_to!.split(":")[1]}`, "→ escalier enfumé"]
            : [`${n}${o.name ?? o.id}${o.mobility_issue ? " · PMR" : ""}`, `→ ${OCC_STATUS[o.status]}`],
        });
      }
      for (const t of s.crew.teams.filter((x) => x.status === "engaged" && x.location?.level != null)) {
        const lv = t.location!.level!;
        const loc = t.location;
        const p = loc?.room === "corridor" ? pts.get("corridor") : loc?.room ? pts.get(`room:${loc.room}`) : loc?.stair ? pts.get(`stair:${loc.stair}`) : undefined;
        const [tx, tz] = p ? W(...p) : [0, 0];
        list.push({
          pos: v3([tx, floorY(lv) + 0.1, tz]),
          tone: C.ink,
          rank: 3,
          title: t.id,
          index: levelLabel(s, lv),
          lines: [loc?.room === "corridor" ? "Circulation" : (loc?.room ?? (loc?.stair ? `Esc. ${loc.stair}` : "—")), t.exit_by ? `→ sortie ${hm(t.exit_by)}` : `→ ${t.label}`],
        });
      }
      for (const o of inside) if (!noted.has(o.id)) at(person(o), where(o), g);

      // Seraph's route, only when it is a computed path on the plan (through the gaps between zones, never a guess):
      // our way in white, an evacuation in Silex green; a dark casing keeps it readable on the lit room
      for (const r of s.routes as PathRoute[]) {
        if (!r.path || r.path.length < 2 || r.path_level == null || !levels.some((l) => l.level === r.path_level)) continue;
        const y = floorY(r.path_level) + 0.06;
        const pts3 = r.path.map(([px, pz]): V3 => {
          const [wx, wz] = W(px, pz);
          return [wx, y, wz];
        });
        route(g, pts3, r.purpose === "evacuation" ? C.life : C.ink);
      }
      // most urgent first: fire, someone to rescue, someone heading into smoke, our team, the room we go to
      notes = list.sort((a, b) => a.rank - b.rank).slice(0, col.max).map(note);

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
        const half = Math.max(hh, hw / (box.w / box.h)) * (zoom === "focus" ? 1.12 : 1.02);
        camera.left = -half * (box.w / box.h);
        camera.right = half * (box.w / box.h);
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

    // a flat pastille; a short tag only when it calls for a decision
    function person(o: Occupant) {
      const urgent = o.status === "needs_help" || o.status === "trapped";
      const unknown = o.status === "no_answer" || o.status === "unknown" || o.status === "calling";
      const d = document.createElement("div");
      d.className = "b3-mark";
      const dot = document.createElement("i");
      dot.className = `b3-dot ${urgent ? "b3-dot-fire" : unknown ? "b3-dot-dim" : o.status === "moving" ? "b3-dot-warn" : "b3-dot-life"}`;
      d.appendChild(dot);
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

    let raf = 0;
    const frame = () => {
      raf = requestAnimationFrame(frame);
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

function centroid(poly: number[][]): [number, number] {
  return [poly.reduce((a, p) => a + p[0], 0) / poly.length, poly.reduce((a, p) => a + p[1], 0) / poly.length];
}
