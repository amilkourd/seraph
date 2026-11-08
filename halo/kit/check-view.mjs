#!/usr/bin/env node
// Rejects a Halo view that breaks halo/kit/RULES.md. Silex runs it on every view Devin writes, before serving it.
// Usage: node halo/kit/check-view.mjs <view.html> [...]   → exit 1 when a view breaks a rule.
import { readFileSync } from 'node:fs';

const RULES = [
  // [rule number in RULES.md, what is wrong, test on the code without comments]
  [1, 'must draw full screen with Halo.frame', c => !/Halo\.frame\(/.test(c)],
  [3, 'must give the instruction card (f.panel)', c => !/\.panel\(/.test(c)],
  [3, 'no pictograms in the instruction card', c => /\.panel\(\[[\s\S]*?\bicon\s*:/.test(c)],
  [14, 'text never blinks (no blink in the instruction card)', c => /\.panel\(\[[\s\S]*?\bblink\s*:/.test(c)],
  [15, 'floors with nothing special are grey: pass focus: Halo.focusLevels(state) to floorStack', c => /floorStack\(/.test(c) && !/focus\s*:\s*Halo\.focusLevels\(/.test(c)],
  [8, 'no motion of its own (keyframes, animate, timers)', c => /@keyframes|\banimation\s*:|<animate|requestAnimationFrame|setInterval|h-breathe|h-flicker|h-blink/.test(c)],
  [5, 'no glow, blur or shadow', c => /blur|bloom|glow|drop-shadow|box-shadow|text-shadow|feGaussian/i.test(c)],
  [6, 'no gradients or patterns (flat fills; fire/smoke gradients come from the kit)', c => /gradient|<pattern|feTurbulence|halftone/i.test(c)],
  [11, 'no style of its own', c => /<style|\sstyle\s*=|\.style\./.test(c)],
  [10, 'loads nothing but the kit', c => [...c.matchAll(/(?:src|href)\s*=\s*"([^"]+)"/g)].some(m => !m[1].startsWith('{{HALO_KIT_URL}}'))],
];

function stripComments(src) {
  return src.replace(/<!--[\s\S]*?-->/g, '').replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '').replace(/([^:"'])\/\/.*$/gm, '$1');
}

let failed = 0;
for (const file of process.argv.slice(2)) {
  const code = stripComments(readFileSync(file, 'utf8'));
  const errors = RULES.filter(([, , bad]) => bad(code)).map(([n, msg]) => `rule ${n}: ${msg}`);
  // rule 2/3: short words only — string literals with a sentence in them
  const strings = [...code.matchAll(/'([^'\n]*)'|"([^"\n]*)"/g)].map(m => (m[1] ?? m[2]).trim())
    .filter(t => t.length >= 2 && !/^[\w.:/{}#-]+$/.test(t) && !/[=<>]/.test(t));
  strings.filter(t => t.length > 18 || t.split(/\s+/).length > 4).forEach(t => errors.push(`rule 2: too long for the wrist: « ${t} »`));
  if (errors.length) { failed++; console.log(`✗ ${file}\n  ${errors.join('\n  ')}`); }
  else console.log(`✓ ${file}`);
}
process.exit(failed ? 1 : 0);
