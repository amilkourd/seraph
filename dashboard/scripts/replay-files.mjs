// The replay (MOCK=1) as static files under public/, so a deployed dashboard plays it with no service and no repo
// around it (the public Vercel link).
//   node scripts/replay-files.mjs             before every build: the fixtures mock mode loads, from contracts/fixtures
//                                             (single source of truth) to public/fixtures/ (not committed)
//   node scripts/replay-files.mjs --snapshot  by hand: the Halo kit (halo/kit) and the Rosetta shots the fixtures show
//                                             (rosetta/shots), to public/halo-kit/ and public/shots/ (committed: those
//                                             folders are not deployed with the dashboard)
import { cpSync, existsSync, mkdirSync, readFileSync, readdirSync, rmSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const app = path.resolve(here, "..");
const repo = path.resolve(app, "..");
const fixtures = path.join(repo, "contracts/fixtures");
const pub = path.join(app, "public");

// exactly what lib/live.ts loadFixtures() fetches, nothing more is published
const files = ["state-sample.json", "radio.jsonl", "calls.jsonl", ...readdirSync(path.join(fixtures, "endpoints")).map((f) => `endpoints/${f}`)];
rmSync(path.join(pub, "fixtures"), { recursive: true, force: true });
for (const f of files) {
  mkdirSync(path.dirname(path.join(pub, "fixtures", f)), { recursive: true });
  cpSync(path.join(fixtures, f), path.join(pub, "fixtures", f));
}
console.log(`replay: ${files.length} fixtures → public/fixtures`);

if (process.argv.includes("--snapshot")) {
  // the kit's example views, with {{HALO_KIT_URL}} filled in as app/api/kit does
  const kit = path.join(repo, "halo/kit");
  const out = path.join(pub, "halo-kit");
  rmSync(out, { recursive: true, force: true });
  mkdirSync(path.join(out, "examples"), { recursive: true });
  for (const f of ["halo-kit.js", "halo.css"]) cpSync(path.join(kit, f), path.join(out, f));
  for (const f of readdirSync(path.join(kit, "examples")).filter((x) => x.endsWith(".html")))
    writeFileSync(path.join(out, "examples", f), readFileSync(path.join(kit, "examples", f), "utf8").replaceAll("{{HALO_KIT_URL}}", "/halo-kit"));
  console.log("replay: halo/kit → public/halo-kit");

  // the first shot of each endpoint fixture: the one the Rosetta screens show
  const shots = path.join(pub, "shots");
  rmSync(shots, { recursive: true, force: true });
  mkdirSync(shots, { recursive: true });
  for (const f of files.filter((x) => x.startsWith("endpoints/"))) {
    const url = JSON.parse(readFileSync(path.join(fixtures, f), "utf8")).screenshots?.[0]?.url;
    const name = url && path.basename(new URL(url).pathname);
    const src = name && path.join(repo, "rosetta/shots", name);
    if (src && existsSync(src)) cpSync(src, path.join(shots, name));
    else console.log(`replay: no shot for ${f} (${name ?? "none"}), its screen shows « Pas d'image »`);
  }
  console.log(`replay: ${readdirSync(shots).length} shots → public/shots`);
}
