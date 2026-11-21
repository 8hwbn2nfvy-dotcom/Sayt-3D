// Рендер video.mp4 тем же кодом сцены (index.html?video=1), по тому же таймлайну, без тапа.
// Кадры идут в ffmpeg в PNG (без потерь). Кадр N = секунда N/30. 450 кадров = 15 с, 1920×1080, 30 кадров/с, H.264.
// Запуск: node tools/render_video.mjs [кадров=450]
// Нужны: Playwright (Chromium) и ffmpeg.
import { createRequire } from 'node:module';
import { spawn } from 'node:child_process';
import { join, dirname, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
const { chromium } = createRequire(import.meta.url)('playwright');

const FPS = 30, W = 1920, H = 1080, DURATION = 15;
const frames = parseInt(process.argv[2] || String(FPS * DURATION), 10);
const web = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const out = join(web, 'video.mp4');

const browser = await chromium.launch({ args: ['--enable-unsafe-swiftshader', '--use-angle=swiftshader', '--ignore-gpu-blocklist'] });
const page = await browser.newPage({ viewport: { width: W, height: H } });
const errors = [];
page.on('pageerror', (e) => errors.push(e.message));
page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
await page.goto(pathToFileURL(join(web, 'index.html')).href + '?video=1');
await page.waitForFunction(() => window.__lego && window.__lego.ready(), null, { timeout: 60000 });
await page.evaluate(([w, h]) => window.__lego.setSize(w, h), [W, H]);

const ff = spawn('ffmpeg', ['-y', '-loglevel', 'error', '-f', 'image2pipe', '-framerate', String(FPS), '-c:v', 'png', '-i', '-',
  '-c:v', 'libx264', '-preset', 'slow', '-crf', '14', '-pix_fmt', 'yuv420p', '-r', String(FPS), '-movflags', '+faststart', out], { stdio: ['pipe', 'inherit', 'inherit'] });
const done = new Promise((ok, fail) => ff.on('close', (c) => (c === 0 ? ok() : fail(new Error('ffmpeg код ' + c)))));

const t0 = Date.now();
for (let i = 0; i < frames; i++) {
  const url = await page.evaluate((t) => window.__lego.frame(t), i / FPS);
  const buf = Buffer.from(url.slice(url.indexOf(',') + 1), 'base64');
  if (!ff.stdin.write(buf)) await new Promise((r) => ff.stdin.once('drain', r));
  if (i % 30 === 0) console.log(`кадр ${i}/${frames} (${((Date.now() - t0) / 1000).toFixed(0)} с)`);
}
ff.stdin.end();
await done;
await browser.close();
if (errors.length) { console.error('Ошибки страницы:\n' + errors.join('\n')); process.exit(1); }
console.log('готово:', out);
