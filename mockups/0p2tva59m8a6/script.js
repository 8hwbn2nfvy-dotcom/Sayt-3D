// Меню, появление блоков, копирование телефона, расчёт по прайсу и шаги заявки.
// Ничего не отправляет в сеть. Выбор услуги передаётся на страницу заявки через sessionStorage, не через адрес.
(function () {
  "use strict";
  var root = document.documentElement;
  root.classList.add("js");
  var reduced = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var store = {
    set: function (k, v) { try { sessionStorage.setItem(k, v); } catch (e) { /* хранилище недоступно: заявка откроется без подстановки */ } },
    take: function (k) { try { var v = sessionStorage.getItem(k); sessionStorage.removeItem(k); return v; } catch (e) { return null; } }
  };

  // Мобильное меню: крестик, Esc, ссылка, затемнение.
  var btn = document.querySelector(".menu-btn");
  var drawer = document.getElementById("drawer");
  if (btn && drawer) {
    var open = function () { drawer.hidden = false; btn.setAttribute("aria-expanded", "true"); document.body.classList.add("locked"); var c = drawer.querySelector(".close"); if (c) c.focus(); };
    var close = function () { drawer.hidden = true; btn.setAttribute("aria-expanded", "false"); document.body.classList.remove("locked"); btn.focus(); };
    btn.addEventListener("click", open);
    drawer.addEventListener("click", function (e) { if (e.target.closest(".close") || e.target.closest(".shade") || e.target.closest("a")) close(); });
    document.addEventListener("keydown", function (e) { if (e.key === "Escape" && !drawer.hidden) close(); });
    window.matchMedia("(min-width:1024px)").addEventListener("change", function (m) { if (m.matches && !drawer.hidden) close(); });
  }

  // Появление блоков при прокрутке: 0,5 с, сдвиг 20 px (в style.css).
  var blocks = document.querySelectorAll(".reveal");
  if (!reduced && "IntersectionObserver" in window) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) { if (en.isIntersecting) { en.target.classList.add("in"); io.unobserve(en.target); } });
    }, { rootMargin: "0px 0px -40px 0px" });
    blocks.forEach(function (b) { io.observe(b); });
  } else {
    blocks.forEach(function (b) { b.classList.add("in"); });
  }

  // Копирование телефона.
  document.querySelectorAll("[data-copy]").forEach(function (b) {
    b.hidden = false;
    b.addEventListener("click", function () {
      var text = b.getAttribute("data-copy");
      var ok = function () { b.textContent = "Номер скопирован"; };
      if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(text).then(ok, function () { b.textContent = text; });
      else b.textContent = text;
    });
  });

  // Ссылки «Заказать» с выбранной услугой.
  document.addEventListener("click", function (e) {
    var a = e.target.closest("a[data-usluga]");
    if (!a) return;
    store.set("zayavka-usluga", a.getAttribute("data-usluga"));
    if (a.hasAttribute("data-tirazh")) store.set("zayavka-tirazh", a.getAttribute("data-tirazh"));
  });

  // Расчёт по прайсу (только «Куранты»): цены из таблиц сайта, без коэффициентов.
  var calc = document.getElementById("raschet-form");
  if (calc) {
    var data = JSON.parse(document.getElementById("price-data").textContent);
    var prod = calc.querySelector("#c-prod"), fmt = calc.querySelector("#c-format"), paper = calc.querySelector("#c-paper"), run = calc.querySelector("#c-run");
    var out = calc.querySelector("#c-result"), cond = calc.querySelector("#c-cond"), fmtRow = calc.querySelector("#c-format-row"), paperRow = calc.querySelector("#c-paper-row");
    var rub = function (n) { return n.toLocaleString("ru-RU") + " ₽"; };
    var fill = function (sel, list) { var v = sel.value; sel.innerHTML = list.map(function (x) { return "<option>" + x + "</option>"; }).join(""); if (list.indexOf(v) >= 0) sel.value = v; };
    var update = function () {
      var isViz = prod.value === "Визитки";
      fmtRow.hidden = isViz; paperRow.hidden = isViz;
      var price, text;
      if (isViz) {
        fill(run, Object.keys(data.vizitki.rows).map(function (r) { return r + " шт."; }));
        price = data.vizitki.rows[parseInt(run.value, 10)];
        text = data.vizitki.title + ", " + run.value;
      } else {
        fill(paper, Object.keys(data.listovki.papers));
        fill(fmt, Object.keys(data.listovki.papers[paper.value]));
        fill(run, data.listovki.runs.map(function (r) { return r + " шт."; }));
        var idx = data.listovki.runs.indexOf(parseInt(run.value, 10));
        price = data.listovki.papers[paper.value][fmt.value][idx];
        text = "Листовки " + fmt.value + ", бумага " + paper.value.toLowerCase() + ", " + run.value;
      }
      out.textContent = rub(price);
      cond.textContent = text;
      var order = document.getElementById("c-order");
      if (order) { order.setAttribute("data-usluga", isViz ? "Визитки" : "Листовки"); order.setAttribute("data-tirazh", text); }
    };
    [prod, fmt, paper, run].forEach(function (s) { s.addEventListener("change", update); });
    calc.hidden = false;
    update();
  }

  // Заявка в три шага: что печатаем → контакты → проверка. Никуда не отправляется.
  var form = document.getElementById("order-form");
  if (form) {
    form.noValidate = true;
    var steps = form.querySelectorAll(".step"), bar = document.getElementById("steps-bar"), cur = 0;
    var q = function (s) { return form.querySelector(s); };
    var pre = store.take("zayavka-usluga"), preT = store.take("zayavka-tirazh");
    if (pre) { var sel = q("#o-usluga"); for (var i = 0; i < sel.options.length; i++) if (sel.options[i].text === pre) sel.selectedIndex = i; }
    if (preT) q("#o-tirazh").value = preT;
    form.querySelectorAll("[data-js]").forEach(function (el) { el.hidden = false; });
    bar.hidden = false;
    var show = function (n, quiet) {
      cur = n;
      steps.forEach(function (st, k) { st.classList.toggle("on", k === n); });
      bar.querySelectorAll("li").forEach(function (li, k) { li.classList.toggle("on", k === n); li.classList.toggle("done", k < n); if (k === n) li.setAttribute("aria-current", "step"); else li.removeAttribute("aria-current"); });
      if (!quiet) { bar.scrollIntoView({ behavior: reduced ? "auto" : "smooth", block: "start" }); var h = steps[n].querySelector("h2"); if (h) { h.tabIndex = -1; h.focus({ preventScroll: true }); } }
    };
    var err = function (n, msg) { steps[n].querySelector(".err").textContent = msg; return !msg; };
    var check = function (n) {
      if (n === 0) {
        if (!q("#o-tirazh").value.trim()) return err(0, "Укажите тираж и параметры.");
        if (!q("#o-file").files.length && !q("#o-design").checked) return err(0, "Прикрепите файл или отметьте «Нужен дизайн».");
      }
      if (n === 1) {
        if (!q("#o-name").value.trim()) return err(1, "Укажите имя.");
        if (q("#o-phone").value.replace(/\D/g, "").length < 10) return err(1, "Укажите телефон: не меньше 10 цифр.");
      }
      return err(n, "");
    };
    var summary = function () {
      var f = Array.prototype.map.call(q("#o-file").files, function (x) { return x.name; }).join(", ");
      var ch = form.querySelector("input[name=svyaz]:checked"), pick = q("#o-pickup");
      var rows = [["Услуга", q("#o-usluga").value], ["Тираж и параметры", q("#o-tirazh").value],
        ["Файл", f ? f + (q("#o-design").checked ? "; нужен дизайн" : "") : (q("#o-design").checked ? "нужен дизайн" : "—")],
        ["Имя", q("#o-name").value], ["Телефон", q("#o-phone").value], ["Как связаться", ch ? ch.value : "—"]];
      if (pick) rows.push(["Где забрать", pick.options[pick.selectedIndex].text]);
      var dl = q("#o-summary"); dl.textContent = "";
      rows.forEach(function (r) { var d = document.createElement("div"), dt = document.createElement("dt"), dd = document.createElement("dd"); dt.textContent = r[0]; dd.textContent = r[1]; d.appendChild(dt); d.appendChild(dd); dl.appendChild(d); });
    };
    form.addEventListener("click", function (e) {
      if (e.target.closest("[data-next]") && check(cur)) { if (cur === 1) summary(); show(cur + 1); }
      if (e.target.closest("[data-back]")) show(cur - 1);
    });
    form.addEventListener("input", function () { steps.forEach(function (st) { st.querySelector(".err").textContent = ""; }); });
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      if (!check(0)) return show(0);
      if (!check(1)) return show(1);
      form.hidden = true; bar.hidden = true;
      var done = document.getElementById("spasibo"); done.hidden = false; done.focus();
    });
    show(0, true);
  }
})();
