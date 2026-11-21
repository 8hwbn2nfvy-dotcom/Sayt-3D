// Собирает web/index.html из tools/index.src.html: вставляет картинку коробки (tools/box_front.jpg) прямо в страницу.
// Зачем: с file:// браузер не даёт WebGL читать соседние картинки, а встроенная картинка работает.
// Запуск: node tools/build_page.mjs
import { readFileSync, writeFileSync, statSync, readdirSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
const here = dirname(fileURLToPath(import.meta.url));
const src = readFileSync(join(here, 'index.src.html'), 'utf8');
const img = readFileSync(join(here, 'box_front.jpg')).toString('base64');
if (!src.includes('__BOX_TEXTURE__')) throw new Error('нет метки __BOX_TEXTURE__');
const out = join(here, '..', 'index.html');
// Наклейки машинки (tools/decals/*.jpg, делает tools/make_decals.py)
const decalDir = join(here, 'decals');
const decals = {};
for (const f of readdirSync(decalDir).filter((f) => f.endsWith('.jpg')).sort()) decals[f.replace(/\.jpg$/, '')] = 'data:image/jpeg;base64,' + readFileSync(join(decalDir, f)).toString('base64');
if (!src.includes('__DECALS__')) throw new Error('нет метки __DECALS__');
writeFileSync(out, src.replace('__BOX_TEXTURE__', 'data:image/jpeg;base64,' + img).replace('__DECALS__', JSON.stringify(decals)));
const a = statSync(out).size, b = statSync(join(here, '..', 'three.js')).size;
console.log(`index.html ${(a / 1024).toFixed(0)} КБ + three.js ${(b / 1024).toFixed(0)} КБ = ${((a + b) / 1024 / 1024).toFixed(2)} МБ (лимит 3 МБ)`);
if (a + b > 3 * 1024 * 1024) { console.error('Больше 3 МБ!'); process.exit(1); }
