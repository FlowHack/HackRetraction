/* HackRetraction UI — логика: форма, превью, генерация, настройки. */
"use strict";

var state = {
  params: {},
  settings: {},
  ui: null,
  gcode: ""
};

/* --- Мост с Python --- */
function post(msg) {
  if (typeof orca !== "undefined" && orca.postMessage) {
    orca.postMessage(msg);
  }
}

/* --- Локализация --- */
function text(key) {
  if (state.ui && state.ui.texts && state.ui.texts[key]) {
    return state.ui.texts[key];
  }
  return key;
}

function applyTexts() {
  var nodes = document.querySelectorAll("[data-text]");
  for (var i = 0; i < nodes.length; i++) {
    nodes[i].textContent = text(nodes[i].getAttribute("data-text"));
  }
  document.title = text("window_title");
}

/* --- Тема и шрифт --- */
function applyTheme(settings) {
  var theme = (settings && settings.theme) || "auto";
  document.body.setAttribute("data-theme", theme);
}

function applyFont(settings) {
  var size = (settings && settings.font_size) || 14;
  var style = (settings && settings.font_style) || "system";
  document.body.style.fontSize = size + "px";
  document.body.style.fontFamily =
    style === "mono" ? "var(--font-mono)" : "var(--font)";
}

/* --- Форма параметров --- */
function buildForm(ui, params) {
  var panel = document.getElementById("params-panel");
  var html = "";
  var sections = ui.sections || [];
  for (var s = 0; s < sections.length; s++) {
    var secKey = sections[s][0];
    var keys = sections[s][1];
    html += '<div class="sec" data-sec="' + secKey + '">';
    html += '<div class="sec-head"><span class="chevron">&#9660;</span><span>' +
      text(secKey) + "</span></div>";
    html += '<div class="sec-body">';
    for (var k = 0; k < keys.length; k++) {
      var key = keys[k];
      var label = ui.labels["p." + key] || key;
      var tip = ui.tips["t." + key] || "";
      var unit = ui.units[key] || "";
      var type = ui.types[key] || "number";
      var value = params[key] !== undefined ? params[key] : "";
      html += '<div class="field">';
      html += '<label title="' + esc(label) + '">' + esc(label) + "</label>";
      if (tip) {
        html += '<span class="tip" tabindex="0" data-tip="' + esc(tip) + '">?</span>';
      }
      if (type === "textarea") {
        html += '<textarea data-param="' + key + '">' + esc(value) + "</textarea>";
      } else {
        /* Шаги инкрементальных параметров не могут быть отрицательными. */
        var min = STEP_KEYS.indexOf(key) >= 0 ? ' min="0"' : "";
        html += '<span class="input-wrap">';
        html += '<input type="number" step="any" data-param="' + key +
          '" value="' + esc(value) + '"' + min + ">";
        if (unit) {
          html += '<span class="unit">' + esc(unit) + "</span>";
        }
        html += "</span>";
      }
      html += "</div>";
    }
    html += "</div></div>";
  }
  panel.innerHTML = html;
  bindSections();
  bindLivePreview();
  bindTips();
  applyStepLock(params);
}

function esc(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function collectParams() {
  var params = {};
  var inputs = document.querySelectorAll("[data-param]");
  for (var i = 0; i < inputs.length; i++) {
    var el = inputs[i];
    var key = el.getAttribute("data-param");
    var raw = el.value.trim();
    if (el.tagName === "TEXTAREA" || el.tagName === "textarea") {
      params[key] = el.value;
    } else if (raw !== "") {
      params[key] = Number(raw);
    }
  }
  return params;
}

function setFormValues(params) {
  var inputs = document.querySelectorAll("[data-param]");
  for (var i = 0; i < inputs.length; i++) {
    var el = inputs[i];
    var key = el.getAttribute("data-param");
    if (params[key] !== undefined) {
      el.value = params[key];
    }
  }
}

/* --- Live-обновление превью при изменении параметров --- */
function bindLivePreview() {
  var inputs = document.querySelectorAll("[data-param]");
  for (var i = 0; i < inputs.length; i++) {
    inputs[i].addEventListener("input", function () {
      var params = collectParams();
      applyStepLock(params);
      renderPreview(params);
    });
  }
}

/* --- Тултипы через JS (fixed, не обрезаются панелью) --- */
function bindTips() {
  /* data-tip есть у «вопросиков» и у кнопок тулбара (pull/load). */
  var tips = document.querySelectorAll("[data-tip]");
  for (var i = 0; i < tips.length; i++) {
    tips[i].addEventListener("mouseenter", showTip);
    tips[i].addEventListener("mouseleave", hideTip);
    tips[i].addEventListener("focus", showTip);
    tips[i].addEventListener("blur", hideTip);
  }
}

function showTip(e) {
  var tip = e.currentTarget;
  var box = document.getElementById("tip-box");
  if (!box) return;
  box.textContent = tip.getAttribute("data-tip") || "";
  var r = tip.getBoundingClientRect();
  var left = r.right + 8;
  var top = r.top;
  if (left + 270 > window.innerWidth) {
    left = r.left - 8 - 260;
  }
  if (top + 200 > window.innerHeight) {
    top = window.innerHeight - 200;
  }
  if (top < 4) top = 4;
  box.style.left = left + "px";
  box.style.top = top + "px";
  box.classList.add("visible");
}

function hideTip() {
  var box = document.getElementById("tip-box");
  if (box) box.classList.remove("visible");
}

/* --- Превью --- */
function renderPreview(params) {
  var side = document.getElementById("preview-side");
  var top = document.getElementById("preview-top");
  if (side) side.innerHTML = renderSide(params);
  if (top) top.innerHTML = renderTop(params);
}

function num(v, d) {
  var n = Number(v);
  return isNaN(n) ? d : n;
}

function fmtNum(v) {
  return (Math.round(v * 100) / 100).toString();
}

/* Вид сверху: квадрат с точками дистанции ретракции по периметру. */
function renderTop(p) {
  var srd = num(p.startRetractiondistance, 0);
  var ird = num(p.incrementRetractiondistance, 0);
  var val = function (i) { return fmtNum(srd + ird * i); };

  /* Длинные значения -> класс small (мельче шрифт, чтобы не сливались). */
  var maxLen = 0;
  for (var i = 0; i < 16; i++) {
    var len = val(i).length;
    if (len > maxLen) maxLen = len;
  }
  var labelCls = maxLen > 4 ? "topview-label small" : "topview-label";

  /* Точка на линии рамки + подпись снаружи (pos — сторона квадрата). */
  var dot = function (x, y, v, pos) {
    return '<div class="topview-dot" style="left:' + x + '%;top:' + y + '%"></div>' +
      '<div class="' + labelCls + '" data-pos="' + pos + '" style="left:' + x +
      '%;top:' + y + '%">' + v + "</div>";
  };

  var h = '<div class="topview-square-wrap">';
  h += '<div class="topview-square"></div>';
  /* Низ (0-3): подписи под квадратом */
  for (var i = 0; i < 4; i++) {
    h += dot((i + 0.5) * 25, 100, val(i), "bottom");
  }
  /* Верх (11-8): подписи над квадратом */
  for (var j = 0; j < 4; j++) {
    h += dot((j + 0.5) * 25, 0, val(11 - j), "top");
  }
  /* Лево (12-15): подписи слева */
  for (var k = 0; k < 4; k++) {
    h += dot(0, (k + 0.5) * 25, val(12 + k), "left");
  }
  /* Право (7-4): подписи справа */
  for (var m = 0; m < 4; m++) {
    h += dot(100, (m + 0.5) * 25, val(7 - m), "right");
  }
  h += "</div>";
  /* Надпись «перед» строго под нижней гранью квадрата */
  h += '<div class="topview-front">HACKRETRACTION</div>';
  return h;
}

/* Вид сбоку: монолитная башня из ячеек (column-reverse), подписи справа.
   Точки на стыках ячеек — со стороны инкрементного параметра (справа). */
function renderSide(p) {
  var nt = Math.max(1, Math.round(num(p.NumTests, 1)));
  var lt = Math.max(1, num(p.layersTest, 1));
  var srs = num(p.startRetractionspeed, 0);
  var irs = num(p.incrementRetractionspeed, 0);
  var fs = num(p.speedFan, 0);
  var fsi = num(p.speedFanIncrement, 0);
  var tsh = num(p.tempStarthotend, 0);
  var tih = num(p.tempIncrementhotend, 0);

  /* Показываем только параметры с ненулевым шагом (динамические). */
  var showSpeed = irs !== 0;
  var showFan = fsi !== 0;
  var showTemp = tih !== 0;
  var hasStep = showSpeed || showFan || showTemp;

  /* Высота блока пропорциональна слоям на тест (1.2px на слой). */
  var blockH = Math.max(6, Math.round(lt * 1.2));

  var h = '<div class="tower">';
  for (var i = 0; i < nt; i++) {
    h += '<div class="tower-row" style="height:' + blockH + 'px">';
    h += '<div class="tower-block">';
    /* Точка на стыке ячеек (кроме верхнего блока), справа у параметров. */
    if (hasStep && i < nt - 1) {
      h += '<span class="tower-dot"></span>';
    }
    h += "</div>";
    h += '<div class="tower-labels">';
    if (showSpeed) {
      h += '<span class="lbl lbl-speed">' + fmtNum(srs + irs * i) + " мм/с</span>";
    }
    if (showFan) {
      h += '<span class="lbl lbl-fan">' + fmtNum(fs + fsi * i) + " %</span>";
    }
    if (showTemp) {
      h += '<span class="lbl lbl-temp">' + fmtNum(tsh + tih * i) + " °C</span>";
    }
    h += "</div></div>";
  }
  h += "</div>";
  return h;
}

/* --- Блокировка шагов: только один из трёх инкрементов может быть ненулевым --- */
var STEP_KEYS = ["incrementRetractionspeed", "tempIncrementhotend", "speedFanIncrement"];

function label(key) {
  if (state.ui && state.ui.labels && state.ui.labels[key]) {
    return state.ui.labels[key];
  }
  return key;
}

function tip(key) {
  if (state.ui && state.ui.tips && state.ui.tips[key]) {
    return state.ui.tips[key];
  }
  return key;
}

function applyStepLock(params) {
  var active = null;
  for (var i = 0; i < STEP_KEYS.length; i++) {
    if (num(params[STEP_KEYS[i]], 0) !== 0) {
      active = STEP_KEYS[i];
      break;
    }
  }
  for (var j = 0; j < STEP_KEYS.length; j++) {
    var key = STEP_KEYS[j];
    var input = document.querySelector('[data-param="' + key + '"]');
    if (!input) continue;
    var locked = active !== null && active !== key;
    input.disabled = locked;
    if (locked) {
      /* Сбрасываем заблокированное поле, чтобы не было двух ненулевых шагов. */
      input.value = "0";
      params[key] = 0;
    } else if (num(params[key], 0) < 0) {
      /* Шаг не может быть отрицательным — обнуляем (и в форме, и в превью). */
      input.value = "0";
      params[key] = 0;
    }
    var tipEl = input.parentElement.querySelector(".tip");
    if (tipEl) {
      if (locked) {
        tipEl.setAttribute(
          "data-tip",
          tip("t.locked").replace("{param}", label("p." + active))
        );
        tipEl.classList.add("locked");
      } else {
        tipEl.setAttribute("data-tip", tip("t." + key));
        tipEl.classList.remove("locked");
      }
    }
  }
}

/* --- Тосты (вместо статусбара) --- */
var TOAST_ERROR_KEYS = [
  "status.error", "status.save_failed", "status.load_failed", "status.copy_failed",
  "status.step_multiple", "status.step_none", "status.step_negative", "status.pull_fail"
];

function toastType(key) {
  if (TOAST_ERROR_KEYS.indexOf(key) >= 0) return "error";
  if (key === "status.generated" || key === "status.copied" || key === "status.saved" ||
      key === "status.pull_ok" || key === "status.reset_ok" || key === "status.loaded") {
    return "success";
  }
  return "info";
}

function showToast(key, params) {
  var container = document.getElementById("toast-container");
  if (!container) return;
  var t = text(key);
  if (params) {
    for (var k in params) {
      t = t.replace("{" + k + "}", String(params[k]));
    }
  }
  var toast = document.createElement("div");
  toast.className = "toast " + toastType(key);
  toast.textContent = t;
  container.appendChild(toast);
  /* Удаляем с анимацией через 4 секунды. */
  window.setTimeout(function () {
    toast.classList.add("out");
    window.setTimeout(function () {
      if (toast.parentElement) toast.parentElement.removeChild(toast);
    }, 300);
  }, 4000);
}

/* --- Копирование с fallback --- */
function copyText(value, okKey) {
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(value).then(function () {
      showToast(okKey);
    }, function () {
      legacyCopy(value, okKey);
    });
  } else {
    legacyCopy(value, okKey);
  }
}

function legacyCopy(value, okKey) {
  var ta = document.createElement("textarea");
  ta.value = value;
  ta.style.position = "fixed";
  ta.style.opacity = "0";
  document.body.appendChild(ta);
  ta.select();
  var ok = false;
  try {
    ok = document.execCommand("copy");
  } catch (e) {
    ok = false;
  }
  document.body.removeChild(ta);
  showToast(ok ? okKey : "status.copy_failed");
}

/* --- Обработка сообщений Python --- */
function onMessage(msg) {
  if (!msg) return;
  switch (msg.type) {
    case "state":
      state.ui = msg.ui;
      state.params = msg.params || {};
      state.settings = msg.settings || {};
      applyTexts();
      applyTheme(state.settings);
      applyFont(state.settings);
      buildForm(state.ui, state.params);
      renderPreview(state.params);
      break;
    case "generated":
      state.gcode = msg.gcode || "";
      showToast("status.generated");
      /* Отложенное действие из меню «Сгенерировать GCODE». */
      if (pendingAction === "copy") {
        pendingAction = null;
        copyText(state.gcode, "status.copied");
      } else if (pendingAction === "save") {
        pendingAction = null;
        promptSave();
      }
      break;
    case "pulled":
      state.params = msg.params || {};
      setFormValues(state.params);
      applyStepLock(state.params);
      renderPreview(state.params);
      showToast(msg.status || "status.pull_ok");
      break;
    case "reset":
      state.params = msg.params || {};
      setFormValues(state.params);
      applyStepLock(state.params);
      renderPreview(state.params);
      showToast(msg.status || "status.reset_ok");
      break;
    case "loaded":
      state.params = msg.params || {};
      setFormValues(state.params);
      applyStepLock(state.params);
      renderPreview(state.params);
      showToast("status.loaded");
      break;
    case "settings_saved":
      if (msg.settings) {
        state.settings = msg.settings;
        applyTheme(state.settings);
        applyFont(state.settings);
      }
      if (msg.ok) {
        post({ type: "get_state" });
      }
      break;
    case "status":
      showToast(msg.key, msg.params);
      break;
    case "error":
      showToast("status.error", { error: msg.message });
      break;
  }
}

/* --- Кнопки --- */
var pendingAction = null;

function promptSave() {
  var path = window.prompt(text("status.path_placeholder"), "");
  if (path) {
    post({ type: "save", path: path });
  }
}

function toggleGenerateMenu() {
  var menu = document.getElementById("generate-menu");
  if (!menu) return;
  var hidden = menu.classList.contains("hidden");
  menu.classList.toggle("hidden");
  if (hidden) {
    /* Закрытие по клику вне меню. */
    window.setTimeout(function () {
      document.addEventListener("click", closeGenerateMenu, true);
    }, 0);
  }
}

function closeGenerateMenu(e) {
  var menu = document.getElementById("generate-menu");
  if (!menu || menu.classList.contains("hidden")) return;
  var wrap = document.getElementById("btn-generate");
  if (e && wrap && (e.target === wrap || menu.contains(e.target))) return;
  menu.classList.add("hidden");
  document.removeEventListener("click", closeGenerateMenu, true);
}

function bindToolbar() {
  var map = {
    "btn-help": function () { openHelp(); },
    "btn-pull": function () { post({ type: "pull" }); },
    "btn-generate": function () { toggleGenerateMenu(); },
    "gen-copy": function () {
      pendingAction = "copy";
      post({ type: "generate", params: collectParams() });
    },
    "gen-save": function () {
      pendingAction = "save";
      post({ type: "generate", params: collectParams() });
    },
    "btn-load": function () {
      var input = document.getElementById("file-input");
      input.click();
    },
    "btn-settings": function () { openSettings(); },
    "btn-support": function () { openSupport(); }
  };
  for (var id in map) {
    var el = document.getElementById(id);
    if (el) el.addEventListener("click", map[id]);
  }
}

/* --- Загрузка gcode из файла --- */
function bindFileInput() {
  var input = document.getElementById("file-input");
  input.addEventListener("change", function () {
    var file = input.files && input.files[0];
    if (!file) return;
    var reader = new FileReader();
    reader.onload = function (e) {
      post({ type: "load_gcode", gcode: e.target.result });
    };
    reader.readAsText(file);
    input.value = "";
  });
}

/* --- Секции (сворачивание) --- */
function bindSections() {
  var heads = document.querySelectorAll(".sec-head");
  for (var i = 0; i < heads.length; i++) {
    heads[i].addEventListener("click", function () {
      var sec = this.parentElement;
      sec.classList.toggle("collapsed");
    });
  }
}

/* --- Настройки (применение в реальном времени) --- */
function openSettings() {
  var modal = document.getElementById("settings-modal");
  var s = state.settings || {};
  setSelect("set-theme", s.theme || "auto");
  setRange("set-font-size", s.font_size || 14);
  setSelect("set-font", s.font_style || "system");
  setSelect("set-language", s.language || "en");
  setSelect("set-comment-lang", s.comment_lang || "en");
  modal.classList.remove("hidden");
}

function setSelect(id, value) {
  var el = document.getElementById(id);
  if (!el) return;
  for (var i = 0; i < el.options.length; i++) {
    if (el.options[i].value === value) {
      el.selectedIndex = i;
      return;
    }
  }
}

function setRange(id, value) {
  var el = document.getElementById(id);
  if (!el) return;
  el.value = value;
  var val = document.getElementById("set-font-size-val");
  if (val) val.textContent = value;
}

function getSelect(id) {
  var el = document.getElementById(id);
  return el ? el.value : "";
}

function getRange(id) {
  var el = document.getElementById(id);
  return el ? Number(el.value) : 14;
}

function collectSettings() {
  return {
    theme: getSelect("set-theme"),
    font_size: getRange("set-font-size"),
    font_style: getSelect("set-font"),
    language: getSelect("set-language"),
    comment_lang: getSelect("set-comment-lang")
  };
}

/* Применение настроек в реальном времени по смене значения. */
function bindSettingsLive() {
  var ids = ["set-theme", "set-font-size", "set-font", "set-language", "set-comment-lang"];
  for (var i = 0; i < ids.length; i++) {
    var el = document.getElementById(ids[i]);
    if (!el) continue;
    el.addEventListener("change", function () {
      post({ type: "settings", settings: collectSettings() });
    });
    el.addEventListener("input", function () {
      post({ type: "settings", settings: collectSettings() });
    });
  }
  var fs = document.getElementById("set-font-size");
  if (fs) {
    fs.addEventListener("input", function () {
      var val = document.getElementById("set-font-size-val");
      if (val) val.textContent = fs.value;
    });
  }
}

function closeSettings() {
  var modal = document.getElementById("settings-modal");
  modal.classList.add("hidden");
  post({ type: "settings", settings: collectSettings() });
}

/* --- Поддержка --- */
function renderDonate(donate) {
  var list = document.getElementById("donate-list");
  if (!list || !donate) return;
  var html = "";
  for (var i = 0; i < donate.length; i++) {
    var d = donate[i];
    html += '<div class="donate-card">';
    html += '<span class="d-title">' + esc(d.title) + "</span>";
    html += '<span class="d-value" title="' + esc(d.value) + '">' + esc(d.value) + "</span>";
    html += '<span class="d-actions">';
    html += '<button class="btn" data-copy="' + esc(d.value) + '">' +
      text("donate.copy") + "</button>";
    if (d.url) {
      html += '<a class="btn" href="' + esc(d.url) + '" target="_blank" rel="noopener">' +
        text("donate.open") + "</a>";
    }
    html += "</span></div>";
  }
  list.innerHTML = html;
  var btns = list.querySelectorAll("[data-copy]");
  for (var j = 0; j < btns.length; j++) {
    btns[j].addEventListener("click", function () {
      copyText(this.getAttribute("data-copy"), "donate.copied");
    });
  }
}

function openSupport() {
  var modal = document.getElementById("support-modal");
  renderDonate(state.ui && state.ui.donate);
  modal.classList.remove("hidden");
}

/* --- Помощь --- */
function renderHelp() {
  var box = document.getElementById("help-content");
  if (!box) return;
  var sections = [
    { title: "help.title", body: "help.what", type: "p" },
    { title: "help.title_steps", body: "help.steps", type: "ol" },
    { title: "help.title_read", body: "help.read", type: "ul" },
    { title: "help.title_pick", body: "help.pick", type: "p" },
    { title: "help.title_pick", body: "help.pick_list", type: "ul" },
    { title: "help.title_tips", body: "help.tips", type: "ul" },
  ];
  var html = "";
  var lastTitle = "";
  for (var i = 0; i < sections.length; i++) {
    var s = sections[i];
    var t = text(s.title);
    if (t !== lastTitle) {
      html += "<h3>" + esc(t) + "</h3>";
      lastTitle = t;
    }
    var body = text(s.body);
    if (s.type === "ol" || s.type === "ul") {
      var items = body.split("\n");
      html += "<" + s.type + ">";
      for (var j = 0; j < items.length; j++) {
        html += "<li>" + esc(items[j]) + "</li>";
      }
      html += "</" + s.type + ">";
    } else {
      html += "<p>" + esc(body) + "</p>";
    }
  }
  html += '<div class="help-source">' + esc(text("help.source")) + "</div>";
  box.innerHTML = html;
}

function openHelp() {
  var modal = document.getElementById("help-modal");
  renderHelp();
  modal.classList.remove("hidden");
}

function bindModals() {
  document.getElementById("settings-close").addEventListener("click", closeSettings);
  document.getElementById("support-close").addEventListener("click", function () {
    document.getElementById("support-modal").classList.add("hidden");
  });
  document.getElementById("help-close").addEventListener("click", function () {
    document.getElementById("help-modal").classList.add("hidden");
  });
  document.getElementById("settings-modal").addEventListener("click", function (e) {
    if (e.target === this) closeSettings();
  });
  document.getElementById("support-modal").addEventListener("click", function (e) {
    if (e.target === this) this.classList.add("hidden");
  });
  document.getElementById("help-modal").addEventListener("click", function (e) {
    if (e.target === this) this.classList.add("hidden");
  });
}

/* --- Инициализация --- */
function init() {
  if (typeof orca !== "undefined" && orca.onMessage) {
    orca.onMessage(onMessage);
  }
  bindToolbar();
  bindFileInput();
  bindModals();
  bindSettingsLive();
  post({ type: "get_state" });
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}
