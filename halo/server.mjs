#!/usr/bin/env node
// Halo kit server, :3001 on every interface (the phone reaches it over the LAN).
//   /kit/*           the kit, CORS open (Devin's views load it from here)
//   /views/<name>/   a kit example served as a view, {{HALO_KIT_URL}} replaced like Silex does: stand-in views
//                    until Silex serves Devin's (approach, inside_route, occupants, team_engaged)
// No dependencies:  node halo/server.mjs   (PORT env to change the port)
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { extname, join, normalize, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = dirname(fileURLToPath(import.meta.url));
const KIT = join(ROOT, 'kit');
const PORT = Number(process.env.PORT || 3001);
const TYPES = { '.js': 'text/javascript', '.mjs': 'text/javascript', '.css': 'text/css', '.html': 'text/html', '.md': 'text/markdown', '.svg': 'image/svg+xml', '.json': 'application/json' };

function send(res, code, body, type) {
  res.writeHead(code, { 'Content-Type': (type || 'text/plain') + '; charset=utf-8', 'Access-Control-Allow-Origin': '*', 'Cache-Control': 'no-store' });
  res.end(body);
}

createServer(async (req, res) => {
  const url = new URL(req.url, 'http://x');
  const path = decodeURIComponent(url.pathname);
  try {
    if (path.startsWith('/kit/')) {
      const file = normalize(join(KIT, path.slice(5)));
      if (!file.startsWith(KIT)) return send(res, 403, 'no');
      return send(res, 200, await readFile(file), TYPES[extname(file)]);
    }
    const view = path.match(/^\/views\/([a-z_]+)\/?$/);
    if (view) {
      const html = await readFile(join(KIT, 'examples', view[1] + '.html'), 'utf8');
      return send(res, 200, html.replaceAll('{{HALO_KIT_URL}}', `http://${req.headers.host}/kit`), 'text/html');
    }
    if (path === '/health') return send(res, 200, '{"ok":true}', 'application/json');
    send(res, 404, 'not found');
  } catch {
    send(res, 404, 'not found');
  }
}).listen(PORT, '0.0.0.0', () => console.log(`halo kit server on :${PORT}`));
