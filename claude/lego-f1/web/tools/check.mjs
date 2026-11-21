// Проверка страницы: открывает index.html как при двойном клике (file://),
// ловит ошибки консоли, проверяет тап и перемотку, снимает кадры на ключевых секундах.
// Запуск: node tools/check.mjs [папка для снимков]
import { createRequire } from 'node:module';
const { chromium } = createRequire(import.meta.url)('playwright'); // Playwright уже установлен в системе
import { mkdirSync } from 'node:fs';
import { join, dirname, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const web = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const outDir = resolve(process.argv[2] || join(web, '..', 'check'));
mkdirSync(outDir, { recursive: true });
const url = pathToFileURL(join(web, 'index.html')).href;

const browser = await chromium.launch({ args: ['--enable-unsafe-swiftshader', '--use-angle=swiftshader', '--ignore-gpu-blocklist'] });
const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
const problems = [];
page.on('console', (m) => { if (m.type() === 'error' || m.type() === 'warning') problems.push(`[${m.type()}] ${m.text()}`); });
page.on('pageerror', (e) => problems.push('[pageerror] ' + e.message));

await page.goto(url);
await page.waitForFunction(() => window.__lego && window.__texReady, null, { timeout: 60000 });
const blocks = await page.evaluate(() => window.__lego.blocks);
console.log('кубиков в машинке:', blocks);

// 1) Тап по машинке до 7-й секунды запускает разбор
await page.evaluate(() => { window.__lego.setTime(3); window.__lego.pause(); });
await page.waitForTimeout(300);
await page.mouse.click(640, 400);
await page.waitForTimeout(300);
const tap = await page.evaluate(() => ({ tapAt: window.__lego.state.tapAt, start: window.__lego.explodeStart() }));
console.log('тап на 3-й секунде → разбор начинается с', tap.start, tap.tapAt !== null ? '(OK)' : '(НЕ СРАБОТАЛ)');
await page.waitForTimeout(100);
await page.evaluate(() => { window.__lego.setTime(3.9); window.__lego.pause(); });
await page.waitForTimeout(400);
await page.screenshot({ path: join(outDir, 'tap_3.0_then_3.9.png') });

// 2) Пробел перезапускает ролик
await page.keyboard.press('Space');
await page.waitForTimeout(200);
const afterSpace = await page.evaluate(() => ({ t: window.__lego.getTime(), tap: window.__lego.state.tapAt }));
console.log('после пробела: t =', afterSpace.t.toFixed(2), 'тап сброшен:', afterSpace.tap === null);

// 3) Клавиша → перематывает вперёд
await page.evaluate(() => { window.__lego.setTime(5); window.__lego.pause(); });
await page.keyboard.press('ArrowRight');
const afterArrow = await page.evaluate(() => window.__lego.getTime());
console.log('5.0 + стрелка вправо =', afterArrow.toFixed(2));

// 4) Ползунок
await page.evaluate(() => { const s = document.getElementById('scrub'); s.value = '9.5'; s.dispatchEvent(new Event('input')); window.__lego.pause(); });
console.log('ползунок на 9.5 → t =', (await page.evaluate(() => window.__lego.getTime())).toFixed(2));

// 5) Снимки на ключевых секундах (без тапа)
await page.keyboard.press('Space');
for (const t of (process.env.TIMES || '0,4,7.5,9.5,11.5,13,15').split(',').map(Number)) {
  await page.evaluate((x) => { window.__lego.setTime(x); window.__lego.pause(); }, t);
  await page.waitForTimeout(350);
  await page.screenshot({ path: join(outDir, `t_${String(t).padStart(4, '0')}.png`) });
}
console.log(problems.length ? 'Сообщения консоли:\n' + problems.join('\n') : 'Ошибок в консоли нет');
console.log('снимки:', outDir);
await browser.close();
