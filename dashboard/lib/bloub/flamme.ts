// Seraph's flame for the judges' tour: the Bloub engine (copied as is, see README.md) with a flame body. Seraph means
// "the burning one". Only this file is ours in lib/bloub/.
import { PROFILE_SAMPLES } from "./profiles";
import { hullOfCircles, profileFromPolygon } from "./shape";

const ANGLES = Array.from({ length: PROFILE_SAMPLES }, (_, i) => (i / PROFILE_SAMPLES) * Math.PI * 2);

/** Bloub's droplet with its tip leaning right and two tongues rippling up its sides (y points down). */
function flameProfile(): number[] {
  const drop = profileFromPolygon(hullOfCircles(0, 0.3, 0.64, 0.2, -1.02, 0.04), 0, 0);
  const radii = drop.map((r, i) => {
    const a = ANGLES[i] ?? 0;
    const up = Math.max(0, -Math.sin(a)); // 1 at the top of the screen, 0 on the lower half
    return r * (1 + 0.08 * up * up * Math.sin(4 * a + 0.8));
  });
  const peak = Math.max(...radii);
  return radii.map((r) => (r * 1.04) / peak);
}

export const FLAME_RADII = flameProfile();

/** The module colours of brand/tokens.css: the flame burns in the colour of whoever acts. */
export const FLAME_COLOR = {
  seraph: "#f2560f",
  gabriel: "#6b84ff",
  rosetta: "#e45cc2",
  silex: "#3fd68a",
  halo: "#f5f5f4",
} as const;

export type FlameModule = keyof typeof FLAME_COLOR;
