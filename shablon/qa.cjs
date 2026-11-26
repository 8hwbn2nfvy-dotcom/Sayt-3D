const { chromium } = require('playwright');
const path = require('path'); const fs = require('fs');
// Запуск: node shablon/qa.cjs <папка для скриншотов>  (нужен playwright с Chromium)
const ROOT = path.join(__dirname, '..'); const OUT = process.argv[2] || path.join(ROOT, 'proverka', 'latest');
const sites = { kuranty: '09wcyhn9xhjw', link: 'w4t9rdbykf0k', kukuruznik: '0p2tva59m8a6' };
fs.mkdirSync(OUT, { recursive: true });
const sample = path.join(OUT, 'maket-vizitki.pdf'); fs.writeFileSync(sample, '%PDF-1.4 test');
(async () => {
  const b = await chromium.launch();
  const report = [];
  for (const [name, dir] of Object.entries(sites)) for (const w of [390, 1280]) {
    const ctx = await b.newContext({ viewport: { width: w, height: w === 390 ? 844 : 900 }, reducedMotion: 'reduce', deviceScaleFactor: 1, hasTouch: w === 390, isMobile: w === 390 });
    const page = await ctx.newPage();
    const ext = []; const errs = [];
    page.on('request', r => { if (!r.url().startsWith('file:') && !r.url().startsWith('data:')) ext.push(r.url()); });
    page.on('pageerror', e => errs.push(e.message)); page.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });
    page.on('dialog', d => d.dismiss());
    await page.goto('file://' + path.join(ROOT, 'mockups', dir, 'index.html'));
    const tag = `${name}-${w}`; const r = { tag };
    const overflow = async () => page.evaluate(() => {
      const W = document.documentElement.clientWidth; const bad = [];
      document.querySelectorAll('body *').forEach(el => { const b = el.getBoundingClientRect(); if (b.width && (b.right > W + 1 || b.left < -1) && getComputedStyle(el).position !== 'fixed' && !el.closest('.tabs') && !el.classList.contains('sr')) bad.push(el.tagName + '.' + el.className + ' ' + Math.round(b.right)); });
      return { scroll: document.documentElement.scrollWidth > W, bad: bad.slice(0, 5) };
    });
    const small = async () => page.evaluate(() => {
      const out = [];
      document.querySelectorAll('a.btn,button,.cbtn,.tab,select,input:not([type=checkbox]):not([type=radio]):not(.sr),.choice label,.check').forEach(el => {
        const b = el.getBoundingClientRect(); if (b.width && b.height && b.height < 47.5) out.push((el.textContent || el.id || el.tagName).trim().slice(0, 30) + ' ' + Math.round(b.height));
      }); return out;
    });
    r.overflowMain = await overflow(); r.smallMain = await small();
    await page.screenshot({ path: `${OUT}/${tag}-1-glavnaya.png`, fullPage: true });
    const calc = [];
    const res = async () => (await page.textContent('#calc-result')).replace(/\s+/g, ' ').slice(0, 90);
    const tabs = await page.$$('.tab');
    for (let i = 0; i < tabs.length; i++) {
      await tabs[i].click();
      const sels = await page.$$('#calc-params select');
      for (const s of sels) { const n = await s.evaluate(e => e.options.length); await s.selectOption({ index: n - 1 }); }
      const num = await page.$('#calc-params input[type=number]');
      calc.push(`tab${i} max-options: ${await res()}`);
      if (num) {
        const mn = await num.getAttribute('min'), mx = await num.getAttribute('max');
        await num.fill(''); calc.push(`  пусто: ${await res()}`);
        await num.fill(mn); calc.push(`  min ${mn}: ${await res()}`);
        await num.fill(mx); calc.push(`  max ${mx}: ${await res()}`);
        await num.fill(String(+mx + 1)); calc.push(`  >max: ${await res()}`);
        await num.fill('0'); calc.push(`  0: ${await res()}`);
        await page.click('#calc-params button[data-step="-1"]'); calc.push(`  «−» от 0: val=${await num.inputValue()}`);
        await num.fill(mx); await page.click('#calc-params button[data-step="1"]'); calc.push(`  «+» на max: val=${await num.inputValue()}`);
      }
      for (const s of sels) await s.selectOption({ index: 0 });
      if (num) await num.fill(await num.getAttribute('min'));
      calc.push(`tab${i} min: ${await res()}`);
    }
    r.calc = calc;
    await page.click('.tab >> nth=0'); await page.click('#calc-order');
    r.prefill = await page.inputValue('#o-details');
    await page.fill('#o-details', '');
    await page.click('[data-next="2"]'); r.err1 = await page.textContent('#err-1');
    await page.setInputFiles('#o-file', sample);
    r.small1 = await small(); r.overflow1 = await overflow();
    await page.screenshot({ path: `${OUT}/${tag}-2-zayavka-shag1.png`, fullPage: true });
    await page.click('[data-next="2"]');
    await page.click('[data-next="3"]'); r.err2 = await page.textContent('#err-2');
    await page.fill('#o-name', 'Тест'); await page.fill('#o-phone', '123');
    await page.click('[data-next="3"]'); r.err2b = await page.textContent('#err-2');
    await page.fill('#o-phone', '+7 900 000-00-00');
    r.small2 = await small();
    await page.screenshot({ path: `${OUT}/${tag}-3-zayavka-shag2.png`, fullPage: true });
    await page.click('#order-back'); r.keptFile = await page.textContent('#o-files'); await page.click('[data-next="2"]');
    r.keptName = await page.inputValue('#o-name');
    await page.click('[data-next="3"]');
    r.summary = (await page.textContent('#o-summary')).replace(/\s+/g, ' ');
    r.overflow3 = await overflow();
    await page.screenshot({ path: `${OUT}/${tag}-4-zayavka-shag3.png`, fullPage: true });
    await page.click('button[type=submit]');
    r.done = await page.textContent('.ostep.on h2');
    await page.screenshot({ path: `${OUT}/${tag}-5-gotovo.png`, fullPage: true });
    await page.click('#order-home'); r.backHome = await page.isVisible('#calc');
    r.external = ext; r.errors = errs;
    report.push(r); await ctx.close();
  }
  const p = await b.newPage(); await p.goto('file://' + ROOT + '/shablon/index.html');
  report.push({ template: (await p.textContent('body')).trim().slice(0, 80) });
  await b.close();
  console.log(JSON.stringify(report, null, 1));
})();
