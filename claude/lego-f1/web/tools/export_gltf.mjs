// Выгружает сцену страницы в glTF (scene.glb) для рендера в Blender Cycles.
// В файле: все кубики машинки с наклейками, трасса, коробка, камера и движение всего этого
// по тому же таймлайну (450 кадров, 30 к/с, без тапа). Прозрачность коробки по кадрам — в box_alpha.json.
// Запуск: node tools/export_gltf.mjs <папка для результата> [путь к three.js/examples/jsm/exporters/GLTFExporter.js]
import { createRequire } from 'node:module';
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { join, dirname, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
const { chromium } = createRequire(import.meta.url)('playwright');

const web = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const outDir = resolve(process.argv[2] || join(web, '..', 'blender_build'));
const exporterPath = process.argv[3] || '/home/user/three.js/examples/jsm/exporters/GLTFExporter.js';
mkdirSync(outDir, { recursive: true });

// GLTFExporter — ES-модуль; превращаем его в обычный скрипт, берущий всё из window.THREE.
let ex = readFileSync(exporterPath, 'utf8');
ex = ex.replace(/^import\s*\{([\s\S]*?)\}\s*from\s*'three';/m, (_, names) => `const {${names}} = THREE;`);
ex = ex.replace(/^export\s*\{\s*GLTFExporter\s*\};?/m, 'window.GLTFExporter = GLTFExporter;');

const browser = await chromium.launch({ args: ['--enable-unsafe-swiftshader', '--use-angle=swiftshader'] });
const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
const errors = [];
page.on('pageerror', (e) => errors.push(e.message));
await page.goto(pathToFileURL(join(web, 'index.html')).href + '?video=1');
await page.waitForFunction(() => window.__lego && window.__lego.ready(), null, { timeout: 60000 });
await page.addScriptTag({ content: ex });

const result = await page.evaluate(async () => {
  const L = window.__lego, T = window.THREE;
  const { scene, camera } = L;
  L.setSize(1920, 1080);
  camera.name = 'camera';
  scene.add(camera);
  // свет ставим в Blender, из файла его убираем
  const lights = [];
  scene.traverse((o) => { if (o.isLight) lights.push(o); });
  lights.forEach((l) => { l.parent.remove(l); if (l.target && l.target.parent) l.target.parent.remove(l.target); });

  // бордюры из «инстансов» → две обычные сетки (красная и белая), так Blender их точно прочтёт
  const kerbs = scene.getObjectByName('kerbs');
  const buckets = {};
  const m4 = new T.Matrix4(), col = new T.Color();
  for (let i = 0; i < kerbs.count; i++) {
    kerbs.getMatrixAt(i, m4); kerbs.getColorAt(i, col);
    const key = col.getHex();
    const g = kerbs.geometry.clone().applyMatrix4(m4).toNonIndexed();
    (buckets[key] = buckets[key] || []).push(g);
  }
  Object.entries(buckets).forEach(([hex, list]) => {
    let n = 0; list.forEach((g) => { n += g.attributes.position.count; });
    const pos = new Float32Array(n * 3), nor = new Float32Array(n * 3);
    let o = 0;
    list.forEach((g) => { pos.set(g.attributes.position.array, o * 3); nor.set(g.attributes.normal.array, o * 3); o += g.attributes.position.count; });
    const geo = new T.BufferGeometry();
    geo.setAttribute('position', new T.BufferAttribute(pos, 3));
    geo.setAttribute('normal', new T.BufferAttribute(nor, 3));
    const mesh = new T.Mesh(geo, new T.MeshStandardMaterial({ color: Number(hex), roughness: 0.6 }));
    mesh.name = 'kerbs_' + Number(hex).toString(16);
    scene.add(mesh);
  });
  scene.remove(kerbs);

  // что двигается: машинка со всеми частями, коробка, камера
  const car = scene.getObjectByName('car'), box = scene.getObjectByName('box');
  const nodes = [];
  [car, box].forEach((root) => root.traverse((o) => nodes.push(o)));
  nodes.push(camera);
  const FPS = 30, N = 450;
  const rec = nodes.map(() => ({ p: [], q: [], s: [] }));
  const alpha = [], explode = [], wheel = [], carPose = [];
  const times = [];
  for (let f = 0; f < N; f++) {
    const t = f / FPS;
    times.push(t);
    const ps = L.pose(t);
    alpha.push(ps.boxOpacity); explode.push(ps.explode); wheel.push(ps.wheel); carPose.push(ps.car);
    nodes.forEach((o, i) => {
      rec[i].p.push(o.position.x, o.position.y, o.position.z);
      rec[i].q.push(o.quaternion.x, o.quaternion.y, o.quaternion.z, o.quaternion.w);
      rec[i].s.push(o.scale.x, o.scale.y, o.scale.z);
    });
  }
  const changes = (a, w) => { for (let i = w; i < a.length; i++) if (Math.abs(a[i] - a[i % w]) > 1e-6) return true; return false; };
  const tracks = [];
  nodes.forEach((o, i) => {
    if (changes(rec[i].p, 3)) tracks.push(new T.VectorKeyframeTrack(o.name + '.position', times, rec[i].p));
    if (changes(rec[i].q, 4)) tracks.push(new T.QuaternionKeyframeTrack(o.name + '.quaternion', times, rec[i].q));
    if (changes(rec[i].s, 3)) tracks.push(new T.VectorKeyframeTrack(o.name + '.scale', times, rec[i].s));
  });
  const clip = new T.AnimationClip('timeline', (N - 1) / FPS, tracks);
  L.pose(0);
  box.visible = true; // в Blender коробка прячется прозрачностью

  const glb = await new Promise((ok, fail) => new window.GLTFExporter().parse(scene, ok, fail, { binary: true, animations: [clip], onlyVisible: true, maxTextureSize: 4096 }));
  const bytes = new Uint8Array(glb);
  let bin = '';
  for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
  return {
    glb: btoa(bin), alpha, explode, wheel, carPose, tracks: tracks.length, nodes: nodes.length,
    camera: { fov: camera.fov, aspect: camera.aspect, near: camera.near, far: camera.far },
    keyOffset: L.KEY_OFFSET.toArray(),
  };
});
await browser.close();
if (errors.length) { console.error('Ошибки страницы:\n' + errors.join('\n')); process.exit(1); }
writeFileSync(join(outDir, 'scene.glb'), Buffer.from(result.glb, 'base64'));
// explode/wheel/carPose — для замены Лего-машинки другой моделью (claude/real-f1/tools/real_car.py); carPose = [x, y, z, поворот] в координатах страницы
writeFileSync(join(outDir, 'timeline.json'), JSON.stringify({ fps: 30, frames: result.alpha.length, boxAlpha: result.alpha, explode: result.explode, wheel: result.wheel, carPose: result.carPose, camera: result.camera, keyOffset: result.keyOffset }));
console.log(`scene.glb ${(result.glb.length * 0.75 / 1024 / 1024).toFixed(1)} МБ, узлов с движением: ${result.nodes}, дорожек анимации: ${result.tracks}`);
