# Halo schemes — hard rules (from Amil, non-negotiable)

Halo is an emergency device on a firefighter's wrist. They must see what happens where it happens, in one glance.
Every view must pass `node halo/kit/check-view.mjs <view.html>` before it is served.

1. **Full screen, landscape, native app.** One scheme, big. Draw inside `Halo.AREA`.
2. **No text panels.** No sentences, no captions, no sources, no « vue construite par… ». Only short tags on the
   drawing (`E2`, `3.12`, `B1`) and the instruction card.
3. **Instruction card** (`f.panel`): right side, 2–4 imperative lines (« Entrez par E2 »), **one line each, never
   wraps** (≤ 18 characters), plain words, **no pictograms, no fluff**.
4. **The card never touches the drawing.** Keep empty ground between them, or the card reads as being about the
   nearest element.
5. **The target is flat white.** No dots, no halftone, no checkerboard, no gradient, no glow, no texture.
6. **Flat fills everywhere** (buildings, rooms, roads). Gradients only inside fire and smoke zones. No glow, no bloom,
   no shadow, no shading spilling onto roads.
7. **Grain only on the background** (the kit's ground) and inside fire/smoke. Never on buildings or roads.
8. **Motion only where something happens**: the route, the one entrance to take, fire, smoke, danger triangles, the
   air countdown. Buildings, roads, the target and the ground never move. No breathing, pulsing or blinking to
   « bring life ».
9. **Art direction = the reference**: big geometric shapes, thin white outlines, small black tags, 45° composition for
   top views (`Halo.scene({rotate: -45})`).
10. **Nothing under the Dynamic Island** or the screen edges: stay inside `Halo.AREA`.
11. **The view adds no style of its own**: no `<style>`, no `style=`, no gradients, filters, patterns, keyframes or
    timers. Everything comes from the kit.
12. Colours carry meaning only (SITAC): red fire/danger, amber smoke/warning, orange gas/elec, blue water, green
    people, white structure/our crews/route, grey unknown.
13. Positions and routes come from the state. Never invent one.
14. **Text never blinks.** Only pictograms, triangles, rings and the air dial's ticks blink; words, numbers and tags
    stay still so they can be read.
15. **Floors with nothing special are grey** (« les étages où il n'y a rien de spécial doivent être grisés »): no fill, no
    coloured tag. In focus: fire/smoke, someone inside, an engaged team, a route's target (Seraph's
    `building.levels[].focus` when present). `floorStack({focus: Halo.focusLevels(state)})` does it.
