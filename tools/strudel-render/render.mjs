// render_strudel: Strudel code -> WAV, offline (OfflineAudioContext via @strudel/web renderPatternAudio)
// usage: node render.mjs <code.js> <out.wav> [--cycles N] [--begin C] [--samples-dir DIR] [--browser PATH]
// Starts at cycle <begin> (default 0) on an OfflineAudioContext: no scheduler latency, sample-exact.
// http://localhost:5432/* (samples('http://localhost:5432/strudel.json')) is served from --samples-dir.
// Needs a local Edge or Chrome (playwright-core drives it headless, no browser download).
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright-core';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const args = process.argv.slice(2);
const opts = {}, pos = [];
for (let i = 0; i < args.length; i++) {
  if (args[i].startsWith('--')) opts[args[i]] = args[++i];
  else pos.push(args[i]);
}
const opt = (k, d) => (k in opts ? opts[k] : d);
const [codeFile, outWav] = pos;
if (!codeFile || !outWav) {
  console.error('usage: node render.mjs <code.js> <out.wav> [--cycles 8] [--begin 0] [--samples-dir DIR] [--browser PATH]');
  process.exit(2);
}
const cycles = parseFloat(opt('--cycles', '8'));
const begin = parseFloat(opt('--begin', '0'));
const samplesDir = opt('--samples-dir', null);
const code = fs.readFileSync(codeFile, 'utf8');

// drum machine banks (.bank("RolandTR909")) as on strudel.cc
const prebake = /\.bank\(/.test(code)
  ? ['https://raw.githubusercontent.com/felixroos/dough-samples/main/tidal-drum-machines.json']
  : [];

function findBrowser() {
  const c = [opt('--browser', null), process.env.STRUDEL_BROWSER,
    'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
    'C:/Program Files/Microsoft/Edge/Application/msedge.exe',
    'C:/Program Files/Google/Chrome/Application/chrome.exe',
    path.join(process.env.LOCALAPPDATA || '', 'Google/Chrome/Application/chrome.exe')];
  for (const p of c) if (p && fs.existsSync(p)) return p;
  throw new Error('no Edge/Chrome found, pass --browser <path to msedge.exe|chrome.exe>');
}

const MIME = { '.html': 'text/html', '.mjs': 'text/javascript', '.js': 'text/javascript', '.json': 'application/json', '.wav': 'audio/wav' };
const distDir = path.join(HERE, 'node_modules/@strudel/web/dist');
const server = http.createServer((req, res) => {
  const u = decodeURIComponent(new URL(req.url, 'http://x').pathname);
  let f = null;
  if (u === '/' || u === '/page.html') f = path.join(HERE, 'page.html');
  else if (u.startsWith('/strudel/')) f = path.join(distDir, u.slice('/strudel/'.length));
  if (!f || !path.resolve(f).startsWith(path.resolve(HERE)) || !fs.existsSync(f)) { res.writeHead(404); return res.end(); }
  res.writeHead(200, { 'content-type': MIME[path.extname(f)] || 'application/octet-stream' });
  fs.createReadStream(f).pipe(res);
});
await new Promise((r) => server.listen(0, '127.0.0.1', r));
const port = server.address().port;

const browser = await chromium.launch({ executablePath: findBrowser(), headless: true,
  args: ['--autoplay-policy=no-user-gesture-required'] });
try {
  const ctx = await browser.newContext({ acceptDownloads: true });
  const page = await ctx.newPage();
  page.on('console', (m) => { const t = m.text(); if (/error|could not|not found|warn/i.test(t)) console.log('[page]', t); });
  page.on('pageerror', (e) => console.log('[pageerror]', e.message));
  if (samplesDir) {
    // http://localhost:5432/<path> -> <samples-dir>/<path> (no need for serve_samples.py while rendering)
    await page.route(/^http:\/\/localhost:5432\//, (route) => {
      const rel = decodeURIComponent(new URL(route.request().url()).pathname).replace(/^\//, '') || 'strudel.json';
      const f = path.resolve(samplesDir, rel);
      if (!f.startsWith(path.resolve(samplesDir)) || !fs.existsSync(f) || fs.statSync(f).isDirectory())
        return route.fulfill({ status: 404, body: '' });
      route.fulfill({ status: 200, path: f, headers: { 'access-control-allow-origin': '*',
        'content-type': MIME[path.extname(f)] || 'application/octet-stream' } });
    });
  }
  await page.goto(`http://127.0.0.1:${port}/page.html`);
  await page.waitForFunction(() => window.ready === true, null, { timeout: 60000 });
  const t0 = Date.now();
  const [dl, info] = await Promise.all([
    page.waitForEvent('download', { timeout: 600000 }),
    page.evaluate(([c, n, b, pb]) => window.renderCode(c, n, b, pb, 'render'), [code, cycles, begin, prebake]),
  ]);
  fs.mkdirSync(path.dirname(path.resolve(outWav)), { recursive: true });
  await dl.saveAs(outWav);
  console.log(JSON.stringify({ out: outWav, ...info, cycles, begin, seconds: cycles / info.cps, render_ms: Date.now() - t0 }));
} finally {
  await browser.close();
  server.close();
}
