// Собирает макеты: shablon/index.html + data/<имя>.json -> mockups/<mockup_dir>/index.html.
// Данные встраиваются в один тег <script id="company-data">, остальное — шаблон без изменений.
//   node shablon/build.mjs            собрать все макеты
//   node shablon/build.mjs kuranty    собрать один (другие папки не трогаются)
//   node shablon/build.mjs --check    проверить, что макеты = шаблон + данные и в шаблоне нет данных компаний
import { readFileSync, writeFileSync, mkdirSync, readdirSync, existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const TEMPLATE = join(ROOT, "shablon", "index.html");
const DATA_DIR = join(ROOT, "data");
const SLOT = '<script type="application/json" id="company-data">null</script>';
const REQUIRED = ["mockup_dir", "name", "kind", "city", "phone", "messengers", "locations", "services", "calculator", "reviews", "about", "price_checked", "price_source", "theme"];

function fail(msg) { console.error("ОШИБКА: " + msg); process.exit(1); }

function load(name) {
  const file = join(DATA_DIR, name + ".json");
  let d;
  try { d = JSON.parse(readFileSync(file, "utf8")); } catch (e) { fail(`${file}: ${e.message}`); }
  for (const k of REQUIRED) if (!(k in d)) fail(`${file}: нет поля "${k}"`);
  if (!/^[a-z0-9]{12}$/.test(d.mockup_dir)) fail(`${file}: mockup_dir должен быть 12 символов a-z0-9`);
  d.calculator.forEach((c, i) => {
    if (typeof c.base !== "number") fail(`${file}: calculator[${i}].base не число`);
    if (!["site", "example"].includes(c.base_source)) fail(`${file}: calculator[${i}].base_source должен быть site или example`);
    if (c.base_source === "site" && !d.services.some(s => s.price_from === c.base)) fail(`${file}: calculator[${i}] помечен как цена с сайта, но такой цены нет в services`);
  });
  return d;
}

function render(template, d) {
  const json = JSON.stringify(d, null, 1).replace(/</g, "\\u003c");
  return template.replace(SLOT, `<script type="application/json" id="company-data">${json}</script>`);
}

function placeholders(d) {
  const out = [];
  (function walk(v, path) {
    if (v === null) { if (!/(locations\[\d+\]\.phone|\.date|\.source_url|\.rating)$/.test(path)) out.push(`${path}: пусто (null)`); return; }
    if (typeof v === "string") { for (const m of v.match(/\[[^\]]+\]/g) || []) out.push(`${path}: ${m}`); return; }
    if (Array.isArray(v)) { v.forEach((x, i) => walk(x, `${path}[${i}]`)); return; }
    if (typeof v === "object") for (const [k, x] of Object.entries(v)) walk(x, path ? `${path}.${k}` : k);
  })(d, "");
  d.calculator.filter(c => c.base_source === "example").forEach(c => out.push(`calculator «${c.name}»: базовая цена ${c.base} ₽ — пример`));
  return out;
}

const template = readFileSync(TEMPLATE, "utf8");
if (template.split(SLOT).length !== 2) fail("в шаблоне должен быть ровно один пустой тег company-data");
const names = readdirSync(DATA_DIR).filter(f => f.endsWith(".json")).map(f => f.slice(0, -5)).sort();
const args = process.argv.slice(2);

if (args.includes("--check")) {
  let bad = 0;
  const dirs = new Set();
  for (const n of names) {
    const d = load(n);
    if (dirs.has(d.mockup_dir)) { console.error(`✗ ${n}: mockup_dir повторяется`); bad++; }
    dirs.add(d.mockup_dir);
    const out = join(ROOT, "mockups", d.mockup_dir, "index.html");
    if (!existsSync(out)) { console.error(`✗ ${n}: нет ${out}`); bad++; continue; }
    const html = readFileSync(out, "utf8");
    const stripped = html.replace(/<script type="application\/json" id="company-data">[\s\S]*?<\/script>/, SLOT);
    if (stripped !== template) { console.error(`✗ ${n}: макет отличается от шаблона не только данными`); bad++; }
    else if (html !== render(template, d)) { console.error(`✗ ${n}: данные в макете устарели — пересоберите`); bad++; }
    else console.log(`✓ ${n}: шаблон тот же, отличаются только данные`);
    // В коде шаблона не должно быть данных компании.
    const probes = [d.name, d.short_name, d.city, d.phone && d.phone.display, d.phone && d.phone.tel, d.email,
      ...d.locations.map(l => l.address.split(",")[1]), ...d.services.filter(s => s.price_from).map(s => String(s.price_from)),
      ...d.reviews.map(r => r.text).filter(x => x && !x.startsWith("["))].filter(Boolean).map(s => s.trim());
    for (const p of probes) if (p.length > 2 && template.includes(p)) { console.error(`✗ ${n}: в шаблоне найдено «${p}»`); bad++; }
  }
  process.exit(bad ? 1 : 0);
}

const pick = args.length ? args : names;
for (const n of pick) {
  if (!names.includes(n)) fail(`нет data/${n}.json`);
  const d = load(n);
  const dir = join(ROOT, "mockups", d.mockup_dir);
  mkdirSync(dir, { recursive: true });
  writeFileSync(join(dir, "index.html"), render(template, d));
  console.log(`${n} -> mockups/${d.mockup_dir}/index.html`);
  for (const p of placeholders(d)) console.log("   заглушка  " + p);
}
