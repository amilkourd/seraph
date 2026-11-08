# brand/ — Seraph art direction

Art direction only: colours, typography, the ring. Open `index.html` (served next to the two other files).

- `tokens.css` — one colour and one tint scale (50 → 950) per module: `--halo-*`, `--seraph-*`, `--gabriel-*`,
  `--rosetta-*`, `--silex-*`, plus `--halo` / `--seraph` / … for each module's colour. Fonts and type scale.
- `seraph-field.js` — the ring of light (WebGL, no deps) in any module's colour:
  `SeraphField.mount(el, { module: 'gabriel' })`, `ring.set({ module: 'silex' })`.

| Module | Colour | Reference |
|---|---|---|
| Halo | `#f5f5f4` (50) | thermal white-hot; its greys are the system neutrals |
| Seraph | `#f2560f` (500) | blackbody, 800 → 3000 K |
| Gabriel | `#6b84ff` (400) | blue flame, CH* 431 nm |
| Rosetta | `#e45cc2` (400) | ironbow thermal magenta |
| Silex | `#3fd68a` (400) | green flame, C₂ 516 nm |

Type: Archivo (titles; caps at wdth 125 for the wordmark), Geist (text), Geist Mono (labels, caps +0.08em).
