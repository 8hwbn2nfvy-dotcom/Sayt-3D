// Автопроверка макетов и скриншоты всех страниц при 390 и 1280 px.
// Запуск: node shablon/qa.cjs <папка для скриншотов>  (нужен playwright с Chromium)
const { chromium } = require('playwright');
const path = require('path'); const fs = require('fs');
const ROOT = path.join(__dirname, '..'); const OUT = process.argv[2] || path.join(ROOT, 'proverka', 'latest');
fs.mkdirSync(OUT, { recursive: true });
const sample = path.join(OUT, 'maket-vizitki.pdf'); fs.writeFileSync(sample, '%PDF-1.4 test');
const names = fs.readdirSync(path.join(ROOT, 'data')).filter(f => f.endsWith('.json')).map(f => f.slice(0, -5)).sort();

(async () => {
  const b = await chromium.launch();
  const report = [];
  for (const name of names) {
    const d = JSON.parse(fs.readFileSync(path.join(ROOT, 'data', name + '.json'), 'utf8'));
    const url = 'file://' + path.join(ROOT, 'mockups', d.mockup_dir, 'index.html');
    const routes = [['01-glavnaya', ''], ['02-uslugi', 'uslugi'], ['03-usluga', 'uslugi/' + d.services[0].slug], ['04-ceny', 'ceny'],
      ['05-raboty', 'raboty'], ['06-otzyvy', 'otzyvy'], ['07-o-kompanii', 'o-kompanii'], ['08-kontakty', 'kontakty']];
    for (const w of [390, 1280]) {
      const ctx = await b.newContext({ viewport: { width: w, height: w === 390 ? 844 : 900 }, reducedMotion: 'reduce', deviceScaleFactor: 1, hasTouch: w === 390, isMobile: w === 390 });
      const page = await ctx.newPage();
      const ext = [], errs = [], r = { tag: `${name}-${w}`, pages: {} };
      page.on('request', q => { if (!q.url().startsWith('file:') && !q.url().startsWith('data:')) ext.push(q.url()); });
      page.on('pageerror', e => errs.push(e.message)); page.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });
      page.on('dialog', x => x.dismiss());
      const check = () => page.evaluate(() => {
        const W = document.documentElement.clientWidth, bad = [], small = [];
        document.querySelectorAll('body *').forEach(el => { const q = el.getBoundingClientRect(); if (q.width && (q.right > W + 1 || q.left < -1) && getComputedStyle(el).position !== 'fixed' && !el.closest('.tabs,.drawer') && !el.classList.contains('sr')) bad.push(el.tagName + '.' + el.className); });
        document.querySelectorAll('a.btn,button,.cbtn,.tab,select,input:not([type=checkbox]):not([type=radio]):not(.sr),.choice label,.check,.navbar a,.others a').forEach(el => {
          const q = el.getBoundingClientRect(); if (q.width && q.height && q.height < 47.5 && !el.closest('.drawer')) small.push((el.textContent || el.id || el.tagName).trim().slice(0, 25) + ' ' + Math.round(q.height));
        });
        return { scroll: document.documentElement.scrollWidth > W, bad: bad.slice(0, 4), small: small.slice(0, 6), h1: (document.querySelector('#page h1') || {}).textContent };
      });
      await page.goto(url);
      for (const [file, route] of routes) {
        await page.evaluate(h => { location.hash = h; }, '#/' + route); await page.waitForTimeout(80);
        r.pages[file] = await check();
        await page.screenshot({ path: `${OUT}/${name}-${w}-${file}.png`, fullPage: true });
      }
      // «← Назад» со страницы услуги ведёт в каталог
      await page.evaluate(() => { location.hash = '#/uslugi'; }); await page.waitForTimeout(50);
      await page.click('.tile, .cat h3 a >> nth=0'); await page.waitForTimeout(50);
      await page.click('#page [data-back]'); await page.waitForTimeout(80);
      r.backTo = await page.evaluate(() => location.hash);
      // Мобильное меню
      if (w === 390) {
        await page.click('#burger'); r.menuOpen = await page.isVisible('#drawer .box');
        await page.screenshot({ path: `${OUT}/${name}-${w}-09-menu.png` });
        await page.click('#drawer a.item[data-nav="kontakty"]'); await page.waitForTimeout(80);
        r.menuNav = await page.evaluate(() => location.hash); r.menuClosed = !(await page.isVisible('#drawer .box'));
      }
      // Фильтр работ
      await page.evaluate(() => { location.hash = '#/raboty'; }); await page.waitForTimeout(50);
      const fb = await page.$$('#filters button');
      if (fb.length > 1) { await fb[1].click(); r.filtered = await page.$$eval('#works .ph-img', x => x.length); }
      // Калькулятор на странице цен: крайние значения
      await page.evaluate(() => { location.hash = '#/ceny'; }); await page.waitForTimeout(50);
      const res = async () => (await page.textContent('#calc-result')).replace(/\s+/g, ' ').trim().slice(0, 70);
      const calc = [];
      const tabs = await page.$$('.tab');
      for (let i = 0; i < Math.max(1, tabs.length); i++) {
        if (tabs[i]) await tabs[i].click();
        const sels = await page.$$('#calc-params select');
        for (const s of sels) { const n = await s.evaluate(e => e.options.length); await s.selectOption({ index: n - 1 }); }
        calc.push(`tab${i} max: ${await res()}`);
        const num = await page.$('#calc-params input[type=number]');
        if (num) {
          const mn = await num.getAttribute('min'), mx = await num.getAttribute('max');
          for (const v of ['', mn, mx, String(+mx + 1), '0']) { await num.fill(v); calc.push(`  «${v}»: ${await res()}`); }
          await page.click('#calc-params button[data-step="-1"]'); calc.push(`  «−» от 0 → ${await num.inputValue()}`);
          await num.fill(mx); await page.click('#calc-params button[data-step="1"]'); calc.push(`  «+» на max → ${await num.inputValue()}`);
          await num.fill(mn);
        }
        for (const s of sels) await s.selectOption({ index: 0 });
        calc.push(`tab${i} min: ${await res()}`);
      }
      r.calc = calc;
      // Заявка из калькулятора на главной
      await page.evaluate(() => { location.hash = '#/'; }); await page.waitForTimeout(50);
      await page.click('#calc-order'); await page.waitForTimeout(50);
      r.prefill = await page.inputValue('#o-details');
      await page.fill('#o-details', '');
      await page.click('[data-next="2"]'); r.err1 = await page.textContent('#err-1');
      await page.setInputFiles('#o-file', sample);
      r.step1 = await check();
      await page.screenshot({ path: `${OUT}/${name}-${w}-10-zayavka-shag1.png`, fullPage: true });
      await page.click('[data-next="2"]');
      await page.click('[data-next="3"]'); r.err2 = await page.textContent('#err-2');
      await page.fill('#o-name', 'Тест'); await page.fill('#o-phone', '123');
      await page.click('[data-next="3"]'); r.err2b = await page.textContent('#err-2');
      await page.fill('#o-phone', '+7 900 000-00-00');
      await page.screenshot({ path: `${OUT}/${name}-${w}-11-zayavka-shag2.png`, fullPage: true });
      await page.click('#order-back'); r.keptFile = await page.textContent('#o-files'); await page.click('[data-next="2"]');
      r.keptName = await page.inputValue('#o-name');
      await page.click('[data-next="3"]');
      r.step3 = await check();
      await page.screenshot({ path: `${OUT}/${name}-${w}-12-zayavka-shag3.png`, fullPage: true });
      await page.click('button[type=submit]');
      r.done = await page.textContent('.ostep.on h2');
      await page.screenshot({ path: `${OUT}/${name}-${w}-13-gotovo.png`, fullPage: true });
      await page.click('#order-home'); await page.waitForTimeout(80); r.home = await page.evaluate(() => location.hash) + ' calc=' + await page.isVisible('#calc');
      r.external = ext; r.errors = errs;
      report.push(r); await ctx.close();
    }
  }
  const p = await b.newPage(); await p.goto('file://' + ROOT + '/shablon/index.html');
  report.push({ template: (await p.textContent('body')).trim().slice(0, 60) });
  await b.close();
  console.log(JSON.stringify(report, null, 1));
})();
