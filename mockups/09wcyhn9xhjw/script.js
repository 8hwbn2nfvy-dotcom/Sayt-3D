// Меню, появление блоков, копирование телефона, расчёт по прайсу и шаги заявки.
(function () {
  "use strict";
  var root = document.documentElement;
  root.classList.add("js");
  var reduced = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // Мобильное меню: крестик, Esc, ссылка, затемнение.
  var btn = document.querySelector(".menu-btn");
  var drawer = document.getElementById("drawer");
  if (btn && drawer) {
    var open = function () { drawer.hidden = false; btn.setAttribute("aria-expanded", "true"); var c = drawer.querySelector(".close"); if (c) c.focus(); };
    var close = function () { drawer.hidden = true; btn.setAttribute("aria-expanded", "false"); btn.focus(); };
    btn.addEventListener("click", open);
    drawer.addEventListener("click", function (e) { if (e.target.closest(".close") || e.target.closest(".shade") || e.target.closest("a")) close(); });
    document.addEventListener("keydown", function (e) { if (e.key === "Escape" && !drawer.hidden) close(); });
  }

  // Появление блоков при прокрутке.
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

  // Расчёт по прайсу: только цены из таблиц на странице.
  var calc = document.getElementById("raschet-form");
  if (calc) {
    var data = JSON.parse(document.getElementById("price-data").textContent);
    var prod = calc.querySelector("#c-prod"), fmt = calc.querySelector("#c-format"), paper = calc.querySelector("#c-paper"), run = calc.querySelector("#c-run");
    var out = calc.querySelector("#c-result"), cond = calc.querySelector("#c-cond"), fmtRow = calc.querySelector("#c-format-row"), paperRow = calc.querySelector("#c-paper-row");
    var rub = function (n) { return n.toLocaleString("ru-RU") + " ₽"; };
    var fill = function (sel, list) { var v = sel.value; sel.innerHTML = list.map(function (x) { return "<option>" + x + "</option>"; }).join(""); if (list.indexOf(v) >= 0) sel.value = v; };
    var update = function () {
      var isViz = prod.value === "Визитки";
      fmtRow.hidden = isViz; paperRow.hidden = isViz;
      var runs, price, text;
      if (isViz) {
        runs = Object.keys(data.vizitki.rows);
        fill(run, runs.map(function (r) { return r + " шт."; }));
        price = data.vizitki.rows[parseInt(run.value, 10)];
        text = data.vizitki.title + ", " + run.value;
      } else {
        fill(paper, Object.keys(data.listovki.papers));
        var formats = Object.keys(data.listovki.papers[paper.value]);
        fill(fmt, formats);
        fill(run, data.listovki.runs.map(function (r) { return r + " шт."; }));
        var idx = data.listovki.runs.indexOf(parseInt(run.value, 10));
        price = data.listovki.papers[paper.value][fmt.value][idx];
        text = "Листовки " + fmt.value + ", бумага " + paper.value.toLowerCase() + ", " + run.value;
      }
      out.textContent = rub(price);
      cond.textContent = text;
      var order = document.getElementById("c-order");
      if (order) order.href = "zakaz.html?usluga=" + encodeURIComponent(isViz ? "Визитки" : "Листовки") + "&tirazh=" + encodeURIComponent(text);
    };
    [prod, fmt, paper, run].forEach(function (s) { s.addEventListener("change", update); });
    calc.hidden = false;
    update();
  }

  // Заявка в три шага.
  var form = document.getElementById("order-form");
  if (form) {
    form.noValidate = true;
    var steps = form.querySelectorAll(".step"), bar = document.getElementById("steps-bar"), cur = 0;
    var params = new URLSearchParams(location.search);
    if (params.get("usluga")) { var s = form.querySelector("#o-usluga"); s.value = params.get("usluga"); }
    if (params.get("tirazh")) form.querySelector("#o-tirazh").value = params.get("tirazh");
    form.querySelectorAll("[data-js]").forEach(function (el) { el.hidden = false; });
    form.querySelectorAll("[data-nojs]").forEach(function (el) { el.hidden = true; });
    bar.hidden = false;
    var show = function (i, quiet) {
      cur = i;
      steps.forEach(function (st, k) { st.classList.toggle("on", k === i); });
      bar.querySelectorAll("li").forEach(function (li, k) { li.classList.toggle("on", k === i); li.classList.toggle("done", k < i); });
      if (!quiet) bar.scrollIntoView({ behavior: reduced ? "auto" : "smooth", block: "start" });
    };
    var err = function (i, msg) { var e = steps[i].querySelector(".err"); e.textContent = msg; return !msg; };
    var check = function (i) {
      if (i === 0) {
        if (!form.querySelector("#o-tirazh").value.trim()) return err(0, "Укажите тираж.");
        if (!form.querySelector("#o-file").files.length && !form.querySelector("#o-design").checked) return err(0, "Прикрепите файл или отметьте «Нужен дизайн».");
      }
      if (i === 1) {
        if (!form.querySelector("#o-name").value.trim()) return err(1, "Укажите имя.");
        if (form.querySelector("#o-phone").value.replace(/\D/g, "").length < 10) return err(1, "Укажите телефон: не меньше 10 цифр.");
      }
      return err(i, "");
    };
    var summary = function () {
      var f = Array.prototype.map.call(form.querySelector("#o-file").files, function (x) { return x.name; }).join(", ");
      var ch = form.querySelector("input[name=svyaz]:checked");
      var rows = [["Услуга", form.querySelector("#o-usluga").value], ["Тираж", form.querySelector("#o-tirazh").value],
        ["Файл", f || (form.querySelector("#o-design").checked ? "нужен дизайн" : "—")], ["Имя", form.querySelector("#o-name").value],
        ["Телефон", form.querySelector("#o-phone").value], ["Как связаться", ch ? ch.value : "—"], ["Где забрать", form.querySelector("#o-pickup").value]];
      var dl = form.querySelector("#o-summary"); dl.innerHTML = "";
      rows.forEach(function (r) { var d = document.createElement("div"), dt = document.createElement("dt"), dd = document.createElement("dd"); dt.textContent = r[0]; dd.textContent = r[1]; d.appendChild(dt); d.appendChild(dd); dl.appendChild(d); });
    };
    form.addEventListener("click", function (e) {
      var n = e.target.closest("[data-next]"), b = e.target.closest("[data-back]");
      if (n) { if (check(cur)) { if (cur === 1) summary(); show(cur + 1); } }
      if (b) show(cur - 1);
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
