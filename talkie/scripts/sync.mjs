// Copies the shared inputs the talkie needs from outside its folder, so the app also builds on its own
// (Vercel, a tunnel box) where ../contracts is absent. The copy is committed.
//   ../contracts/fixtures/radio.jsonl  → lib/radio/fixtures/radio.json
import { copyFileSync, existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const app = resolve(here, "..");
const root = resolve(app, "..");

function sync(label, from, to, transform) {
  if (!existsSync(from)) {
    console.log(`[sync] ${label}: source missing, keeping committed copy`);
    return;
  }
  mkdirSync(dirname(to), { recursive: true });
  if (transform) writeFileSync(to, transform(readFileSync(from, "utf8")));
  else copyFileSync(from, to);
  console.log(`[sync] ${label}: ok`);
}

sync(
  "radio fixture",
  resolve(root, "contracts/fixtures/radio.jsonl"),
  resolve(app, "lib/radio/fixtures/radio.json"),
  (text) =>
    JSON.stringify(
      text
        .split("\n")
        .map((l) => l.trim())
        .filter(Boolean)
        .map((l) => JSON.parse(l)),
      null,
      2,
    ) + "\n",
);
