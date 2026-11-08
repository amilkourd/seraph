import type { Tone } from "@/lib/fr";

/** Status square: the colour, always next to a label that says what it means. */
export function Sq({ tone, pulse = false }: { tone: Tone; pulse?: boolean }) {
  return <i className={`sq ${tone} ${pulse ? "pulse" : ""}`} />;
}
