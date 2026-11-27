// Меню на телефоне, появление блоков при прокрутке, копирование телефона и проверка формы записи.
(function () {
  "use strict";
  document.documentElement.classList.add("js");
  var reduced = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // Меню: кнопка, Esc.
  var btn = document.querySelector(".menu-btn");
  var nav = document.getElementById("nav");
  if (btn && nav) {
    var setOpen = function (open) {
      nav.classList.toggle("open", open);
      btn.setAttribute("aria-expanded", open ? "true" : "false");
      btn.textContent = open ? "Закрыть" : "Меню";
    };
    btn.addEventListener("click", function () { setOpen(!nav.classList.contains("open")); });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && nav.classList.contains("open")) { setOpen(false); btn.focus(); }
    });
  }

  // Появление блоков при прокрутке.
  var blocks = document.querySelectorAll(".reveal");
  if (!reduced && "IntersectionObserver" in window) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (en.isIntersecting) { en.target.classList.add("in"); io.unobserve(en.target); }
      });
    }, { rootMargin: "0px 0px -40px 0px" });
    blocks.forEach(function (b) { io.observe(b); });
  } else {
    blocks.forEach(function (b) { b.classList.add("in"); });
  }

  // Копирование телефона: кнопка появляется только при номере в разметке.
  document.querySelectorAll("[data-copy]").forEach(function (b) {
    b.hidden = false;
    b.addEventListener("click", function () {
      var text = b.getAttribute("data-copy");
      var ok = function () { b.textContent = "Номер скопирован"; };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(ok, function () { b.textContent = text; });
      } else {
        b.textContent = text;
      }
    });
  });

  // Форма записи: черновик хранится в sessionStorage этой вкладки, в адрес ничего не попадает.
  var form = document.getElementById("zapis-form");
  if (!form) return;
  form.noValidate = true;
  var KEY = "zapis:" + location.pathname.replace(/[^/]*$/, "");
  var ids = ["f-need", "f-date", "f-name", "f-phone"];
  var fields = ids.map(function (id) { return document.getElementById(id); });
  var store = null;
  try { store = window.sessionStorage; } catch (err) { store = null; /* хранилище недоступно: черновик не сохраняется */ }

  var today = new Date();
  var pad = function (n) { return (n < 10 ? "0" : "") + n; };
  var todayStr = today.getFullYear() + "-" + pad(today.getMonth() + 1) + "-" + pad(today.getDate());
  document.getElementById("f-date").min = todayStr;

  if (store) {
    var saved = null;
    try { saved = JSON.parse(store.getItem(KEY) || "null"); } catch (err) { saved = null; /* повреждённый черновик: начинаем с пустой формы */ }
    if (saved) fields.forEach(function (f) { if (typeof saved[f.id] === "string") f.value = saved[f.id]; });
  }
  var save = function () {
    if (!store) return;
    var data = {};
    fields.forEach(function (f) { data[f.id] = f.value; });
    try { store.setItem(KEY, JSON.stringify(data)); } catch (err) { /* хранилище переполнено или запрещено: черновик не сохраняется */ }
  };
  form.addEventListener("input", save);

  var checks = {
    "f-need": function (v) { return v.trim().length > 0; },
    "f-date": function (v) { return /^\d{4}-\d{2}-\d{2}$/.test(v) && v >= todayStr; },
    "f-name": function (v) { return v.trim().length > 0; },
    "f-phone": function (v) { return v.replace(/\D/g, "").length >= 10; }
  };
  var show = function (f, ok) {
    var err = document.getElementById("e-" + f.id.slice(2));
    f.closest(".field").classList.toggle("bad", !ok);
    f.setAttribute("aria-invalid", ok ? "false" : "true");
    if (err) err.hidden = ok;
  };
  fields.forEach(function (f) {
    f.addEventListener("blur", function () { if (f.value) show(f, checks[f.id](f.value)); });
  });
  form.addEventListener("submit", function (e) {
    e.preventDefault();
    var first = null;
    fields.forEach(function (f) {
      var ok = checks[f.id](f.value);
      show(f, ok);
      if (!ok && !first) first = f;
    });
    if (first) { first.focus(); return; }
    save();
    location.assign("prinyato.html");
  });
})();
