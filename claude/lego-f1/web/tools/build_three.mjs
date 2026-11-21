// Склеивает ES-модули three.js (three.core.js + three.module.js) в один обычный
// скрипт web/three.js, который кладёт всё в window.THREE.
// Зачем: страница открывается двойным кликом (file://), а Chrome не грузит
// <script type="module"> с file://. Обычный <script src> работает.
// Запуск: node tools/build_three.mjs <папка build из репозитория three.js>
import { readFileSync, writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const src = process.argv[2] || '/home/user/three.js/build';
const out = join(dirname(fileURLToPath(import.meta.url)), '..', 'three.js');

const names = (stmt) => stmt.replace(/^[^{]*\{/, '').replace(/\}.*$/s, '').split(',').map((s) => s.trim()).filter(Boolean);

function split(code) {
	const lines = code.split('\n');
	const body = [];
	const stmts = [];
	for (const l of lines) {
		if (/^(import|export) \{/.test(l)) stmts.push(l); else body.push(l);
	}
	return { body: body.join('\n'), stmts };
}

const core = split(readFileSync(join(src, 'three.core.js'), 'utf8'));
const mod = split(readFileSync(join(src, 'three.module.js'), 'utf8'));

const coreExports = names(core.stmts.find((s) => s.startsWith('export {')));
const modImports = names(mod.stmts.find((s) => s.startsWith('import {')));
const modReexports = names(mod.stmts.find((s) => s.startsWith('export {') && s.includes("from './three.core.js'")));
const modOwn = names(mod.stmts.find((s) => s.startsWith('export {') && !s.includes(' from ')));

for (const n of [...modImports, ...modReexports]) if (!coreExports.includes(n)) throw new Error('нет в core: ' + n);
const licence = core.body.match(/^\/\*\*[\s\S]*?\*\//)[0];

const result = `${licence}
// Собрано tools/build_three.mjs из three.core.js + three.module.js (r${(/REVISION = ['"](\d+)/.exec(core.body) || [0, '?'])[1]}).
(function () {
'use strict';
var __core = (function () {
${core.body}
return { ${coreExports.join(', ')} };
})();
var __mod = (function (__core) {
var { ${modImports.join(', ')} } = __core;
${mod.body}
return { ${modOwn.join(', ')} };
})(__core);
var THREE = {};
${JSON.stringify(modReexports)}.forEach(function (k) { THREE[k] = __core[k]; });
Object.keys(__mod).forEach(function (k) { THREE[k] = __mod[k]; });
window.THREE = Object.freeze(THREE);
})();
`;
// Ужимаем: TypeScript (если установлен) убирает комментарии разбором кода, затем снимаем отступы и пустые строки.
// Переводы строк остаются, поэтому смысл кода не меняется.
let final = result;
try {
	const ts = createRequire(import.meta.url)('typescript');
	const body = ts.transpileModule(result, { compilerOptions: { removeComments: true, target: ts.ScriptTarget.ESNext, module: ts.ModuleKind.None } }).outputText;
	final = licence + '\n' + body.split('\n').map((l) => l.replace(/^\s+/, '')).filter((l) => l.length).join('\n') + '\n';
} catch (e) { console.warn('typescript не найден — three.js без ужатия:', e.message); }
writeFileSync(out, final);
console.log('three.js:', (final.length / 1024 / 1024).toFixed(2), 'MB,', modReexports.length + modOwn.length, 'имён');
