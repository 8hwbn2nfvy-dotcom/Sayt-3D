// Собирает страницу настоящей AMR24: web/index.html + web/three.js.
// - three.js берётся готовым (ужатым) из Лего-проекта: claude/lego-f1/web/three.js.
// - GLTFLoader (+ BufferGeometryUtils, SkeletonUtils) из репозитория three.js превращается в обычный скрипт (window.GLTFLoaderLib)
//   и вставляется в страницу: с file:// модули не грузятся.
// - Модель tools/amr24_web.glb (делает ../../tools/export_web_glb.py + glb_webp.py) и картинка коробки встраиваются в base64.
// Запуск: node tools/build_page.mjs [папка three.js/examples/jsm]
import { readFileSync, writeFileSync, copyFileSync, statSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const web = join(here, '..');
const jsm = process.argv[2] || '/home/user/three.js/examples/jsm';
const lego = join(here, '..', '..', '..', 'lego-f1', 'web');

copyFileSync(join(lego, 'three.js'), join(web, 'three.js'));

// ES-модуль → функция, возвращающая его экспорт. deps: { './путь.js': 'имяПеременной' }
function wrap(file, varName, deps) {
	let src = readFileSync(join(jsm, file), 'utf8');
	src = src.replace(/^import\s*\{([\s\S]*?)\}\s*from\s*'three';/m, (_, n) => `const {${n}} = THREE;`);
	for (const [path, v] of Object.entries(deps)) {
		const re = new RegExp(`^import\\s*\\{([\\s\\S]*?)\\}\\s*from\\s*'${path.replace(/[.*+?^${}()|[\]\\/]/g, '\\$&')}';`, 'm');
		if (!re.test(src)) throw new Error(`${file}: нет импорта ${path}`);
		src = src.replace(re, (_, n) => `const {${n}} = ${v};`);
	}
	if (/^import\s/m.test(src)) throw new Error(`${file}: остались необработанные import`);
	src = src.replace(/^export\s*\{([\s\S]*?)\};?\s*$/m, (_, n) => `return {${n}};`);
	return `const ${varName} = (function () {\n${src}\n})();\n`;
}
const loader = '(function () {\n' +
	wrap('utils/BufferGeometryUtils.js', '__BGU', {}) +
	wrap('utils/SkeletonUtils.js', '__SKU', {}) +
	wrap('loaders/GLTFLoader.js', '__GLTF', { '../utils/BufferGeometryUtils.js': '__BGU', '../utils/SkeletonUtils.js': '__SKU' }) +
	'window.GLTFLoaderLib = __GLTF;\n})();';

const src = readFileSync(join(here, 'index.src.html'), 'utf8');
for (const k of ['__GLTF_LOADER__', '__MODEL_GLB__', '__BOX_TEXTURE__']) if (!src.includes(k)) throw new Error('нет метки ' + k);
const box = 'data:image/jpeg;base64,' + readFileSync(join(lego, 'tools', 'box_front.jpg')).toString('base64');
const glb = readFileSync(join(here, 'amr24_web.glb')).toString('base64');
const out = join(web, 'index.html');
writeFileSync(out, src.replace('__GLTF_LOADER__', () => loader).replace('__MODEL_GLB__', () => glb).replace('__BOX_TEXTURE__', () => box));
const a = statSync(out).size, b = statSync(join(web, 'three.js')).size;
console.log(`index.html ${(a / 2 ** 20).toFixed(2)} МБ + three.js ${(b / 2 ** 20).toFixed(2)} МБ = ${((a + b) / 2 ** 20).toFixed(2)} МБ`);
